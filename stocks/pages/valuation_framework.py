"""Valuation Framework — 10Y sales projection & discount (Zerodha Varsity style)."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from stocks.core.config import FORMULA_100X_MAX_WORKERS, INDIA_STOCKS_DATASET, cap_tier_id_from_label
from stocks.listings.stocks_data import load_india_stocks
from stocks.scans.holdings_industry_filter import apply_holdings_industries_if_checked
from stocks.scans.scan_toolbar import (
    COMPACT_SCAN_BTN_COL_WIDTH,
    WORKERS_COL_WIDTH,
    base_scan_extra_widths,
    inject_scan_toolbar_css,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters
from stocks.strategies.valuation_framework.service import (
    prepare_valuation_universe,
    run_valuation_scan,
)
from stocks.strategies.valuation_framework.strategy import (
    DEFAULT_GROWTH_RATES_PCT,
    LENSKART_ASSUMPTIONS,
    LENSKART_PL_ROWS,
    LENSKART_SALES_15PCT_YEARLY,
    lenskart_reference_result,
    projection_year_labels,
    sales_trajectory_table,
    sensitivity_table,
)


def _fmt_cr(v: float | int | None) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v):,.0f}"


def _render_lenskart_backtest() -> None:
    st.markdown("#### Lenskart · validation backtest")
    st.caption(
        "Zerodha Varsity framework: project 10-year sales at multiple growth rates, "
        "apply a terminal sales multiple, discount to today, compare with market cap."
    )

    result = lenskart_reference_result()
    a = result.assumptions

    st.markdown("**Step 1 · Net profitability & sales trend**")
    pl_df = pd.DataFrame(LENSKART_PL_ROWS)
    st.dataframe(
        pl_df.style.format(
            {
                "sales": "{:,.0f}",
                "operating_profit": "{:,.0f}",
                "net_profit": "{:,.0f}",
            },
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
    )
    sales_cagr = ((6653 / 3788) ** (1 / 2) - 1) * 100
    st.caption(
        f"Sales grew **{sales_cagr:.1f}%** CAGR (Mar 2023 → Mar 2025). "
        f"Net profit turned positive in Mar 2025 (**₹296 Cr**)."
    )

    st.markdown("**Step 2 · Growth trajectory (10 years)**")
    c1, c2 = st.columns([1.1, 1])
    with c1:
        traj = sales_trajectory_table(result)
        st.dataframe(
            traj.style.format({c: "{:,.0f}" for c in traj.columns if c != "Year"}, na_rep="—"),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("All values in **₹ Cr**. Year 1 = first full year after base year.")
    with c2:
        sc15 = result.scenario_at(15.0)
        st.markdown("**Discounting @ 15% growth**")
        if sc15:
            st.metric("Year-10 sales", f"₹ {_fmt_cr(sc15.year10_sales_cr)} Cr")
            st.metric(
                f"Valuation @ {a.sales_multiple:g}x sales",
                f"₹ {_fmt_cr(sc15.valuation_at_multiple_cr)} Cr",
            )
            st.metric(
                f"Discounted to today ({a.discount_rate_pct:g}%)",
                f"₹ {_fmt_cr(sc15.discounted_value_cr)} Cr",
                delta=f"{sc15.margin_of_safety_pct}% vs mcap",
                delta_color="inverse",
            )
            st.metric("Current market cap", f"₹ {_fmt_cr(a.market_cap_cr)} Cr")
        ref_ok = sc15 and abs(sc15.year10_sales_cr - LENSKART_SALES_15PCT_YEARLY[-1]) < 2
        if ref_ok and sc15:
            st.success(
                f"Backtest OK — 15% path matches reference "
                f"(discounted **₹43,235 Cr** vs mcap **₹90,979 Cr** → overvalued)."
            )

    st.markdown("**Step 3 · Value assumptions & sensitivity**")
    ac1, ac2, ac3, ac4 = st.columns(4)
    ac1.metric("Base year sales", f"₹ {_fmt_cr(a.current_sales_cr)} Cr")
    ac2.metric("Sales multiple", f"{a.sales_multiple:g}x")
    ac3.metric("Discount rate", f"{a.discount_rate_pct:g}%")
    ac4.metric("Horizon", f"{a.projection_years} years")

    sens = sensitivity_table(result)
    st.dataframe(
        sens.style.format(
            {
                f"Valuation at {a.sales_multiple:g}x (₹ Cr)": "{:,.0f}",
                "Discounted value (₹ Cr)": "{:,.0f}",
                "Current mkt cap (₹ Cr)": "{:,.0f}",
                "Margin of safety %": "{:,.1f}",
            },
            na_rep="—",
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "**Filter rule:** discounted value **>** market cap → margin of safety (undervalued). "
        "Lenskart fails at 15–25% growth; only **35%** path clears mcap in this reference."
    )


def render_valuation_framework(*, show_title: bool = True) -> None:
    inject_scan_toolbar_css()

    if show_title:
        st.markdown("### Valuation Framework")

    tab_demo, tab_scan = st.tabs(["Lenskart backtest", "Universe scan & filter"])

    with tab_demo:
        _render_lenskart_backtest()

    with tab_scan:
        st.markdown("#### Scan · filter undervalued names")
        st.caption(
            "Uses latest annual **sales** from Yahoo, your multiple/discount assumptions, "
            "and flags stocks where discounted value exceeds market cap."
        )

        try:
            stocks = load_india_stocks()
        except Exception as exc:
            st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
            return

        with st.expander("Assumptions", expanded=False):
            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                sales_multiple = st.number_input(
                    "Terminal sales multiple",
                    min_value=1.0,
                    max_value=20.0,
                    value=5.0,
                    step=0.5,
                    key="vf_multiple",
                )
            with ac2:
                discount_pct = st.number_input(
                    "Discount rate %",
                    min_value=5.0,
                    max_value=30.0,
                    value=15.0,
                    step=0.5,
                    key="vf_discount",
                )
            with ac3:
                proj_years = st.number_input(
                    "Projection years",
                    min_value=5,
                    max_value=15,
                    value=10,
                    step=1,
                    key="vf_years",
                )
            filter_growth = st.selectbox(
                "Filter: undervalued at growth",
                ["Any rate", "15%", "20%", "25%", "30%", "35%"],
                key="vf_filter_growth",
            )

        with scan_toolbar_row(
            *base_scan_extra_widths(WORKERS_COL_WIDTH, COMPACT_SCAN_BTN_COL_WIDTH)
        ) as row:
            filters, cap_tier_label_ui, holdings_industries_only = render_base_scan_filters(
                stocks,
                row,
                key_prefix="vf",
                cap_tier_key="vf_cap_tier",
                holdings_key="vf_holdings_industries_only",
            )
            cap_tier_id = resolve_cap_tier_id(
                filters.market, cap_tier_id_from_label(cap_tier_label_ui)
            )
            min_mcap_cr = cap_tier_min_mcap_cr(cap_tier_id)
            filtered = apply_stock_filters(stocks, filters)
            applied = apply_holdings_industries_if_checked(
                filtered, enabled=holdings_industries_only
            )
            if applied is None:
                return
            filtered, _note = applied

            with row[5]:
                st.number_input(
                    "Conc",
                    min_value=1,
                    max_value=32,
                    value=min(FORMULA_100X_MAX_WORKERS, 16),
                    step=1,
                    key="vf_workers",
                )
            with row[6]:
                run_clicked = st.button(
                    "Scan",
                    type="primary",
                    use_container_width=True,
                    key="vf_scan",
                )

        if not run_clicked:
            cached = st.session_state.get("vf_results")
            if cached is None or (isinstance(cached, pd.DataFrame) and cached.empty):
                return
            results = cached
        else:
            from stocks.strategies.valuation_framework.strategy import FrameworkAssumptions

            assumptions = FrameworkAssumptions(
                base_year=pd.Timestamp.now().year,
                current_sales_cr=1.0,
                market_cap_cr=1.0,
                sales_multiple=float(sales_multiple),
                discount_rate_pct=float(discount_pct),
                projection_years=int(proj_years),
                growth_rates_pct=DEFAULT_GROWTH_RATES_PCT,
            )
            with st.spinner("Preparing universe..."):
                universe, cap_excluded, mcap_excluded = prepare_valuation_universe(
                    filtered,
                    cap_tier_id=cap_tier_id,
                )
            if universe.empty:
                st.warning("No stocks match the current filters.")
                return

            workers = int(st.session_state.get("vf_workers") or FORMULA_100X_MAX_WORKERS)
            progress = st.progress(0, text="Running valuation scan...")
            try:

                def _progress(done: int, total: int) -> None:
                    progress.progress(
                        done / max(total, 1),
                        text=f"Valuation {done}/{total}...",
                    )

                results = run_valuation_scan(
                    universe,
                    assumptions=assumptions,
                    min_mcap_cr=min_mcap_cr,
                    max_workers=workers,
                    progress_callback=_progress,
                )
            finally:
                progress.empty()

            if results.empty:
                st.warning("No rows with annual sales + market cap from Yahoo.")
                return
            st.session_state.vf_results = results

        show = results.copy()
        growth_pass_col = {
            "15%": "pass_15pct",
            "20%": "pass_20pct",
            "25%": "pass_25pct",
            "30%": "pass_30pct",
            "35%": "pass_35pct",
        }
        if filter_growth in growth_pass_col:
            col = growth_pass_col[filter_growth]
            show = show[show[col] == True]
        elif st.session_state.get("vf_undervalued_only", True):
            show = show[show["pass_undervalued"] == True]

        st.checkbox(
            "Show undervalued only (any growth rate)",
            value=st.session_state.get("vf_undervalued_only", True),
            key="vf_undervalued_only",
        )

        disp = show[
            [
                "ticker",
                "name",
                "sales_cr",
                "market_cap_cr",
                "disc_15_cr",
                "disc_20_cr",
                "disc_25_cr",
                "mos_15_pct",
                "best_undervalued_growth_pct",
                "pass_undervalued",
            ]
        ].copy()
        disp = disp.rename(
            columns={
                "sales_cr": "Sales ₹Cr",
                "market_cap_cr": "Mcap ₹Cr",
                "disc_15_cr": "Disc@15%",
                "disc_20_cr": "Disc@20%",
                "disc_25_cr": "Disc@25%",
                "mos_15_pct": "MoS@15%",
                "best_undervalued_growth_pct": "Min growth pass",
                "pass_undervalued": "Undervalued",
            }
        )
        st.caption(
            f"**{len(show):,}** / **{len(results):,}** stocks shown · "
            f"**{int(results['pass_undervalued'].sum()):,}** undervalued at some growth rate."
        )
        st.dataframe(
            disp.style.format(
                {
                    "Sales ₹Cr": "{:,.0f}",
                    "Mcap ₹Cr": "{:,.0f}",
                    "Disc@15%": "{:,.0f}",
                    "Disc@20%": "{:,.0f}",
                    "Disc@25%": "{:,.0f}",
                    "MoS@15%": "{:,.1f}",
                    "Min growth pass": "{:,.0f}",
                },
                na_rep="—",
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Download CSV",
            data=show.to_csv(index=False).encode("utf-8"),
            file_name="valuation_framework.csv",
            mime="text/csv",
            key="download_vf_csv",
        )
