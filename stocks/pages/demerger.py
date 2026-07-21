"""Demergers & mergers — NSE corporate actions with dates."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.config import MERGER_DEMERGER_LOOKBACK_YEARS
from stocks.core.json_utils import json_safe_obj
from stocks.market.merger_demerger import load_merger_demerger_table, tradebrains_merger_url
from stocks.shared.demerger_stocks import enrich_demerger_stocks, load_demerger_stocks

_DS_CACHE_KEY = "demerger_stocks_priced_v1"


def _filter_lookback_years(df: pd.DataFrame, years: int) -> pd.DataFrame:
    """Keep rows whose ex-date falls within the last N calendar years."""
    if df.empty or "ex_date" not in df.columns or years < 1:
        return df
    cutoff = pd.Timestamp.now().normalize() - pd.DateOffset(years=years)
    ex = pd.to_datetime(df["ex_date"], errors="coerce")
    return df[ex >= cutoff].copy()


def _filter_year_with_pairs(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Year filter that keeps parent + spin-off listing rows together."""
    if df.empty:
        return df
    work = df.copy()
    work["_ticker"] = work["ticker"].astype(str).str.upper()
    ex_years = pd.to_datetime(work["ex_date"], errors="coerce").dt.year
    seed = set(work.loc[ex_years == year, "_ticker"])
    if not seed:
        return work.iloc[0:0].drop(columns=["_ticker"], errors="ignore")
    keep: set[str] = set()
    for _, row in work.iterrows():
        ticker = str(row["_ticker"])
        parent = str(row.get("parent_ticker") or "").upper()
        demerged = str(row.get("demerged_ticker") or "").upper()
        if ticker in seed or parent in seed or demerged in seed:
            keep.add(ticker)
    return work[work["_ticker"].isin(keep)].drop(columns=["_ticker"])


def _display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "ex_date" in out.columns:
        out["ex_date"] = pd.to_datetime(out["ex_date"], errors="coerce").dt.strftime("%d-%b-%Y")
    if "record_date" in out.columns:
        out["record_date"] = pd.to_datetime(out["record_date"], errors="coerce").dt.strftime(
            "%d-%b-%Y"
        )
    cols = [
        "row_role",
        "ex_date",
        "record_date",
        "company",
        "ticker",
        "action_type",
        "ratio",
        "counterparty_company",
        "counterparty_ticker",
        "subject",
        "isin",
        "series",
        "source",
        "screener_link",
        "tv_link",
    ]
    present = [c for c in cols if c in out.columns]
    rename = {
        "row_role": "Role",
        "ex_date": "Ex-date",
        "record_date": "Record date",
        "company": "Company",
        "ticker": "Ticker",
        "action_type": "Type",
        "ratio": "Ratio",
        "counterparty_company": "Demerged / merged company",
        "counterparty_ticker": "Other ticker",
        "subject": "Details",
        "isin": "ISIN",
        "series": "Series",
        "source": "Source",
        "screener_link": "Screener",
        "tv_link": "TradingView",
    }
    return out[present].rename(columns=rename)


def _ds_display_df(priced: pd.DataFrame) -> pd.DataFrame:
    df = priced.copy()
    if "ex_date" in df.columns:
        df["ex_date"] = pd.to_datetime(df["ex_date"], errors="coerce").dt.strftime("%d-%b-%Y")
    if "momentum_rank" in df.columns:
        df = df.sort_values("momentum_rank", ascending=True, na_position="last")
    elif "momentum_pct" in df.columns:
        df = df.sort_values("momentum_pct", ascending=False, na_position="last")
        df["momentum_rank"] = range(1, len(df) + 1)
    elif "ex_date" in df.columns:
        df = df.sort_values(["ex_date", "role", "ticker"], ascending=[False, True, True])

    rename = {
        "momentum_rank": "Rank",
        "role": "Role",
        "ticker": "Ticker",
        "name": "Company",
        "peer_ticker": "Peer",
        "peer_company": "Peer company",
        "ex_date": "Ex-date",
        "momentum_pct": "Momentum %",
        "current_price": "Price",
        "price_1y": "Price 1Y",
        "price_1m": "Price 1M",
        "industry": "Industry",
        "screener_link": "Screener",
        "tv_link": "TradingView",
    }
    present = [c for c in rename if c in df.columns]
    return df[present].rename(columns=rename).reset_index(drop=True)


def _render_nse_actions(df: pd.DataFrame, fetched_at: str | None, lookback_years: int) -> None:
    type_filter = st.selectbox(
        "Type",
        ["All", "Demerger", "Merger", "Merger/Demerger"],
        key="demerger_type_filter",
    )
    role_filter = st.selectbox(
        "Role",
        ["All rows", "Parent only", "Spin-off only"],
        key="demerger_role_filter",
    )
    search = st.text_input(
        "Search company or ticker",
        placeholder="Search company or ticker",
        key="demerger_search",
    )

    work = df.copy()
    if type_filter != "All" and "action_type" in work.columns:
        work = work[work["action_type"].astype(str) == type_filter]
    if role_filter == "Parent only" and "row_role" in work.columns:
        work = work[work["row_role"].astype(str) == "Parent"]
    elif role_filter == "Spin-off only" and "row_role" in work.columns:
        work = work[work["row_role"].astype(str) == "Spin-off"]
    if search.strip():
        q = search.strip().lower()
        cols = [
            c
            for c in (
                "company",
                "ticker",
                "counterparty_company",
                "counterparty_ticker",
                "demerged_company",
                "parent_company",
                "related_company",
                "related_ticker",
            )
            if c in work.columns
        ]
        mask = False
        for col in cols:
            mask = mask | work[col].astype(str).str.lower().str.contains(q, na=False)
        work = work[mask]

    years = sorted(
        pd.to_datetime(df["ex_date"], errors="coerce").dt.year.dropna().astype(int).unique(),
        reverse=True,
    )
    year_options = ["All"] + [str(y) for y in years]
    year_pick = st.selectbox("Year", year_options, key="demerger_year")
    if year_pick != "All":
        work = _filter_year_with_pairs(work, int(year_pick))

    spin_n = int((df.get("row_role", pd.Series(dtype=str)) == "Spin-off").sum())
    dem_n = int((df["action_type"] == "Demerger").sum()) if "action_type" in df.columns else 0
    mer_n = int((df["action_type"] == "Merger").sum()) if "action_type" in df.columns else 0
    cp_col = df.get("counterparty_company", pd.Series(dtype=object))
    named_n = int(cp_col.astype(str).str.strip().replace({"": None, "nan": None, "None": None}).notna().sum())
    meta = (
        f"**{len(work):,}** shown · **{len(df):,}** total · "
        f"**{named_n:,}** with demerged/merged company · "
        f"**{spin_n:,}** spin-off listings · **{dem_n:,}** demergers · **{mer_n:,}** mergers · "
        f"**{lookback_years}**-year window"
    )
    if fetched_at:
        meta += f" · updated {fetched_at}"
    st.caption(meta)

    display = _display_df(work)
    table_height = min(900, max(320, 38 + len(display) * 36))
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=table_height,
        column_config={
            "Role": st.column_config.TextColumn("Role", width="small"),
            "Screener": st.column_config.LinkColumn("Screener", display_text="SC"),
            "TradingView": st.column_config.LinkColumn("TradingView", display_text="TV"),
        },
    )

    st.download_button(
        "Download CSV",
        data=work.to_csv(index=False).encode("utf-8"),
        file_name="merger_demerger_nse.csv",
        mime="text/csv",
        key="download_merger_demerger_csv",
    )


def _render_ds_stock_list() -> None:
    stocks = load_demerger_stocks()
    if stocks.empty:
        st.info("No D&S stocks saved yet. Open **NSE Actions** and click **Fetch / Refresh**.")
        return

    parent_n = int((stocks.get("role", pd.Series(dtype=str)) == "Parent").sum())
    spin_n = int((stocks.get("role", pd.Series(dtype=str)) == "Spin-off").sum())
    st.caption(
        f"**{len(stocks):,}** stocks saved · **{parent_n:,}** parents · **{spin_n:,}** spin-offs · "
        f"auto-updated when demerger data loads · use **D&S** in scan Market filter"
    )

    role_filter = st.selectbox(
        "Role",
        ["All", "Parent", "Spin-off"],
        key="ds_role_filter",
    )
    work = stocks.copy()
    if role_filter != "All":
        work = work[work["role"].astype(str) == role_filter]

    if st.button("Refresh prices", type="primary", key="ds_refresh_prices"):
        st.session_state.pop(_DS_CACHE_KEY, None)
        st.rerun()

    if _DS_CACHE_KEY not in st.session_state:
        with st.spinner("Fetching prices and momentum…"):
            priced = enrich_demerger_stocks(work if role_filter != "All" else stocks, use_cache=True)
        st.session_state[_DS_CACHE_KEY] = pd.DataFrame(
            json_safe_obj(priced.to_dict(orient="records"))
        )
    else:
        priced = st.session_state[_DS_CACHE_KEY]
        if role_filter != "All":
            priced = priced[priced["role"].astype(str) == role_filter]

    priced_count = (
        int(pd.Series(priced["current_price"]).notna().sum())
        if "current_price" in priced.columns
        else 0
    )
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Stocks", len(priced))
    with m2:
        st.metric("Priced", priced_count)
    with m3:
        st.metric(
            "With momentum",
            int(pd.Series(priced["momentum_pct"]).notna().sum())
            if "momentum_pct" in priced.columns
            else 0,
        )

    display = _ds_display_df(priced)
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d"),
            "Momentum %": st.column_config.NumberColumn(format="%.2f"),
            "Price": st.column_config.NumberColumn(format="%.2f"),
            "Price 1Y": st.column_config.NumberColumn(format="%.2f"),
            "Price 1M": st.column_config.NumberColumn(format="%.2f"),
            "Screener": st.column_config.LinkColumn(display_text="Open"),
            "TradingView": st.column_config.LinkColumn(display_text="Chart"),
        },
    )


def render_demerger() -> None:
    st.markdown("### Demergers & Mergers")

    if "demerger_lookback_years" not in st.session_state:
        st.session_state.demerger_lookback_years = MERGER_DEMERGER_LOOKBACK_YEARS

    lookback_years = int(st.session_state.demerger_lookback_years)

    c1, c2 = st.columns([1.1, 0.7])
    with c1:
        refresh = st.button("Fetch / Refresh", type="primary", width="stretch")
    with c2:
        years_raw = st.text_input(
            "Years",
            value=str(lookback_years),
            placeholder="15",
            label_visibility="collapsed",
            help="How many calendar years of NSE corporate actions to load",
        )
        try:
            lookback_years = max(1, min(30, int(str(years_raw).strip())))
        except ValueError:
            lookback_years = MERGER_DEMERGER_LOOKBACK_YEARS
        st.session_state.demerger_lookback_years = lookback_years

    st.caption(
        f"NSE corporate actions · last **{lookback_years}** years · "
        f"parents + spin-offs auto-saved to **D&S** list · "
        f"[Trade Brains reference]({tradebrains_merger_url()})"
    )

    with st.spinner(
        "Loading merger/demerger data from NSE"
        + (" and enriching company names…" if refresh else "…")
    ):
        df, fetched_at = load_merger_demerger_table(
            refresh=refresh,
            lookback_years=lookback_years,
        )

    if refresh:
        st.session_state.pop(_DS_CACHE_KEY, None)

    if df.empty:
        st.warning(
            "No merger/demerger records returned. Try **Fetch / Refresh** — NSE may rate-limit briefly."
        )
        return

    df = _filter_lookback_years(df, lookback_years)

    tab_nse, tab_ds = st.tabs(["NSE Actions", "D&S Stock List"])
    with tab_nse:
        _render_nse_actions(df, fetched_at, lookback_years)
    with tab_ds:
        _render_ds_stock_list()
