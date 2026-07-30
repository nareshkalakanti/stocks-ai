"""SuperStars — tracked ace investor portfolios from Trendlyne."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import streamlit as st

from stocks.core.config import SUPERSTAR_CACHE_HOURS, CAP_TIERS, cap_tier_labels, cap_tier_id_from_label
from stocks.core.database import (
    load_company_profiles_from_db,
    load_market_cap_from_db,
    save_superstar_holdings,
    superstar_holdings_db_stats,
)
from stocks.core.text_utils import safe_str, sanitize_website
from stocks.shared.portfolio import load_holdings
from stocks.shared.links import attach_research_links
from stocks.shared.fund_watchlists import sync_all_fund_watchlists
from stocks.scans.scan_toolbar import default_cap_tier_label
from stocks.governance.score import mcap_cap_code
from stocks.market.company_profile import merge_company_profile
from stocks.shared.superstars.holdings import (
    aggregate_all_portfolios,
    enrich_superstar_classification,
    portfolios_from_db,
    _sector_is_missing,
)
from stocks.shared.superstars.cache import (
    load_cached_superstar_portfolios,
    save_cached_superstar_portfolios,
)
from stocks.shared.superstars.html import build_superstars_html, superstars_iframe_height
from stocks.shared.superstars.investors import (
    SUPERSTAR_INVESTORS,
    _build_company_lookup,
    _load_symbol_cache_from_db,
    load_superstar_portfolio,
)
from stocks.dashboards.report_html import embed_html_iframe

_CACHE_VERSION = 19  # NSE SME tickers (strip -SM) for Negen / Niveshaay
_DISPLAY_READY_KEY = "superstar_display_ready_v20"
_SS_SECTOR_KEY = "ss_sector_filter"
_SS_CAP_KEY = "ss_cap_tier"
_SS_INVESTOR_KEY = "ss_investor"
_SS_CHANGE_KEY = "ss_change_filter"
_SS_ALL = "All"
_SS_CHANGE_OPTS = ("All", "New", "Increased", "Decreased")
_SS_CHANGE_MAP = {
    "New": "new",
    "Increased": "increased",
    "Decreased": "decreased",
}


def _df_row_count(value: pd.DataFrame | list | None) -> int:
    if value is None:
        return 0
    if isinstance(value, pd.DataFrame):
        return len(value)
    return len(value)


def _loaded_investor_count(portfolios: dict, investor_names: list[str]) -> int:
    return len(
        [
            n
            for n in investor_names
            if n in portfolios and int(portfolios[n].get("count") or 0) > 0
        ]
    )


def _hydrate_portfolios_from_disk(portfolios: dict, fetched_at: dict) -> bool:
    cached = load_cached_superstar_portfolios(
        max_hours=SUPERSTAR_CACHE_HOURS,
        cache_version=_CACHE_VERSION,
    )
    if not cached:
        return False
    data, ts_display = cached
    portfolios.clear()
    portfolios.update(data)
    fetched_at.clear()
    for name in data:
        fetched_at[name] = ts_display
    st.session_state["superstar_from_disk_cache"] = True
    return True


def _hydrate_portfolios_from_db(portfolios: dict, fetched_at: dict) -> bool:
    investor_names = [entry["name"] for entry in SUPERSTAR_INVESTORS]
    data, ts_map, ts = portfolios_from_db(investor_names)
    if not data or _loaded_investor_count(data, investor_names) == 0:
        return False
    portfolios.clear()
    portfolios.update(data)
    fetched_at.clear()
    fetched_at.update(ts_map)
    st.session_state["superstar_from_db"] = True
    st.session_state["superstar_db_fetched_at"] = ts
    return True


def _sector_missing_mask(series: pd.Series) -> pd.Series:
    return series.map(_sector_is_missing)


def _attach_mcap_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if work.empty:
        return work
    if "market_cap_cr" not in work.columns:
        work["market_cap_cr"] = pd.NA
    sym_col = "ticker" if "ticker" in work.columns else "symbol"

    def _mcap_keys(t: str) -> list[str]:
        s = safe_str(t).upper()
        if not s:
            return []
        keys = [s]
        if s.endswith("-SM"):
            keys.append(s[:-3])
        return keys

    tickers: list[str] = []
    for t in work[sym_col]:
        tickers.extend(_mcap_keys(t))
    tickers = list(dict.fromkeys(tickers))
    if tickers:
        mcap_df = load_market_cap_from_db(tickers, allow_stale=True)
        if not mcap_df.empty:
            mcap_map = {
                safe_str(r["ticker"]).upper(): r["market_cap_cr"]
                for _, r in mcap_df.iterrows()
                if safe_str(r.get("ticker"))
            }
            work["market_cap_cr"] = work[sym_col].map(
                lambda t: next(
                    (mcap_map[k] for k in _mcap_keys(t) if k in mcap_map),
                    None,
                )
            )
    work["cap_code"] = work["market_cap_cr"].map(mcap_cap_code)
    return work


def _attach_website_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if work.empty:
        return work
    if "website" not in work.columns:
        work["website"] = None
    sym_col = "ticker" if "ticker" in work.columns else "symbol"
    tickers = [safe_str(t).upper() for t in work[sym_col] if safe_str(t)]
    if not tickers:
        return work
    profiles = load_company_profiles_from_db(tickers)
    work["website"] = work[sym_col].map(
        lambda t: sanitize_website((profiles.get(safe_str(t).upper()) or {}).get("website"))
    )
    return work


def _prepare_display_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    needs_links = "screener_link" not in work.columns
    needs_sector = "sector" not in work.columns or work["sector"].map(_sector_is_missing).all()
    if needs_links or needs_sector:
        work = enrich_superstar_classification(work)
        work["ticker"] = work["symbol"]
        work["market"] = work["exchange"].map(
            lambda x: (
                "BSE"
                if safe_str(x).upper() == "BSE"
                else ("NSE SME" if safe_str(x).upper() == "NSE SME" else "NSE")
            )
        )
        work = attach_research_links(work)
    if "ticker" not in work.columns:
        work["ticker"] = work["symbol"]
    if "sector" in work.columns:
        work["sector"] = work["sector"].apply(lambda s: safe_str(s) or "—")
    else:
        work["sector"] = "—"
    miss = _sector_missing_mask(work["sector"])
    if miss.any():
        filled = enrich_superstar_classification(work.loc[miss].copy())
        if not filled.empty and "sector" in filled.columns:
            work.loc[miss, "sector"] = filled["sector"].apply(
                lambda s: safe_str(s) or "—"
            ).values
    work = _attach_mcap_columns(work)
    work = _attach_website_columns(work)
    return work


def _cap_tier_mask(mcap: pd.Series, tier_id: str) -> pd.Series:
    if not tier_id or tier_id == "all":
        return pd.Series(True, index=mcap.index)
    tier = next((t for t in CAP_TIERS if t["id"] == tier_id), None)
    if not tier:
        return pd.Series(True, index=mcap.index)
    vals = pd.to_numeric(mcap, errors="coerce")
    mask = vals.notna()
    if tier.get("min") is not None:
        mask &= vals >= float(tier["min"])
    if tier.get("max") is not None:
        mask &= vals < float(tier["max"])
    return mask


def _apply_superstar_filters(
    df: pd.DataFrame | None,
    *,
    sector: str,
    cap_tier_id: str,
    change: str = "All",
) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.iloc[0:0].copy()
    work = df.copy()
    if sector and sector != "All" and "sector" in work.columns:
        work = work[work["sector"].astype(str) == sector]
    if cap_tier_id and cap_tier_id != "all":
        if "market_cap_cr" not in work.columns:
            work = _attach_mcap_columns(work)
        work = work[_cap_tier_mask(work["market_cap_cr"], cap_tier_id)]
    change_key = _SS_CHANGE_MAP.get(change)
    if change_key and "change_type" in work.columns:
        work = work[work["change_type"].astype(str).str.lower() == change_key]
    return work.reset_index(drop=True)


def _fill_superstar_gaps(portfolios: dict, *, max_web: int = 40) -> dict[str, int]:
    merged = aggregate_all_portfolios(portfolios)
    if merged.empty:
        return {"sector": 0, "web": 0, "web_tried": 0}

    if "sector" not in merged.columns:
        merged["sector"] = ""
    miss_sec = _sector_missing_mask(merged["sector"])
    sector_n = 0
    by_sym: dict[str, pd.Series] = {}
    if miss_sec.any():
        filled = enrich_superstar_classification(merged.loc[miss_sec].copy())
        if not filled.empty and "sector" in filled.columns:
            sector_n = int((~_sector_missing_mask(filled["sector"])).sum())
            for _, r in filled.iterrows():
                sym = safe_str(r.get("symbol")).upper()
                if sym:
                    by_sym[sym] = r
        for _name, data in portfolios.items():
            if not isinstance(data, dict):
                continue
            all_df = data.get("all")
            if not isinstance(all_df, pd.DataFrame) or all_df.empty or not by_sym:
                continue
            work = all_df.copy()
            if "sector" not in work.columns:
                work["sector"] = ""
            changed = False
            for i, row in work.iterrows():
                sym = safe_str(row.get("symbol")).upper()
                src = by_sym.get(sym)
                if src is None:
                    continue
                if not _sector_missing_mask(pd.Series([row.get("sector")])).iloc[0]:
                    continue
                work.at[i, "sector"] = safe_str(src.get("sector")) or "—"
                changed = True
            if changed:
                data["all"] = work
                if "change_type" in work.columns:
                    data["new_picks"] = work[work["change_type"] == "new"].copy()
                    data["increased"] = work[work["change_type"] == "increased"].copy()
                    data["decreased"] = work[work["change_type"] == "decreased"].copy()
                    data["unchanged"] = work[work["change_type"] == "unchanged"].copy()
                data["count"] = len(work)

    tickers = sorted({safe_str(t).upper() for t in merged["symbol"] if safe_str(t)})
    profiles = load_company_profiles_from_db(tickers)
    need_web = [
        t for t in tickers if not sanitize_website((profiles.get(t) or {}).get("website"))
    ][:max_web]
    web_n = 0
    market_map: dict[str, str] = {}
    if "exchange" in merged.columns:
        for _, row in merged.iterrows():
            sym = safe_str(row.get("symbol")).upper()
            if sym and sym not in market_map:
                market_map[sym] = (
                    "BSE" if safe_str(row.get("exchange")).upper() == "BSE" else "NSE"
                )
    for ticker in need_web:
        before = sanitize_website((profiles.get(ticker) or {}).get("website"))
        merge_company_profile({}, ticker, market_map.get(ticker, "NSE"))
        after = load_company_profiles_from_db([ticker]).get(ticker) or {}
        if sanitize_website(after.get("website")) and not before:
            web_n += 1
    return {"sector": sector_n, "web": web_n, "web_tried": len(need_web)}


def _sector_options(merged: pd.DataFrame) -> list[str]:
    if merged.empty or "sector" not in merged.columns:
        return ["All"]
    vals = sorted(
        {
            safe_str(s)
            for s in merged["sector"]
            if safe_str(s) and safe_str(s) != "—"
        }
    )
    return ["All", *vals]


def _portfolio_dict_with_display(df: pd.DataFrame) -> dict[str, pd.DataFrame | str | int]:
    work = _prepare_display_df(df)
    if work.empty or "change_type" not in work.columns:
        from stocks.shared.superstars.holdings import portfolio_dict_from_df

        return portfolio_dict_from_df(work)
    return {
        "all": work,
        "new_picks": work[work["change_type"] == "new"].copy(),
        "increased": work[work["change_type"] == "increased"].copy(),
        "decreased": work[work["change_type"] == "decreased"].copy(),
        "unchanged": work[work["change_type"] == "unchanged"].copy(),
        "count": len(work),
        "error": "",
    }


def _prepare_portfolios_for_display(portfolios: dict) -> None:
    if st.session_state.get(_DISPLAY_READY_KEY) == _CACHE_VERSION:
        return
    for name in list(portfolios.keys()):
        data = portfolios.get(name)
        if not isinstance(data, dict):
            continue
        all_df = data.get("all")
        if not isinstance(all_df, pd.DataFrame) or all_df.empty:
            continue
        if "sector" not in all_df.columns or all_df["sector"].map(_sector_is_missing).all():
            all_df = enrich_superstar_classification(all_df)
        portfolios[name] = _portfolio_dict_with_display(all_df)
    st.session_state[_DISPLAY_READY_KEY] = _CACHE_VERSION


def _ensure_merged_classification(merged: pd.DataFrame) -> pd.DataFrame:
    """Classify + mcap for filter dropdowns and table display."""
    if merged.empty:
        return merged
    work = merged.copy()
    if "sector" not in work.columns or work["sector"].map(_sector_is_missing).all():
        work = enrich_superstar_classification(work)
    if "market_cap_cr" not in work.columns:
        work = _attach_mcap_columns(work)
    return work


def _holdings_tickers() -> set[str]:
    try:
        holdings = load_holdings(seed_if_empty=False)
        if holdings.empty:
            return set()
        return {safe_str(t).upper() for t in holdings["ticker"] if safe_str(t)}
    except Exception:
        return set()


def _display_holdings_table(
    df: pd.DataFrame | None,
    *,
    table_id: str = "",
    holdings_symbols: set[str] | None = None,
    show_investor: bool = False,
    title: str = "SuperStars",
) -> None:
    """Governance Map–style HTML report (interactive table + expand panel)."""
    del holdings_symbols
    if df is None or df.empty:
        st.caption("No holdings.")
        return

    display = _prepare_display_df(df)
    if display.empty:
        st.caption("No holdings.")
        return
    if show_investor and "investor" in df.columns and "investor" not in display.columns:
        display = display.copy()
        if len(display) == len(df):
            display["investor"] = [safe_str(v) for v in df["investor"]]

    embed_html = build_superstars_html(
        display,
        title=title,
        show_investor=show_investor,
        standalone=False,
    )
    key = table_id or ("ss_report_all" if show_investor else "ss_report_one")
    embed_html_iframe(
        embed_html,
        height=superstars_iframe_height(len(display)),
        key=key,
    )


def _persist_portfolio(investor: str, data: dict, fetched_at: str) -> int:
    all_df = data.get("all")
    if isinstance(all_df, pd.DataFrame) and not all_df.empty:
        work = enrich_superstar_classification(all_df.copy())
        return save_superstar_holdings(investor, work, fetched_at=fetched_at)
    return 0


def _refresh_all_portfolios(
    portfolios: dict,
    fetched_at: dict,
) -> tuple[int, str]:
    """Fetch every superstar investor, persist to DB, return (rows_saved, timestamp)."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_saved = 0
    n = len(SUPERSTAR_INVESTORS)
    progress = st.progress(0.0, text="Fetching all superstar portfolios…")

    # Warm caches once — Refresh all uses fast ticker resolve (no Yahoo price checks).
    _load_symbol_cache_from_db()
    company_lookup = _build_company_lookup()
    workers = min(6, max(2, n))
    done = 0

    def _fetch_one(inv_entry: dict) -> tuple[str, dict]:
        name = inv_entry["name"]
        data = load_superstar_portfolio(
            inv_entry, company_lookup=company_lookup, fast=True
        )
        return name, data

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_one, inv_entry): inv_entry["name"]
            for inv_entry in SUPERSTAR_INVESTORS
        }
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                name, data = fut.result()
            except Exception as exc:
                data = {
                    "all": pd.DataFrame(),
                    "new_picks": pd.DataFrame(),
                    "increased": pd.DataFrame(),
                    "decreased": pd.DataFrame(),
                    "unchanged": pd.DataFrame(),
                    "count": 0,
                    "error": str(exc),
                    "entities": [],
                }
            portfolios[name] = data
            fetched_at[name] = ts
            total_saved += _persist_portfolio(name, data, ts)
            done += 1
            progress.progress(
                done / n,
                text=f"Fetched {name} ({done}/{n})…",
            )

    progress.progress(1.0, text="Done")
    progress.empty()
    save_cached_superstar_portfolios(
        portfolios,
        fetched_at_display=ts,
        cache_version=_CACHE_VERSION,
    )
    st.session_state["superstar_from_disk_cache"] = False
    st.session_state["superstar_from_db"] = False
    return total_saved, ts



def _render_investor_section(
    name: str,
    data: dict | None = None,
    *,
    holdings_df: pd.DataFrame | None = None,
    holdings_symbols: set[str],
    sector: str = "All",
    cap_tier_id: str = "all",
    change: str = "All",
    show_investor: bool = False,
) -> None:
    if data and data.get("error"):
        st.error(f"Could not load portfolio: {data['error']}")
        return

    source = holdings_df if holdings_df is not None else (data or {}).get("all")
    if source is None or (isinstance(source, pd.DataFrame) and source.empty):
        st.caption("No holdings for the latest quarter.")
        return

    all_df = _apply_superstar_filters(
        source, sector=sector, cap_tier_id=cap_tier_id, change=change
    )
    if all_df.empty:
        st.caption("No holdings match filters.")
        return

    sort_cols = [c for c in ("holding_value_cr", "holding_percent") if c in all_df.columns]
    if sort_cols:
        all_df = all_df.sort_values(sort_cols, ascending=[False] * len(sort_cols), na_position="last")
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "all"
    _display_holdings_table(
        all_df,
        table_id=f"superstar_all_{slug}",
        holdings_symbols=holdings_symbols,
        show_investor=show_investor,
        title=name if name != "All" else "SuperStars",
    )


def render_superstars() -> None:
    st.markdown("### SuperStars")

    if st.session_state.get("superstar_cache_version") != _CACHE_VERSION:
        st.session_state["superstar_portfolios"] = {}
        st.session_state["superstar_fetched_at"] = {}
        st.session_state["superstar_cache_version"] = _CACHE_VERSION
        st.session_state.pop(_DISPLAY_READY_KEY, None)

    if not isinstance(st.session_state.get("superstar_portfolios"), dict):
        st.session_state["superstar_portfolios"] = {}
    if not isinstance(st.session_state.get("superstar_fetched_at"), dict):
        st.session_state["superstar_fetched_at"] = {}

    investor_names = [entry["name"] for entry in SUPERSTAR_INVESTORS]
    investor_opts = [_SS_ALL, *investor_names]
    portfolios = st.session_state["superstar_portfolios"]
    fetched_at = st.session_state["superstar_fetched_at"]

    loaded_count = _loaded_investor_count(portfolios, investor_names)
    if loaded_count == 0:
        _hydrate_portfolios_from_disk(portfolios, fetched_at)
        loaded_count = _loaded_investor_count(portfolios, investor_names)
    if loaded_count == 0:
        _hydrate_portfolios_from_db(portfolios, fetched_at)
        loaded_count = _loaded_investor_count(portfolios, investor_names)

    if loaded_count:
        _prepare_portfolios_for_display(portfolios)

    merged = (
        _ensure_merged_classification(aggregate_all_portfolios(portfolios))
        if loaded_count
        else pd.DataFrame()
    )

    sector_opts = _sector_options(merged)
    cap_labels = cap_tier_labels()
    if _SS_SECTOR_KEY not in st.session_state or st.session_state[_SS_SECTOR_KEY] not in sector_opts:
        st.session_state[_SS_SECTOR_KEY] = "All"
    if _SS_CAP_KEY not in st.session_state or st.session_state[_SS_CAP_KEY] not in cap_labels:
        st.session_state[_SS_CAP_KEY] = default_cap_tier_label()
    if (
        _SS_INVESTOR_KEY not in st.session_state
        or st.session_state[_SS_INVESTOR_KEY] not in investor_opts
    ):
        st.session_state[_SS_INVESTOR_KEY] = _SS_ALL
    if (
        _SS_CHANGE_KEY not in st.session_state
        or st.session_state[_SS_CHANGE_KEY] not in _SS_CHANGE_OPTS
    ):
        st.session_state[_SS_CHANGE_KEY] = "All"

    # Investor · Sector · Cap · Change · Refresh · Fill
    t1, t2, t3, t4, t5, t6 = st.columns(
        [1.5, 1.1, 0.95, 0.85, 0.65, 0.7], vertical_alignment="bottom"
    )
    with t1:
        investor = st.selectbox("Investor", investor_opts, key=_SS_INVESTOR_KEY)
    with t2:
        sector = st.selectbox("Sector", sector_opts, key=_SS_SECTOR_KEY)
    with t3:
        st.selectbox("Cap", cap_labels, key=_SS_CAP_KEY)
    with t4:
        change = st.selectbox(
            "Change",
            list(_SS_CHANGE_OPTS),
            key=_SS_CHANGE_KEY,
            help="New = first-time holding this quarter (green rows).",
        )
    with t5:
        refresh = st.button("Refresh", type="primary", use_container_width=True)
    with t6:
        fill = st.button(
            "Fill gaps",
            use_container_width=True,
            help="Fill missing Sector from classification DB + fetch Web (screener/Yahoo, up to 40).",
        )

    if refresh:
        total_saved, ts = _refresh_all_portfolios(portfolios, fetched_at)
        fund_counts = sync_all_fund_watchlists()
        st.session_state.pop(_DISPLAY_READY_KEY, None)
        _prepare_portfolios_for_display(portfolios)
        loaded_count = _loaded_investor_count(portfolios, investor_names)
        fund_n = sum(fund_counts.values())
        st.success(
            f"**{loaded_count}** investors · **{total_saved:,}** holdings · {ts}"
            + (f" · watchlists {fund_n}" if fund_n else "")
        )
        merged = _ensure_merged_classification(aggregate_all_portfolios(portfolios))

    if fill and loaded_count:
        with st.spinner("Filling missing sectors + websites…"):
            gap = _fill_superstar_gaps(portfolios, max_web=40)
        st.session_state.pop(_DISPLAY_READY_KEY, None)
        _prepare_portfolios_for_display(portfolios)
        merged = _ensure_merged_classification(aggregate_all_portfolios(portfolios))
        st.success(
            f"Filled **{gap.get('sector', 0)}** sectors · "
            f"**{gap.get('web', 0)}** websites "
            f"(tried {gap.get('web_tried', 0)})"
        )

    if not loaded_count:
        st.info(f"Click **Refresh** to load {len(SUPERSTAR_INVESTORS)} portfolios.")
        return

    cap_tier_id = cap_tier_id_from_label(st.session_state.get(_SS_CAP_KEY) or "")
    holdings_symbols = _holdings_tickers()
    show_all = investor == _SS_ALL

    if show_all:
        source = merged
        count = len(source) if isinstance(source, pd.DataFrame) else 0
        filtered = _apply_superstar_filters(
            source, sector=sector, cap_tier_id=cap_tier_id, change=change
        )
        n_show = len(filtered) if isinstance(filtered, pd.DataFrame) else 0
        bits = [f"**{loaded_count}** investors", f"**{count}** holdings"]
        if sector != "All" or cap_tier_id != "all" or change != "All":
            bits.append(f"**{n_show}** shown")
        if change == "New" and isinstance(source, pd.DataFrame) and "change_type" in source.columns:
            bits.append(f"**{int((source['change_type']=='new').sum())}** new total")
        if fetched_at:
            bits.append(str(max(fetched_at.values())))
        st.caption(" · ".join(bits) + " · click row for detail · Web / SC / TV")
        _render_investor_section(
            _SS_ALL,
            holdings_df=source,
            holdings_symbols=holdings_symbols,
            sector=sector,
            cap_tier_id=cap_tier_id,
            change=change,
            show_investor=True,
        )
        return

    data = portfolios.get(investor, {})
    entry = next((e for e in SUPERSTAR_INVESTORS if e["name"] == investor), {})
    count = int(data.get("count") or 0)
    filtered = _apply_superstar_filters(
        data.get("all"), sector=sector, cap_tier_id=cap_tier_id, change=change
    )
    n_show = len(filtered) if isinstance(filtered, pd.DataFrame) else 0

    bits = [f"**{count}** holdings"]
    if sector != "All" or cap_tier_id != "all" or change != "All":
        bits.append(f"**{n_show}** shown")
    new_n = _df_row_count(data.get("new_picks"))
    if new_n:
        bits.append(f"{new_n} new")
    funds = (entry or {}).get("funds") or []
    if funds:
        bits.append(f"{len(funds)} funds")
    ts_display = fetched_at.get(investor) or (
        max(fetched_at.values()) if fetched_at else ""
    )
    if ts_display:
        bits.append(str(ts_display))
    st.caption(" · ".join(bits) + " · set **Change = New** to see first-time buys")

    _render_investor_section(
        investor,
        data,
        holdings_symbols=holdings_symbols,
        sector=sector,
        cap_tier_id=cap_tier_id,
        change=change,
    )
