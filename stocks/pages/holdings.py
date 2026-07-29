"""Holdings — PEAD-style portfolio table (no momentum rank)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.config import HOLDINGS_PEAD_CACHE_HOURS
from stocks.core.json_utils import json_safe_obj
from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.shared.portfolio import (
    add_holdings,
    enrich_holdings,
    load_holdings,
    refresh_holdings_pead_metrics,
    remove_holdings,
    run_holdings_pead_backfill,
    seed_default_holdings,
)
from stocks.core.text_utils import safe_str
from stocks.listings.stocks_data import load_india_stocks
from stocks.strategies.pead2.cache_lookup import count_pead_backfill_pending
from stocks.strategies.pead2.html import build_pead2_dashboard_html, pead2_iframe_height

_CACHE_KEY = "holdings_priced_v9"


def _clear_holdings_view_cache() -> None:
    st.session_state.pop(_CACHE_KEY, None)
    st.session_state.pop("holdings_priced_v8", None)
    st.session_state.pop("holdings_priced_v7", None)


def _session_safe_df(df: pd.DataFrame) -> pd.DataFrame:
    """Convert nullable pandas values so Streamlit can JSON-serialize session state."""
    return pd.DataFrame(json_safe_obj(df.to_dict(orient="records")))


def _holdings_for_pead(priced: pd.DataFrame) -> pd.DataFrame:
    """Normalize holdings rows for the PEAD dashboard (price + name sort)."""
    if priced is None or priced.empty:
        return pd.DataFrame()
    out = priced.copy()
    if "price" not in out.columns or out["price"].isna().all():
        if "current_price" in out.columns:
            out["price"] = out["current_price"]
    # Drop momentum leftovers if present from old cache / demerger-style enrich.
    for col in ("momentum_pct", "momentum_rank", "price_1y", "price_1m"):
        if col in out.columns:
            out = out.drop(columns=[col])
    sort_cols = [c for c in ("name", "ticker") if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=True, na_position="last")
    return out.reset_index(drop=True)


def _has_quarters(row: pd.Series) -> bool:
    q = row.get("quarters")
    return isinstance(q, dict) and bool(q.get("labels"))


def _has_snapshot_mas(row: pd.Series) -> bool:
    snap = row.get("snapshot")
    if not isinstance(snap, dict):
        return False
    mas = snap.get("moving_averages") or snap.get("ema_averages")
    return isinstance(mas, list) and len(mas) > 0


def _has_pead_score(row: pd.Series) -> bool:
    score = row.get("pead_score")
    return score is not None and not (isinstance(score, float) and pd.isna(score))


def _load_priced_holdings(holdings: pd.DataFrame) -> pd.DataFrame:
    if _CACHE_KEY in st.session_state:
        return st.session_state[_CACHE_KEY]

    progress = st.progress(0, text="Holdings — loading prices…")

    def _progress(done: int, total: int) -> None:
        if total <= 0:
            progress.progress(1.0, text="Done")
            return
        progress.progress(
            min(done / total, 1.0),
            text=f"Holdings fundamentals {done:,}/{total:,}…",
        )

    try:
        priced = enrich_holdings(
            holdings,
            use_cache=True,
            with_momentum=False,
            with_pead_expand=True,
            pead_progress_callback=_progress,
        )
    except Exception as exc:
        progress.empty()
        st.error(f"Holdings load failed: {exc}")
        return pd.DataFrame()
    progress.empty()
    st.session_state[_CACHE_KEY] = _session_safe_df(priced)
    return priced


def render_holdings() -> None:
    st.markdown("### Holdings")

    holdings = load_holdings(seed_if_empty=True)

    with st.expander("Add / remove holding", expanded=False):
        try:
            universe = load_india_stocks()
        except Exception:
            universe = pd.DataFrame()
        add_c1, add_c2, add_c3 = st.columns([2, 1, 1])
        with add_c1:
            ticker_in = st.text_input(
                "Ticker",
                key="holdings_add_ticker",
                placeholder="e.g. INA or AARTECH",
                help="NSE/BSE symbol. Holding tag appears on PEAD / Governance Map.",
            )
        with add_c2:
            market_in = st.selectbox(
                "Market",
                options=["NSE", "BSE"],
                index=0,
                key="holdings_add_market",
            )
        with add_c3:
            st.write("")
            st.write("")
            add_clicked = st.button("Add holding", type="primary", use_container_width=True)

        if add_clicked:
            ticker = safe_str(ticker_in).upper()
            if not ticker:
                st.warning("Enter a ticker.")
            else:
                market = safe_str(market_in).upper() or "NSE"
                name = None
                if not universe.empty and "ticker" in universe.columns:
                    match = universe[
                        universe["ticker"].astype(str).str.upper() == ticker
                    ]
                    if not match.empty:
                        if "market" in match.columns:
                            mkt_match = match[
                                match["market"].astype(str).str.upper() == market
                            ]
                            row = (mkt_match if not mkt_match.empty else match).iloc[0]
                        else:
                            row = match.iloc[0]
                        name = safe_str(row.get("name")) or None
                        if "market" in row.index and safe_str(row.get("market")):
                            market = safe_str(row.get("market")).upper() or market
                n = add_holdings(
                    [{"ticker": ticker, "market": market, "name": name}]
                )
                _clear_holdings_view_cache()
                if n:
                    st.success(f"Added **{ticker}** ({market}) — Holding tag enabled.")
                else:
                    st.warning("Nothing added.")
                st.rerun()

        if not holdings.empty:
            options = sorted(
                {
                    f"{safe_str(r.ticker).upper()}"
                    + (f" — {safe_str(r.name)}" if safe_str(getattr(r, "name", None)) else "")
                    for r in holdings.itertuples()
                    if safe_str(getattr(r, "ticker", None))
                }
            )
            pick = st.multiselect(
                "Remove holdings",
                options=options,
                key="holdings_remove_pick",
            )
            if st.button("Remove selected", use_container_width=True, disabled=not pick):
                tickers = [safe_str(p.split(" — ")[0]).upper() for p in pick]
                n = remove_holdings(tickers)
                _clear_holdings_view_cache()
                st.success(f"Removed {n} holding(s).") if n else st.info("Nothing removed.")
                st.rerun()

    if holdings.empty:
        st.warning("No holdings in database.")
        if st.button("Load default portfolio"):
            seed_default_holdings(force=True)
            _clear_holdings_view_cache()
            st.rerun()
        return

    tickers = holdings["ticker"].astype(str).str.upper().tolist()
    pead_pending = count_pead_backfill_pending(tickers, max_hours=999999)

    btn_refresh, btn_pead = st.columns(2)
    with btn_refresh:
        if st.button("Refresh prices", type="primary", use_container_width=True):
            _clear_holdings_view_cache()
            st.rerun()
    with btn_pead:
        pead_label = (
            f"Run PEAD ({pead_pending} missing)"
            if pead_pending
            else "PEAD up to date"
        )
        if st.button(
            pead_label,
            use_container_width=True,
            disabled=pead_pending == 0,
            help="Fetch quarterly earnings and compute PEAD scores for holdings not yet scanned.",
        ):
            progress = st.progress(0, text="PEAD — starting…")

            def _pead_progress(done: int, total: int) -> None:
                if total <= 0:
                    progress.progress(1.0, text="PEAD — done")
                    return
                progress.progress(
                    min(done / total, 1.0),
                    text=f"PEAD fetch {done:,}/{total:,}…",
                )

            try:
                fetched = run_holdings_pead_backfill(
                    holdings,
                    progress_callback=_pead_progress,
                )
                priced = st.session_state.get(_CACHE_KEY)
                if priced is not None and not priced.empty:
                    progress.progress(0, text="PEAD — updating scores…")

                    def _merge_progress(done: int, total: int) -> None:
                        if total <= 0:
                            return
                        progress.progress(
                            min(done / total, 1.0),
                            text=f"PEAD merge {done:,}/{total:,}…",
                        )

                    updated = refresh_holdings_pead_metrics(
                        pd.DataFrame(priced),
                        progress_callback=_merge_progress,
                    )
                    st.session_state[_CACHE_KEY] = _session_safe_df(updated)
                progress.empty()
                if fetched:
                    st.success(f"PEAD fetched for {fetched:,} holding(s).")
                else:
                    st.info("No new PEAD data to fetch — scores refreshed from cache.")
            except Exception as exc:
                progress.empty()
                st.error(f"PEAD fetch failed: {exc}")
            st.rerun()

    st.caption(
        "PEAD-style table — click a row for **quarterly Sales/OP/NP/EPS**, "
        "**20/50/100/200 MAs**, news & profile. "
        "Stocks here get the **Holding** tag on Strategy reports and Governance Map."
    )

    priced = _load_priced_holdings(holdings)
    if priced is None or priced.empty:
        return

    view = _holdings_for_pead(priced)
    priced_count = (
        int(pd.Series(view["price"]).notna().sum()) if "price" in view.columns else 0
    )
    qtr_count = sum(_has_quarters(view.iloc[i]) for i in range(len(view))) if not view.empty else 0
    ma_count = sum(_has_snapshot_mas(view.iloc[i]) for i in range(len(view))) if not view.empty else 0
    pead_count = sum(_has_pead_score(view.iloc[i]) for i in range(len(view))) if not view.empty else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Stocks", len(view))
    with m2:
        st.metric("Priced", priced_count)
    with m3:
        st.metric("With PEAD", pead_count)
    with m4:
        st.metric("With quarterly", qtr_count)
    with m5:
        st.metric("With MAs", ma_count)

    if view.empty:
        st.caption("No holdings to show.")
        return

    embed_html = build_pead2_dashboard_html(
        view,
        title="Holdings",
        list_label="Holdings",
        standalone=False,
        variant="holdings",
        default_sort_col="company",
        default_sort_dir=1,
        show_scored_split=False,
    )
    embed_html_iframe(embed_html, height=pead2_iframe_height(len(view), expanded=True))
