"""Demergers & mergers — NSE corporate actions with dates."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.config import MERGER_DEMERGER_LOOKBACK_YEARS
from stocks.market.merger_demerger import load_merger_demerger_table, tradebrains_merger_url


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


def render_demerger() -> None:
    st.markdown("### Demergers & Mergers")
    st.caption(
        f"NSE corporate actions · last **{MERGER_DEMERGER_LOOKBACK_YEARS}** years · "
        f"spin-off listings appear as **Spin-off** rows under the parent · "
        f"[Trade Brains reference]({tradebrains_merger_url()})"
    )

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        refresh = st.button("Fetch / Refresh", type="primary", use_container_width=True)
    with c2:
        type_filter = st.selectbox(
            "Type",
            ["All", "Demerger", "Merger", "Merger/Demerger"],
            label_visibility="collapsed",
        )
    with c3:
        role_filter = st.selectbox(
            "Role",
            ["All rows", "Parent only", "Spin-off only"],
            label_visibility="collapsed",
        )
    with c4:
        search = st.text_input(
            "Search company or ticker",
            placeholder="Search company or ticker",
            label_visibility="collapsed",
        )

    with st.spinner(
        "Loading merger/demerger data from NSE"
        + (" and enriching company names…" if refresh else "…")
    ):
        df, fetched_at = load_merger_demerger_table(refresh=refresh)

    if df.empty:
        st.warning(
            "No merger/demerger records returned. Try **Fetch / Refresh** — NSE may rate-limit briefly."
        )
        return

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
    year_pick = st.selectbox("Year", year_options)
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
        f"**{spin_n:,}** spin-off listings · **{dem_n:,}** demergers · **{mer_n:,}** mergers"
    )
    if fetched_at:
        meta += f" · updated {fetched_at}"
    st.caption(meta)

    display = _display_df(work)
    table_height = min(900, max(320, 38 + len(display) * 36))
    st.dataframe(
        display,
        use_container_width=True,
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
