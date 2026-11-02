"""Napkin Investing Framework tab — Watching List universe, PEAD-style report."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.scans.list_playlist import (
    WATCHING_LIST_LABELS,
    format_watching_list_option,
)
from stocks.scans.scan_toolbar import inject_scan_toolbar_css
from stocks.strategies.napkin.html import (
    build_napkin_html,
    embed_napkin_report,
    enrich_napkin_display,
    napkin_iframe_height,
)
from stocks.strategies.napkin.napkin_framework import (
    DEFAULT_BASE_RATE,
    DEFAULT_BASE_TV_WEIGHT,
    DEFAULT_CURRENT_RATE,
    DEFAULT_MIN_ADV,
    NapkinParams,
    adj_tv_weight,
    near_term_weight,
    run_napkin_pipeline,
)

# Same session key as Watching — do not fork list selection.
_WATCHING_LIST_KEY = "watching_list_v2"
_RESULT_KEY = "napkin_fw_result_v1"


def _load_list_universe(list_label: str) -> pd.DataFrame:
    """Watching list + local name/sector/market/website enrichment."""
    from stocks.pages.watching import _raw_for_list
    from stocks.shared.early_edge import enrich_watching_board

    raw = _raw_for_list(list_label)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["ticker", "name", "market", "sector", "website"])
    try:
        enriched = enrich_watching_board(raw, list_tag=list_label, fetch_live_prices=False)
    except Exception:
        enriched = raw.copy()
    if enriched is None or enriched.empty:
        enriched = raw.copy()
    out = enriched.copy()
    out["ticker"] = out["ticker"].astype(str).str.strip().str.upper()
    if "name" not in out.columns:
        out["name"] = out["ticker"]
    if "sector" not in out.columns and "industry" in out.columns:
        out["sector"] = out["industry"]
    cols = [
        c
        for c in ("ticker", "name", "market", "sector", "industry", "website", "market_cap_cr")
        if c in out.columns
    ]
    return out[cols].drop_duplicates("ticker").reset_index(drop=True)


def _scatter(scored: pd.DataFrame):
    try:
        import plotly.graph_objects as go
    except Exception:
        return None
    if scored is None or scored.empty:
        return None
    df = scored.copy()
    df["required_cagr"] = pd.to_numeric(df["required_cagr"], errors="coerce")
    df["expected_cagr"] = pd.to_numeric(df["expected_cagr"], errors="coerce")
    df = df.dropna(subset=["required_cagr", "expected_cagr"])
    # Clip extreme outliers so Buys stay visible
    df = df[(df["required_cagr"] <= 1.2) & (df["expected_cagr"] <= 1.2)]
    if df.empty:
        return None

    color_map = {
        "Napkin Buy": "#15803d",
        "Fair Value": "#64748b",
        "Overvalued": "#b91c1c",
    }
    fig = go.Figure()
    for verd, color in color_map.items():
        sub = df[df["verdict"] == verd]
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["required_cagr"],
                y=sub["expected_cagr"],
                mode="markers",
                name=verd,
                marker=dict(color=color, size=8, opacity=0.85),
                text=sub["ticker"],
                customdata=sub[["pe"]].fillna("—"),
                hovertemplate="%{text}<br>PE=%{customdata[0]}<br>Req=%{x:.1%}<br>Exp=%{y:.1%}<extra></extra>",
            )
        )
    lo = 0.0
    hi = float(max(df["required_cagr"].max(), df["expected_cagr"].max(), 0.2))
    fig.add_trace(
        go.Scatter(
            x=[lo, hi],
            y=[lo, hi],
            mode="lines",
            name="Exp = Req",
            line=dict(dash="dash", color="#94a3b8", width=1),
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        height=280,
        margin=dict(l=8, r=8, t=8, b=8),
        xaxis_title="Required CAGR",
        yaxis_title="Expected CAGR",
        xaxis_tickformat=".0%",
        yaxis_tickformat=".0%",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
        plot_bgcolor="#fff",
        paper_bgcolor="#fff",
    )
    return fig


def render_napkin(*, show_title: bool = True) -> None:
    inject_scan_toolbar_css()

    if show_title:
        st.markdown("### Napkin Investing Framework")
    st.caption("What growth does the current PE actually demand?")

    list_opts = list(WATCHING_LIST_LABELS)
    if _WATCHING_LIST_KEY not in st.session_state or st.session_state[_WATCHING_LIST_KEY] not in list_opts:
        st.session_state[_WATCHING_LIST_KEY] = list_opts[0]

    with st.container(border=True):
        r1 = st.columns([1.4, 1.0, 1.0, 1.0], vertical_alignment="bottom", gap="small")
        with r1[0]:
            selected = st.selectbox(
                "List",
                list_opts,
                key=_WATCHING_LIST_KEY,
                format_func=format_watching_list_option,
                help="Same list as Watching — Napkin runs on this universe.",
            )
        with r1[1]:
            base_rate = st.slider(
                "Base Interest Rate (%)",
                1.0,
                15.0,
                float(DEFAULT_BASE_RATE),
                0.1,
                key="napkin_fw_base_rate",
            )
        with r1[2]:
            current_rate = st.slider(
                "Current 10Y Yield (%)",
                1.0,
                15.0,
                float(DEFAULT_CURRENT_RATE),
                0.1,
                key="napkin_fw_current_rate",
            )
        with r1[3]:
            base_tv_pct = st.slider(
                "Base Terminal Weight (%)",
                40,
                95,
                int(round(DEFAULT_BASE_TV_WEIGHT * 100)),
                1,
                key="napkin_fw_tv",
            )

        r2 = st.columns([1.0, 1.0, 1.2], vertical_alignment="bottom", gap="small")
        with r2[0]:
            min_adv = st.slider(
                "min_adv (₹)",
                0.0,
                50_000_000.0,
                float(DEFAULT_MIN_ADV),
                100_000.0,
                key="napkin_fw_min_adv",
            )
        with r2[1]:
            force_full = st.checkbox(
                "Force full run (slow)",
                value=False,
                key="napkin_fw_force",
                help="NSE / NSE SME: fetch fundamentals for every price-screen survivor.",
            )
        with r2[2]:
            run_clicked = st.button("Run Napkin", type="primary", width="stretch", key="napkin_fw_run")

    params = NapkinParams(
        base_rate=float(base_rate),
        current_rate=float(current_rate),
        base_tv_weight=float(base_tv_pct) / 100.0,
        min_adv=float(min_adv),
        force_full=bool(force_full),
    )
    adj = adj_tv_weight(params.base_rate, params.current_rate, params.base_tv_weight)
    near = near_term_weight(params.base_rate, params.current_rate, params.base_tv_weight)

    if run_clicked:
        universe = _load_list_universe(selected)
        prog = st.progress(0.0, text="Napkin — price screen…")

        def _on_fund(done: int, total: int) -> None:
            if total:
                prog.progress(min(1.0, done / total), text=f"Fetching fundamentals {done}/{total}…")

        result = run_napkin_pipeline(
            universe,
            selected,
            params,
            progress_callback=_on_fund,
        )
        prog.empty()
        st.session_state[_RESULT_KEY] = result
        st.session_state[_RESULT_KEY + "_list"] = selected

    result = st.session_state.get(_RESULT_KEY)
    if result is None:
        st.caption(
            f"Terminal **{adj:.0%}** · Near **{near:.0%}** — pick a List, then **Run Napkin**."
        )
        st.caption(
            "Educational tool based on the Lotusdew Napkin Framework. Not investment advice."
        )
        return

    list_used = st.session_state.get(_RESULT_KEY + "_list") or selected
    scored = enrich_napkin_display(result.scored, result.universe)
    gaps = 0
    if scored is not None and not scored.empty and "verdict" in scored.columns:
        gaps = int(
            scored["verdict"].isin(["Insufficient Data", "Unprofitable"]).sum()
        )
    health = (
        f"{result.in_list} in list · {result.passed_price} screened · "
        f"{result.fundamentals_available} with PE · {result.scored_n} scored"
        + (f" · {gaps} gaps" if gaps else "")
        + f" · Prices {result.prices_ts or '—'} · Fund {result.fundamentals_ts or '—'}"
    )

    html_doc = build_napkin_html(
        scored,
        list_label=str(list_used),
        adj_tv=adj,
        near_w=near,
        health=health,
    )
    n_show = len(scored) if scored is not None else 0
    # Default chip shows Buys — height for visible subset approx
    embed_napkin_report(html_doc, height=napkin_iframe_height(min(n_show, 25)))

    with st.expander("Scatter (Req vs Exp)", expanded=False):
        fig = _scatter(scored)
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No plottable rows (need both Required and Expected CAGR).")

    if scored is not None and not scored.empty:
        export_cols = [
            c
            for c in (
                "ticker",
                "name",
                "pe",
                "pe_source",
                "required_cagr",
                "expected_cagr",
                "napkin_score",
                "verdict",
                "growth_source",
                "data_note",
                "sc",
                "tv",
                "website",
            )
            if c in scored.columns
        ]
        st.download_button(
            "Download Napkin CSV",
            data=scored[export_cols].to_csv(index=False).encode("utf-8"),
            file_name="napkin_framework.csv",
            mime="text/csv",
            key="napkin_fw_csv",
        )

    for note in result.notes:
        st.caption(f"· {note}")
    st.caption(
        "Educational tool based on the Lotusdew Napkin Framework. Not investment advice."
    )
