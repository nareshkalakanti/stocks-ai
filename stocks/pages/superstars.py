"""SuperStars — tracked ace investor portfolios from Trendlyne."""

from __future__ import annotations

import html
import re
from datetime import datetime

import pandas as pd
import streamlit as st

from stocks.core.config import SUPERSTAR_CACHE_HOURS
from stocks.shared.corp_tags import corp_tags_html
from stocks.shared.portfolio import load_holdings
from stocks.shared.links import attach_research_links, screener_url, tradingview_url
from stocks.dashboards.report_html import embed_html_iframe
from stocks.core.database import save_superstar_holdings, superstar_holdings_db_stats
from stocks.shared.superstars.holdings import (
    aggregate_all_portfolios,
    all_investors_summary,
    enrich_superstar_classification,
    portfolios_from_db,
)
from stocks.shared.superstars.cache import (
    load_cached_superstar_portfolios,
    save_cached_superstar_portfolios,
)
from stocks.shared.superstars.investors import SUPERSTAR_INVESTORS, load_superstar_portfolio
from stocks.core.text_utils import safe_str

_CACHE_VERSION = 13
_DISPLAY_READY_KEY = "superstar_display_ready_v"


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


def _company_cell_html(row: pd.Series) -> str:
    sym = safe_str(row.get("symbol")).upper()
    name = safe_str(row.get("company_name")) or sym or "—"
    exch = safe_str(row.get("exchange") or "NSE").upper()
    sc = row.get("screener_link") or screener_url(
        sym, "BSE" if exch == "BSE" else "NSE", bse_code=row.get("screener_slug")
    )
    tv = row.get("tv_link") or tradingview_url(
        sym, "BSE" if exch == "BSE" else "NSE", prefer_bse=exch == "BSE"
    )
    tags = corp_tags_html(sym)
    exch_note = (
        f' <span class="sub">({html.escape(exch)})</span>' if exch and exch != "NSE" else ""
    )
    return (
        f'<div class="company-cell">'
        f'<div class="company-top">'
        f'<span class="company-name">{html.escape(name)}</span>'
        f'<span class="company-actions">'
        f'<span class="links-inline">'
        f'<a href="{html.escape(sc)}" target="_blank" rel="noopener noreferrer">SC</a>'
        f'<a href="{html.escape(tv)}" target="_blank" rel="noopener noreferrer">TV</a>'
        f"</span></span></div>"
        f'<div class="sub">{html.escape(sym)}{exch_note}</div>'
        f"{tags if tags else ''}"
        f"</div>"
    )


def _prepare_display_df(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    if "screener_link" not in work.columns:
        work = enrich_superstar_classification(work)
        work["ticker"] = work["symbol"]
        work["market"] = work["exchange"].apply(
            lambda x: "BSE" if safe_str(x).upper() == "BSE" else "NSE"
        )
        work = attach_research_links(work)
    if "industry" not in work.columns:
        work["industry"] = work.get("sub_sector", "")
    work["industry"] = work.apply(
        lambda r: safe_str(r.get("industry")) or safe_str(r.get("sub_sector")) or "—",
        axis=1,
    )
    work["sector"] = work["sector"].apply(lambda s: safe_str(s) or "—")
    return work


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
    """Enrich each investor portfolio once (sector, links) — avoids repeat work per table."""
    if st.session_state.get(_DISPLAY_READY_KEY) == _CACHE_VERSION:
        return
    for name in list(portfolios.keys()):
        data = portfolios.get(name)
        if not isinstance(data, dict):
            continue
        all_df = data.get("all")
        if not isinstance(all_df, pd.DataFrame) or all_df.empty:
            continue
        portfolios[name] = _portfolio_dict_with_display(all_df)
    st.session_state[_DISPLAY_READY_KEY] = _CACHE_VERSION


def _change_html(change_display: str, change_type: str) -> str:
    ct = safe_str(change_type).lower()
    if ct == "new" or ct == "increased":
        color = "#16a34a"
        weight = "700" if ct == "new" else "600"
    elif ct == "decreased":
        color = "#dc2626"
        weight = "600"
    else:
        color = "#6b7280"
        weight = "400"
    return (
        f'<span style="color:{color};font-weight:{weight};">'
        f"{html.escape(change_display)}</span>"
    )


def _row_change_class(change_type: str) -> str:
    ct = safe_str(change_type).lower()
    if ct == "new":
        return " change-new"
    if ct == "increased":
        return " change-inc"
    if ct == "decreased":
        return " change-dec"
    return ""


def _holdings_tickers() -> set[str]:
    try:
        holdings = load_holdings(seed_if_empty=False)
        if holdings.empty:
            return set()
        return {safe_str(t).upper() for t in holdings["ticker"] if safe_str(t)}
    except Exception:
        return set()


def _table_height(row_count: int) -> int:
    return min(720, max(120, 56 + row_count * 52))


_SUPERSTARS_REPORT_CSS = """
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #111827;
    margin: 0;
    padding: 0;
    font-size: 13px;
    line-height: 1.45;
  }
  .ss-table-wrap { overflow-x: auto; padding: 0 2px 8px; }
  .ss-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: auto;
    font-size: 13px;
  }
  .ss-table th, .ss-table td {
    padding: 10px 12px;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: middle;
  }
  .ss-table th {
    background: #f9fafb;
    font-weight: 600;
    text-align: left;
    white-space: nowrap;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #6b7280;
  }
  .ss-table th.num, .ss-table td.num {
    text-align: right;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  .ss-table td.text {
    color: #374151;
    max-width: 320px;
    white-space: normal;
    line-height: 1.35;
  }
  .ss-table tbody tr:hover td { background: #f3f4f6; }
  .ss-table tbody tr.change-new td { background: #ecfdf5 !important; }
  .ss-table tbody tr.change-inc td { background: #f0fdf4 !important; }
  .ss-table tbody tr.change-dec td { background: #fef2f2 !important; }
  .ss-table tbody tr.change-new:hover td { background: #d1fae5 !important; }
  .ss-table tbody tr.change-inc:hover td { background: #dcfce7 !important; }
  .ss-table tbody tr.change-dec:hover td { background: #fee2e2 !important; }
  .ss-table tbody tr.holdings-match {
    box-shadow: inset 4px 0 0 #2563eb;
  }
  td.company-td { white-space: normal; min-width: 220px; max-width: 380px; }
  .company-cell { min-width: 0; }
  .company-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }
  .company-name {
    font-weight: 600;
    font-size: 14px;
    line-height: 1.4;
    letter-spacing: -0.01em;
    white-space: normal;
    word-break: break-word;
    flex: 1;
    min-width: 0;
    color: #0f172a;
  }
  .company-actions { display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; }
  .links-inline { display: inline-flex; gap: 4px; flex-shrink: 0; }
  .links-inline a {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    background: #eff6ff;
    color: #1d4ed8;
    text-decoration: none;
    font-size: 10px;
    font-weight: 700;
  }
  .links-inline a:hover { background: #dbeafe; }
  .sub { color: #6b7280; font-size: 11px; margin-top: 2px; }
  .corp-tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px 6px;
    margin-top: 5px;
  }
  .corp-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    line-height: 1.25;
    padding: 3px 8px;
    border-radius: 5px;
    white-space: nowrap;
  }
  .corp-tag-bg { color: #5b21b6; background: #ede9fe; }
  .corp-tag-hold { color: #1d4ed8; background: #dbeafe; }
  .corp-tag-dem { color: #92400e; background: #fef3c7; }
  .corp-tag-spin { color: #0e7490; background: #cffafe; }
  .corp-tag-spec { color: #9d174d; background: #fce7f3; }
</style>
"""


def _wrap_superstars_html(body: str) -> str:
    return (
        "<!DOCTYPE html><html><head>"
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
        f"{_SUPERSTARS_REPORT_CSS}</head><body>{body}</body></html>"
    )


def _embed_superstars_table(table_id: str, thead: str, body_rows: list[str]) -> None:
    if not body_rows:
        st.caption("No rows.")
        return
    body = (
        f'<div class="ss-table-wrap"><table class="ss-table" id="{html.escape(table_id)}">'
        f"<thead><tr>{thead}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></div>"
    )
    embed_html_iframe(_wrap_superstars_html(body), height=_table_height(len(body_rows)))


def _display_holdings_table(
    df: pd.DataFrame | None,
    *,
    table_id: str,
    holdings_symbols: set[str],
) -> None:
    display = _prepare_display_df(df)
    if display.empty:
        st.caption("No holdings.")
        return

    body_rows: list[str] = []
    for _, row in display.iterrows():
        sym = safe_str(row.get("symbol")).upper()
        on_holdings = bool(sym and sym in holdings_symbols)
        classes: list[str] = []
        if on_holdings:
            classes.append("holdings-match")
        change_cls = _row_change_class(safe_str(row.get("change_type")))
        if change_cls:
            classes.append(change_cls.strip())
        row_cls = f' class="{" ".join(classes)}"' if classes else ""

        holding_pct = (
            f'{float(row["holding_percent"]):.2f}%'
            if pd.notna(row.get("holding_percent"))
            else "—"
        )
        body_rows.append(
            "<tr"
            + row_cls
            + ">"
            f'<td class="company-td">{_company_cell_html(row)}</td>'
            f'<td class="text">{html.escape(safe_str(row.get("sector")))}</td>'
            f'<td class="text">{html.escape(safe_str(row.get("industry")))}</td>'
            f'<td class="num">{holding_pct}</td>'
            + f"<td class=\"num\">{_change_html(safe_str(row.get('change_display')), safe_str(row.get('change_type')))}</td>"
            + f'<td class="num">{html.escape(safe_str(row.get("holding_value_display")))}</td>'
            + f'<td class="num">{html.escape(safe_str(row.get("price_display")) or "—")}</td>'
            + "</tr>"
        )

    thead = (
        "<th>Stock</th><th>Sector</th><th>Industry</th>"
        '<th class="num">Holding %</th><th class="num">Qtr Change</th>'
        '<th class="num">Value</th><th class="num">Price</th>'
    )
    _embed_superstars_table(table_id, thead, body_rows)


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
    progress = st.progress(0.0, text="Fetching all superstar portfolios…")
    for i, inv_entry in enumerate(SUPERSTAR_INVESTORS):
        name = inv_entry["name"]
        progress.progress(
            i / len(SUPERSTAR_INVESTORS),
            text=f"Fetching {name} ({i + 1}/{len(SUPERSTAR_INVESTORS)})…",
        )
        portfolios[name] = load_superstar_portfolio(inv_entry)
        fetched_at[name] = ts
        total_saved += _persist_portfolio(name, portfolios[name], ts)
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


def _investor_expander_label(name: str, data: dict) -> str:
    count = int(data.get("count") or 0)
    new_n = _df_row_count(data.get("new_picks"))
    inc_n = _df_row_count(data.get("increased"))
    dec_n = _df_row_count(data.get("decreased"))
    parts = [f"{count} holdings"]
    if new_n:
        parts.append(f"🟢 {new_n} new")
    if inc_n:
        parts.append(f"↑ {inc_n}")
    if dec_n:
        parts.append(f"↓ {dec_n}")
    return f"{name} · {' · '.join(parts)}"


def _render_investor_section(
    name: str,
    data: dict,
    *,
    holdings_symbols: set[str],
) -> None:
    if data.get("error"):
        st.error(f"Could not load portfolio: {data['error']}")
        return

    count = int(data.get("count") or 0)
    if not count:
        st.caption("No holdings for the latest quarter.")
        return

    new_df = data.get("new_picks")
    has_new = isinstance(new_df, pd.DataFrame) and not new_df.empty

    if has_new:
        st.markdown("**Latest picks**")
        _display_holdings_table(
            new_df,
            table_id=f"superstar_new_{re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')}",
            holdings_symbols=holdings_symbols,
        )

    st.markdown("**All holdings**")
    all_df = data.get("all")
    if isinstance(all_df, pd.DataFrame) and not all_df.empty:
        all_df = all_df.sort_values(
            ["holding_value_cr", "holding_percent"],
            ascending=[False, False],
            na_position="last",
        )
    _display_holdings_table(
        all_df,
        table_id=f"superstar_all_{re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')}",
        holdings_symbols=holdings_symbols,
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

    with st.container(border=True):
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        with c1:
            st.caption(
                f"All **{len(SUPERSTAR_INVESTORS)}** tracked investors · "
                f"latest picks and full holdings · "
                f"green = new/increased · red = decreased"
            )
        with c2:
            refresh = st.button(
                "Refresh all",
                type="primary",
                width="stretch",
                help=(
                    f"Fetch all {len(SUPERSTAR_INVESTORS)} investors from Trendlyne "
                    f"and save to database (bypasses {SUPERSTAR_CACHE_HOURS}h cache)"
                ),
            )

    portfolios = st.session_state["superstar_portfolios"]
    fetched_at = st.session_state["superstar_fetched_at"]

    if refresh:
        total_saved, ts = _refresh_all_portfolios(portfolios, fetched_at)
        st.session_state.pop(_DISPLAY_READY_KEY, None)
        stats = superstar_holdings_db_stats()
        st.success(
            f"Loaded **{len(SUPERSTAR_INVESTORS)}** investors · "
            f"**{total_saved:,}** holdings saved to DB · "
            f"**{stats['symbols']:,}** unique tickers · {ts}"
        )

    loaded_count = _loaded_investor_count(portfolios, investor_names)
    if loaded_count == 0:
        _hydrate_portfolios_from_disk(portfolios, fetched_at)
        loaded_count = _loaded_investor_count(portfolios, investor_names)
    if loaded_count == 0:
        _hydrate_portfolios_from_db(portfolios, fetched_at)
        loaded_count = _loaded_investor_count(portfolios, investor_names)

    if not loaded_count:
        st.info(
            f"Click **Refresh all** to fetch every superstar portfolio "
            f"({len(SUPERSTAR_INVESTORS)} investors). "
            f"Data is saved to the database and reused for **{SUPERSTAR_CACHE_HOURS} hours**."
        )
        return

    _prepare_portfolios_for_display(portfolios)
    holdings_symbols = _holdings_tickers()
    merged = aggregate_all_portfolios(portfolios)
    summary = all_investors_summary(merged)
    db_stats = superstar_holdings_db_stats()
    overlap = int(
        merged["symbol"].astype(str).str.upper().isin(holdings_symbols).sum()
    ) if not merged.empty else 0

    ts_display = ""
    if fetched_at:
        ts_display = max(fetched_at.values())
    elif st.session_state.get("superstar_db_fetched_at"):
        ts_display = str(st.session_state["superstar_db_fetched_at"])

    meta_bits = [
        f"**{loaded_count}** investors loaded",
        f"**{summary['unique_symbols']}** unique stocks",
        f"**{summary['new_picks']}** new picks",
        f"**{summary['increased']}** increased",
        f"**{summary['decreased']}** decreased",
    ]
    if overlap:
        meta_bits.append(f"**{overlap}** in your Holdings")
    if ts_display:
        meta_bits.append(f"as of {ts_display}")
    if db_stats.get("rows"):
        meta_bits.append(f"**{db_stats['rows']:,}** rows in DB")
    st.write(" · ".join(meta_bits))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Investors", loaded_count)
    c2.metric("Unique stocks", summary["unique_symbols"])
    c3.metric("New picks", summary["new_picks"])
    c4.metric("Increased", summary["increased"])
    c5.metric("Decreased", summary["decreased"])

    st.divider()

    for entry in SUPERSTAR_INVESTORS:
        name = entry["name"]
        data = portfolios.get(name, {})
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        new_n = _df_row_count(data.get("new_picks"))
        inc_n = _df_row_count(data.get("increased"))
        expanded = bool(new_n or inc_n)
        load_key = f"ss_loaded_{slug}"
        if load_key not in st.session_state:
            st.session_state[load_key] = expanded
        with st.expander(_investor_expander_label(name, data), expanded=expanded):
            if not st.session_state[load_key]:
                if st.button("Show holdings", key=f"ss_show_{slug}", width="stretch"):
                    st.session_state[load_key] = True
                    st.rerun()
            else:
                _render_investor_section(
                    name,
                    data,
                    holdings_symbols=holdings_symbols,
                )
