"""Data — company list with website + Yahoo about + scraped About Us."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.text_utils import safe_str
from stocks.market.about_data import (
    about_coverage_stats,
    load_about_list,
    migrate_legacy_about_columns,
    refresh_scraped_about,
    refresh_yahoo_about,
)


def _list_view(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    cols = [
        "ticker",
        "name",
        "market",
        "website",
        "yf_about",
        "scraped_about",
        "about",
    ]
    present = [c for c in cols if c in out.columns]
    rename = {
        "ticker": "Ticker",
        "name": "Company",
        "market": "Market",
        "website": "Website",
        "yf_about": "Yahoo about",
        "scraped_about": "Scraped About Us",
        "about": "About (preferred)",
    }
    view = out[present].rename(columns=rename)
    # Truncate long text for the table preview.
    for col in ("Yahoo about", "Scraped About Us", "About (preferred)"):
        if col in view.columns:
            view[col] = view[col].map(
                lambda t: (safe_str(t)[:280] + "…") if len(safe_str(t)) > 280 else safe_str(t)
            )
    return view


def render_data() -> None:
    migrate_legacy_about_columns()
    st.title("Data")
    st.caption(
        "Company websites and About text from **Yahoo** and **corporate site scrapes**, "
        "stored in ``stocks_ai.db``."
    )

    section = st.radio(
        "Section",
        ["List"],
        horizontal=True,
        label_visibility="collapsed",
        key="data_section_v1",
    )

    if section != "List":
        return

    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
    with c1:
        market = st.selectbox(
            "Market",
            ["All", "NSE", "NSE SME", "BSE"],
            key="data_list_market",
        )
    with c2:
        missing_only = st.checkbox(
            "Gaps only (missing web / Yahoo / scrape)",
            value=False,
            key="data_list_gaps",
        )
    with c3:
        limit = st.number_input(
            "Max rows (0 = all)",
            min_value=0,
            max_value=10000,
            value=500,
            step=100,
            key="data_list_limit",
        )

    board = load_about_list(
        market=None if market == "All" else market,
        limit=None if not limit else int(limit),
        missing_only=bool(missing_only),
    )
    stats = about_coverage_stats(board)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Shown", stats["total"])
    m2.metric("Website", stats["website"])
    m3.metric("Yahoo about", stats["yf_about"])
    m4.metric("Scraped", stats["scraped_about"])
    m5.metric("Both abouts", stats["both"])

    view = _list_view(board)
    if view.empty:
        st.info("No listings match — refresh NSE listings or widen filters.")
    else:
        st.dataframe(view, width="stretch", hide_index=True, height=min(640, 40 + len(view) * 35))

    with st.expander("Refresh about data", expanded=False):
        st.caption(
            "Yahoo fills ``yf_about``. Scrape fills ``scraped_about`` from the corporate "
            "About Us page (needs a website). Both are kept in the DB."
        )
        max_batch = st.number_input(
            "Batch size",
            min_value=1,
            max_value=500,
            value=25,
            key="data_about_batch",
        )
        force = st.checkbox("Force re-scrape even if scraped about exists", key="data_force_scrape")
        b1, b2 = st.columns(2)
        targets = board.head(int(max_batch)) if not board.empty else board
        markets = {
            safe_str(r.ticker).upper(): safe_str(r.market) or "NSE"
            for r in targets.itertuples(index=False)
        } if not targets.empty else {}
        names = {
            safe_str(r.ticker).upper(): safe_str(r.name)
            for r in targets.itertuples(index=False)
        } if not targets.empty else {}
        tickers = list(markets.keys())

        with b1:
            if st.button("Fetch Yahoo about", key="data_fetch_yf", disabled=not tickers):
                bar = st.progress(0.0, text="Yahoo about…")

                def _prog(done, total, label):
                    frac = (done / total) if total else 1.0
                    bar.progress(min(1.0, frac), text=f"Yahoo {done}/{total} {label}")

                result = refresh_yahoo_about(
                    tickers, markets=markets, progress_callback=_prog
                )
                bar.progress(1.0, text="Done")
                st.success(
                    f"Yahoo tried={result['tried']} ok={result['ok']} "
                    f"errors={result['errors']}"
                )
                st.rerun()

        with b2:
            if st.button("Scrape About Us", key="data_scrape_about", disabled=not tickers):
                bar = st.progress(0.0, text="Scraping About Us…")

                def _prog(done, total, label):
                    frac = (done / total) if total else 1.0
                    bar.progress(min(1.0, frac), text=f"Scrape {done}/{total} {label}")

                result = refresh_scraped_about(
                    tickers,
                    markets=markets,
                    names=names,
                    force=bool(force),
                    progress_callback=_prog,
                )
                bar.progress(1.0, text="Done")
                st.success(
                    f"Scrape tried={result['tried']} ok={result['ok']} "
                    f"skipped={result['skipped']} errors={result['errors']}"
                )
                st.rerun()
