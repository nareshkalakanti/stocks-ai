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
    common_stocks,
    consensus_momentum,
    enrich_superstar_classification,
)
from stocks.shared.superstars.cache import (
    load_cached_superstar_portfolios,
    save_cached_superstar_portfolios,
)
from stocks.shared.superstars.investors import SUPERSTAR_INVESTORS, load_superstar_portfolio
from stocks.core.text_utils import safe_str

_CACHE_VERSION = 10
ALL_INVESTORS_LABEL = "All Investors"


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


def _df_row_count(value: pd.DataFrame | list | None) -> int:
    if value is None:
        return 0
    if isinstance(value, pd.DataFrame):
        return len(value)
    return len(value)

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
    work = enrich_superstar_classification(df.copy())
    work["ticker"] = work["symbol"]
    work["market"] = work["exchange"].apply(
        lambda x: "BSE" if safe_str(x).upper() == "BSE" else "NSE"
    )
    if "industry" not in work.columns:
        work["industry"] = work.get("sub_sector", "")
    work["industry"] = work.apply(
        lambda r: safe_str(r.get("industry")) or safe_str(r.get("sub_sector")) or "—",
        axis=1,
    )
    work["sector"] = work["sector"].apply(lambda s: safe_str(s) or "—")
    return attach_research_links(work)


def _change_html(change_display: str, change_type: str) -> str:
    if change_type == "new" or change_type == "increased":
        color = "#16a34a"
    elif change_type == "decreased":
        color = "#dc2626"
    else:
        color = "#6b7280"
    return f'<span style="color:{color};">{change_display}</span>'


def _holdings_tickers() -> set[str]:
    try:
        holdings = load_holdings(seed_if_empty=False)
        if holdings.empty:
            return set()
        return {safe_str(t).upper() for t in holdings["ticker"] if safe_str(t)}
    except Exception:
        return set()


def _table_height(row_count: int) -> int:
    return min(900, max(180, 72 + row_count * 58))


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
  .ss-table tbody tr:hover td { background: #f9fafb; }
  .ss-table tbody tr.holdings-match {
    background: #eff6ff !important;
    border-left: 4px solid #2563eb;
  }
  .ss-table tbody tr.holdings-match:hover td { background: #dbeafe !important; }
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
        st.info("No holdings in this category.")
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
    show_investor: bool = False,
) -> None:
    display = _prepare_display_df(df)
    if display.empty:
        st.info("No holdings in this category.")
        return

    body_rows: list[str] = []
    for _, row in display.iterrows():
        sym = safe_str(row.get("symbol")).upper()
        on_holdings = bool(sym and sym in holdings_symbols)
        row_cls = ' class="holdings-match"' if on_holdings else ""
        holding_pct = (
            f'{float(row["holding_percent"]):.2f}%'
            if pd.notna(row.get("holding_percent"))
            else "—"
        )
        investor_cell = ""
        if show_investor:
            investor_cell = (
                f'<td class="text">{html.escape(safe_str(row.get("investor")))}</td>'
            )
        body_rows.append(
            "<tr"
            + row_cls
            + ">"
            f'<td class="company-td">{_company_cell_html(row)}</td>'
            f'<td class="text">{html.escape(safe_str(row.get("sector")))}</td>'
            f'<td class="text">{html.escape(safe_str(row.get("industry")))}</td>'
            + investor_cell
            + f'<td class="num">{holding_pct}</td>'
            + f"<td class=\"num\">{_change_html(safe_str(row.get('change_display')), safe_str(row.get('change_type')))}</td>"
            + f'<td class="num">{html.escape(safe_str(row.get("holding_value_display")))}</td>'
            + f'<td class="num">{html.escape(safe_str(row.get("price_display")) or "—")}</td>'
            + "</tr>"
        )

    investor_th = "<th>Investor</th>" if show_investor else ""
    thead = (
        "<th>Stock</th><th>Sector</th><th>Industry</th>"
        f"{investor_th}"
        '<th class="num">Holding %</th><th class="num">Qtr Change</th>'
        '<th class="num">Value</th><th class="num">Price</th>'
    )
    _embed_superstars_table(table_id, thead, body_rows)


def _display_aggregate_table(
    df: pd.DataFrame | None,
    *,
    table_id: str,
    holdings_symbols: set[str],
    extra_headers: list[tuple[str, str, str]],
) -> None:
    """HTML table for common-stocks / consensus views (extra_headers: label, field, css)."""
    if df is None or df.empty:
        st.info("No data for this view.")
        return

    work = df.copy()
    work["ticker"] = work["symbol"]
    if "exchange" not in work.columns:
        work["exchange"] = "NSE"
    work["market"] = work["exchange"].apply(
        lambda x: "BSE" if safe_str(x).upper() == "BSE" else "NSE"
    )
    work = enrich_superstar_classification(work)
    if "industry" not in work.columns:
        work["industry"] = work.get("sub_sector", "—")
    work["industry"] = work.apply(
        lambda r: safe_str(r.get("industry")) or safe_str(r.get("sub_sector")) or "—",
        axis=1,
    )
    work["sector"] = work["sector"].apply(lambda s: safe_str(s) or "—")
    work = attach_research_links(work)

    body_rows: list[str] = []
    for _, row in work.iterrows():
        sym = safe_str(row.get("symbol")).upper()
        on_holdings = bool(sym and sym in holdings_symbols)
        row_cls = ' class="holdings-match"' if on_holdings else ""
        extra_cells = ""
        for _, field, css in extra_headers:
            raw = row.get(field)
            if css == "num":
                if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                    cell = "—"
                else:
                    cell = html.escape(str(int(raw)) if float(raw) == int(raw) else str(raw))
            else:
                cell = html.escape(safe_str(raw) or "—")
            extra_cells += f'<td class="{css}">{cell}</td>'
        body_rows.append(
            "<tr"
            + row_cls
            + ">"
            f'<td class="company-td">{_company_cell_html(row)}</td>'
            f'<td class="text">{html.escape(safe_str(row.get("sector")))}</td>'
            f'<td class="text">{html.escape(safe_str(row.get("industry") or row.get("sub_sector")))}</td>'
            + extra_cells
            + "</tr>"
        )

    extra_th = "".join(
        f'<th class="{css}">{html.escape(label)}</th>' for label, _, css in extra_headers
    )
    thead = f"<th>Stock</th><th>Sector</th><th>Industry</th>{extra_th}"
    _embed_superstars_table(table_id, thead, body_rows)


def _persist_portfolio(investor: str, data: dict, fetched_at: str) -> int:
    all_df = data.get("all")
    if isinstance(all_df, pd.DataFrame) and not all_df.empty:
        return save_superstar_holdings(investor, all_df, fetched_at=fetched_at)
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
    return total_saved, ts


def _render_all_investors_view(
    merged: pd.DataFrame,
    *,
    holdings_symbols: set[str],
    investor_count: int,
) -> None:
    summary = all_investors_summary(merged)
    overlap = int(
        merged["symbol"].astype(str).str.upper().isin(holdings_symbols).sum()
    )

    st.write(
        f"**{summary['investors']}** investors · "
        f"**{summary['unique_symbols']}** unique stocks · "
        f"**{summary['new_picks']}** new picks · "
        f"**{summary['increased']}** increased"
        + (f" · **{overlap}** rows match your Holdings" if overlap else "")
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Investors", summary["investors"])
    c2.metric("Unique stocks", summary["unique_symbols"])
    c3.metric("New picks", summary["new_picks"])
    c4.metric("Increased", summary["increased"])
    c5.metric("Decreased", summary["decreased"])

    view = st.selectbox(
        "View",
        [
            "New picks",
            "Common stocks",
            "Consensus momentum",
            "Increased",
            "All holdings",
        ],
        key="superstar_all_view",
    )

    if view == "New picks":
        new_df = merged[merged["change_type"].astype(str).str.lower() == "new"].copy()
        if not new_df.empty:
            new_df = new_df.sort_values(["sector", "industry", "investor"])
        _display_holdings_table(
            new_df,
            table_id="superstar_all_new",
            holdings_symbols=holdings_symbols,
            show_investor=True,
        )
        return

    if view == "Common stocks":
        min_inv = st.slider(
            "Minimum investors",
            min_value=2,
            max_value=max(2, investor_count),
            value=2,
            key="superstar_common_min",
        )
        common_df = common_stocks(merged, min_investors=min_inv)
        _display_aggregate_table(
            common_df,
            table_id="superstar_all_common",
            holdings_symbols=holdings_symbols,
            extra_headers=[
                ("Investors", "investor_count", "num"),
                ("New", "new_count", "num"),
                ("Increased", "increased_count", "num"),
                ("Activity", "activity", "text"),
            ],
        )
        return

    if view == "Consensus momentum":
        min_active = st.slider(
            "Minimum active investors",
            min_value=2,
            max_value=max(2, investor_count),
            value=2,
            key="superstar_momentum_min",
        )
        momentum_df = consensus_momentum(merged, min_investors=min_active)
        _display_aggregate_table(
            momentum_df,
            table_id="superstar_all_momentum",
            holdings_symbols=holdings_symbols,
            extra_headers=[
                ("Active", "active_investors", "num"),
                ("New", "new_count", "num"),
                ("Increased", "increased_count", "num"),
                ("Activity", "activity", "text"),
            ],
        )
        return

    if view == "Increased":
        inc_df = merged[merged["change_type"].astype(str).str.lower() == "increased"].copy()
        if not inc_df.empty:
            inc_df = inc_df.sort_values("change_qtr", ascending=False, na_position="last")
        _display_holdings_table(
            inc_df,
            table_id="superstar_all_inc",
            holdings_symbols=holdings_symbols,
            show_investor=True,
        )
        return

    all_sorted = merged.sort_values(["investor", "holding_percent"], ascending=[True, False])
    _display_holdings_table(
        all_sorted,
        table_id="superstar_all_holdings",
        holdings_symbols=holdings_symbols,
        show_investor=True,
    )


def render_superstars() -> None:
    st.markdown("### SuperStars")

    if st.session_state.get("superstar_cache_version") != _CACHE_VERSION:
        st.session_state["superstar_portfolios"] = {}
        st.session_state["superstar_fetched_at"] = {}
        st.session_state["superstar_cache_version"] = _CACHE_VERSION

    if not isinstance(st.session_state.get("superstar_portfolios"), dict):
        st.session_state["superstar_portfolios"] = {}
    if not isinstance(st.session_state.get("superstar_fetched_at"), dict):
        st.session_state["superstar_fetched_at"] = {}

    investor_names = [entry["name"] for entry in SUPERSTAR_INVESTORS]
    names = [ALL_INVESTORS_LABEL] + investor_names
    with st.container(border=True):
        c1, c2 = st.columns([2.5, 1], vertical_alignment="bottom")
        with c1:
            selected = st.selectbox("Investor", names, key="superstar_investor_select")
        with c2:
            refresh = st.button(
                "Refresh",
                type="primary",
                use_container_width=True,
                help=(
                    f"Fetch all {len(SUPERSTAR_INVESTORS)} investors from Trendlyne "
                    f"(bypasses {SUPERSTAR_CACHE_HOURS}h cache)"
                ),
            )

    portfolios = st.session_state["superstar_portfolios"]
    fetched_at = st.session_state["superstar_fetched_at"]

    if refresh:
        total_saved, ts = _refresh_all_portfolios(portfolios, fetched_at)
        stats = superstar_holdings_db_stats()
        st.success(
            f"Loaded **{len(SUPERSTAR_INVESTORS)}** investors · "
            f"**{total_saved:,}** holdings saved · "
            f"**{stats['symbols']:,}** unique tickers · {ts}"
        )

    loaded_count = _loaded_investor_count(portfolios, investor_names)
    if loaded_count == 0:
        _hydrate_portfolios_from_disk(portfolios, fetched_at)
        loaded_count = _loaded_investor_count(portfolios, investor_names)

    if not loaded_count:
        st.info(
            f"Click **Refresh** to fetch every superstar portfolio "
            f"({len(SUPERSTAR_INVESTORS)} investors). "
            f"Data is reused for **{SUPERSTAR_CACHE_HOURS} hours** after each refresh."
        )
        return

    holdings_symbols = _holdings_tickers()

    if selected == ALL_INVESTORS_LABEL:
        merged = aggregate_all_portfolios(portfolios)
        if merged.empty:
            st.warning("No holdings loaded across investors.")
            return
        _render_all_investors_view(
            merged,
            holdings_symbols=holdings_symbols,
            investor_count=loaded_count,
        )
        return

    data = portfolios.get(selected, {})
    if not data:
        st.info(f"No data for **{selected}**. Click **Refresh** to reload.")
        return

    if data.get("error"):
        st.error(f"Could not load portfolio: {data['error']}")
        return

    count = int(data.get("count") or 0)
    if not count:
        st.warning("No holdings found for the latest quarter.")
        return

    overlap = 0
    all_df = data.get("all")
    if isinstance(all_df, pd.DataFrame) and not all_df.empty:
        overlap = int(
            all_df["symbol"].astype(str).str.upper().isin(holdings_symbols).sum()
        )

    st.write(
        f"**{count}** holdings · **{_df_row_count(data.get('new_picks'))}** new · "
        f"**{_df_row_count(data.get('increased'))}** increased"
        + (f" · **{overlap}** in your Holdings" if overlap else "")
    )
    slug = re.sub(r"[^a-z0-9]+", "_", selected.lower()).strip("_")
    view = st.selectbox(
        "View",
        ["Latest picks (NEW)", "Increased", "All holdings", "Decreased"],
        key=f"superstar_one_view_{slug}",
    )

    if view == "Latest picks (NEW)":
        _display_holdings_table(
            data.get("new_picks"),
            table_id=f"superstar_new_{slug}",
            holdings_symbols=holdings_symbols,
        )
    elif view == "Increased":
        inc_df = data.get("increased")
        if isinstance(inc_df, pd.DataFrame) and not inc_df.empty:
            inc_df = inc_df.sort_values("change_qtr", ascending=False, na_position="last")
        _display_holdings_table(
            inc_df,
            table_id=f"superstar_inc_{slug}",
            holdings_symbols=holdings_symbols,
        )
    elif view == "Decreased":
        dec_df = data.get("decreased")
        if isinstance(dec_df, pd.DataFrame) and not dec_df.empty:
            dec_df = dec_df.sort_values("change_qtr", ascending=True, na_position="last")
        _display_holdings_table(
            dec_df,
            table_id=f"superstar_dec_{slug}",
            holdings_symbols=holdings_symbols,
        )
    else:
        _display_holdings_table(
            data.get("all"),
            table_id=f"superstar_all_{slug}",
            holdings_symbols=holdings_symbols,
        )
