import html
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from stocks.shared.corp_tags import corp_tags_html
from stocks.core.config import MIN_MARKET_CAP_CR
from stocks.scans.results_utils import dedupe_recommendations
from stocks.shared.links import attach_research_links, screener_url, tradingview_url
from stocks.core.text_utils import safe_str

_REPORT_CSS = """
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
  .report-wrap { padding: 0 2px 8px; }
  .report-meta {
    color: #6b7280;
    font-size: 12px;
    margin-bottom: 10px;
  }
  table.report {
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    table-layout: fixed;
  }
  table.report th {
    text-align: left;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #374151;
    background: #f9fafb;
    padding: 8px 10px;
    border-bottom: 2px solid #e5e7eb;
  }
  table.report td {
    padding: 10px;
    border-bottom: 1px solid #f0f1f3;
    vertical-align: top;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  table.report tbody tr:nth-child(even) td { background: #fafafa; }
  table.report tbody tr:hover td { background: #f3f4f6; }
  .rank {
    color: #9ca3af;
    font-weight: 600;
    font-size: 12px;
    width: 28px;
  }
  .symbol {
    font-weight: 700;
    font-size: 13px;
    margin-bottom: 5px;
  }
  .links { display: flex; gap: 6px; flex-wrap: wrap; }
  .links a {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    background: #eff6ff;
    color: #1d4ed8;
    text-decoration: none;
    font-size: 11px;
    font-weight: 600;
  }
  .links a:hover { background: #dbeafe; text-decoration: underline; }
  .score {
    font-weight: 700;
    color: #059669;
    white-space: nowrap;
  }
  .price {
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
  }
  .reason { color: #4b5563; }
  .company { font-weight: 500; }
  .muted { color: #6b7280; font-size: 12px; }
  .fund-page { padding: 12px 16px 20px; margin: 0 auto; }
  .fund-title {
    font-size: 18px;
    font-weight: 700;
    margin: 0 0 4px;
    color: #111827;
  }
  .fund-sections {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 12px;
  }
  details.fund-section {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    overflow: hidden;
    background: #fff;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
  }
  details.fund-section[open] {
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
  }
  details.fund-section summary {
    list-style: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 16px;
    font-size: 13px;
    font-weight: 700;
    color: #1f2937;
    background: #f8fafc;
    border-bottom: 1px solid transparent;
    user-select: none;
  }
  details.fund-section summary::-webkit-details-marker { display: none; }
  details.fund-section summary::after {
    content: "▸";
    color: #9ca3af;
    font-size: 14px;
    transition: transform 0.15s ease;
    flex-shrink: 0;
  }
  details.fund-section[open] summary {
    border-bottom-color: #e5e7eb;
    background: #f1f5f9;
  }
  details.fund-section[open] summary::after {
    transform: rotate(90deg);
    color: #6366f1;
  }
  details.fund-section summary:hover { background: #f1f5f9; }
  .fund-section-meta {
    font-size: 11px;
    font-weight: 500;
    color: #6b7280;
    margin-left: auto;
    margin-right: 8px;
  }
  .fund-section-body {
    overflow-x: auto;
    padding: 0;
  }
  .fund-section table.report {
    font-size: 12px;
    font-weight: 600;
    table-layout: auto;
    min-width: 100%;
  }
  .fund-section table.report thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: #f9fafb;
    box-shadow: 0 1px 0 #e5e7eb;
    font-weight: 700;
  }
  .fund-section table.report th,
  .fund-section table.report td {
    padding: 9px 12px;
    vertical-align: middle;
  }
  .fund-section table.report th.col-num,
  .fund-section table.report td.num {
    text-align: right;
    white-space: nowrap;
    font-weight: 700;
  }
  .fund-section table.report th.col-text,
  .fund-section table.report td.col-text {
    font-size: 11px;
    color: #6b7280;
    max-width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .fund-section table.report th.col-rank,
  .fund-section table.report td.rank {
    width: 40px;
    text-align: center;
    color: #9ca3af;
  }
  .fund-section tbody tr.top3 td { background: #f0fdf4; }
  .fund-section tbody tr.top3:hover td { background: #dcfce7; }
  .mom-up { color: #059669; font-weight: 700; }
  .mom-mid { color: #d97706; font-weight: 600; }
  .mom-down { color: #dc2626; font-weight: 700; }
  .stock-cell { min-width: 0; }
  .stock-top {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 2px;
  }
  .stock-top .sym {
    font-weight: 800;
    font-size: 12px;
    color: #111827;
    letter-spacing: 0.02em;
  }
  .links-inline {
    display: inline-flex;
    gap: 4px;
    flex-shrink: 0;
  }
  .links-inline a {
    display: inline-block;
    padding: 1px 6px;
    border-radius: 4px;
    background: #eff6ff;
    color: #1d4ed8;
    text-decoration: none;
    font-size: 10px;
    font-weight: 700;
    line-height: 1.5;
  }
  .links-inline a:hover { background: #dbeafe; }
  .stock-name {
    color: #1d4ed8;
    font-size: 14.5px;
    font-weight: 700;
    line-height: 1.35;
    letter-spacing: -0.02em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 420px;
  }
  .stock-bg {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #7c3aed;
    margin-top: 2px;
    line-height: 1.2;
    white-space: normal;
  }
  .corp-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 8px;
    margin-top: 2px;
  }
  .corp-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    line-height: 1.3;
    padding: 1px 6px;
    border-radius: 4px;
    white-space: normal;
  }
  .corp-tag-bg { color: #5b21b6; background: #ede9fe; }
  .corp-tag-hold { color: #1d4ed8; background: #dbeafe; }
  .corp-tag-sme { color: #9a3412; background: #ffedd5; }
  .corp-tag-dem { color: #92400e; background: #fef3c7; }
  .corp-tag-spin { color: #0e7490; background: #cffafe; }
  .badge-score {
    display: inline-block;
    min-width: 2.5em;
    padding: 2px 6px;
    border-radius: 6px;
    background: #ecfdf5;
    color: #047857;
    font-weight: 700;
    text-align: right;
  }
  .badge-rank {
    display: inline-block;
    min-width: 2.2em;
    padding: 2px 8px;
    border-radius: 999px;
    background: #eef2ff;
    color: #4338ca;
    font-weight: 700;
    text-align: center;
  }
  .badge-yellow {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    background: #fef3c7;
    color: #b45309;
    font-weight: 700;
    text-transform: uppercase;
    font-size: 10px;
  }
  .badge-red {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    background: #fee2e2;
    color: #b91c1c;
    font-weight: 700;
    text-transform: uppercase;
    font-size: 10px;
  }
  .pct-up { color: #059669; font-weight: 700; }
  .pct-down { color: #dc2626; font-weight: 700; }
  .pct-flat { color: #6b7280; }
  .hr-head {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
  }
  .hr-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .hr-stat {
    min-width: 88px;
    padding: 8px 12px;
    border-radius: 10px;
    background: #f8fafc;
    border: 1px solid #e5e7eb;
  }
  .hr-stat-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #6b7280;
    margin-bottom: 2px;
  }
  .hr-stat-value {
    font-size: 18px;
    font-weight: 800;
    color: #111827;
    font-variant-numeric: tabular-nums;
  }
  .hr-method {
    padding: 10px 12px;
    border-radius: 10px;
    background: #f9fafb;
    border: 1px solid #eef0f3;
    color: #4b5563;
    font-size: 12px;
    line-height: 1.5;
    margin-bottom: 12px;
  }
  .hr-method strong { color: #374151; }
  .num { font-variant-numeric: tabular-nums; }
</style>
"""


def _cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    return html.escape(str(value))


def _symbol_cell(ticker: str, sc_link: str, tv_link: str) -> str:
    sym = html.escape(ticker)
    return (
        f'<div class="symbol">{sym}</div>'
        f'<div class="links">'
        f'<a href="{html.escape(sc_link)}" target="_blank" rel="noopener noreferrer" title="screener.in">SC</a>'
        f'<a href="{html.escape(tv_link)}" target="_blank" rel="noopener noreferrer" title="TradingView">TV</a>'
        f"</div>"
    )


def build_recommendations_html(
    results: pd.DataFrame,
    *,
    include_price: bool = True,
    title: str = "Recommended stocks",
    subtitle: str | None = None,
    standalone: bool = False,
    top_n: int = 10,
    full_list: bool = False,
) -> str:
    cap = 0 if full_list else top_n
    df = dedupe_recommendations(results, top_n=cap)
    df = attach_research_links(df) if "tv_link" not in df.columns else df.copy()

    headers = ["#", "Symbol", "Company", "Market", "Sector", "Score", "Reason"]
    if "news_sentiment" in df.columns:
        headers.append("News")
    if include_price and "current_price" in df.columns:
        headers.append("Price (INR)")

    col_widths = {
        "#": "36px",
        "Symbol": "110px",
        "Score": "56px",
        "Market": "64px",
        "Price (INR)": "96px",
        "News": "88px",
    }

    rows_html: list[str] = []
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        sc = row.get("screener_link") or screener_url(ticker)
        tv = row.get("tv_link") or tradingview_url(ticker, market)

        company = _cell(row.get("name"))
        tags_html = corp_tags_html(ticker)
        if tags_html:
            company = f"{company}{tags_html}"
        cells = [
            f'<td class="rank">{rank}</td>',
            f"<td>{_symbol_cell(ticker, sc, tv)}</td>",
            f'<td class="company">{company}</td>',
            f'<td class="muted">{_cell(row.get("market"))}</td>',
            f'<td class="muted">{_cell(row.get("sector"))}</td>',
            f'<td class="score">{_cell(row.get("score"))}</td>',
            f'<td class="reason">{_cell(row.get("reason"))}</td>',
        ]
        if "news_sentiment" in df.columns:
            sentiment = row.get("news_sentiment")
            score = row.get("sentiment_score")
            if sentiment is not None and not (isinstance(sentiment, float) and pd.isna(sentiment)):
                label = _cell(sentiment)
                if score is not None and not (isinstance(score, float) and pd.isna(score)):
                    cells.append(f'<td class="muted">{label} ({float(score):.2f})</td>')
                else:
                    cells.append(f'<td class="muted">{label}</td>')
            else:
                cells.append("<td>—</td>")
        if include_price and "current_price" in df.columns:
            price = row.get("current_price")
            if price is not None and not (isinstance(price, float) and pd.isna(price)):
                cells.append(f'<td class="price">{float(price):,.2f}</td>')
            else:
                cells.append("<td>—</td>")

        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    thead = "".join(
        f'<th style="width:{col_widths.get(h, "auto")}">{html.escape(h)}</th>'
        for h in headers
    )
    meta = ""
    body = (
        f'<div class="report-wrap">'
        f"{meta}"
        f'<table class="report"><thead><tr>{thead}</tr></thead>'
        f"<tbody>{''.join(rows_html)}</tbody></table>"
        f"</div>"
    )

    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def _num_cell(value, *, decimals: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return html.escape(f"{float(value):,.{decimals}f}")
    except (TypeError, ValueError):
        return _cell(value)


def _fund_symbol_cell(
    ticker: str,
    name: str,
    sc_link: str,
    tv_link: str,
    *,
    business_group: str | None = None,
) -> str:
    sym = html.escape(ticker)
    company = html.escape(safe_str(name))
    tags_html = corp_tags_html(ticker, business_group=business_group)
    return (
        f'<div class="stock-cell">'
        f'<div class="stock-top">'
        f'<span class="sym">{sym}</span>'
        f'<span class="links-inline">'
        f'<a href="{html.escape(sc_link)}" target="_blank" rel="noopener noreferrer" title="screener.in">SC</a>'
        f'<a href="{html.escape(tv_link)}" target="_blank" rel="noopener noreferrer" title="TradingView">TV</a>'
        f"</span></div>"
        f'<div class="stock-name" title="{company}">{company or "—"}</div>'
        f"{tags_html}"
        f"</div>"
    )


def _fundamentals_table_rows(
    df: pd.DataFrame,
    *,
    common_cols: list[tuple[str, str, str | int]],
    metric_cols: list[tuple[str, str, str | int]],
    score_col: str | None = None,
) -> str:
    if df.empty:
        return '<tr><td colspan="99" class="muted">No data</td></tr>'

    df = attach_research_links(df) if "tv_link" not in df.columns else df.copy()
    rows: list[str] = []

    def _metric_cell(col: str, val, fmt: str | int) -> str:
        if fmt == "text":
            return f'<td class="muted col-text">{_cell(val)}</td>'
        if score_col and col == score_col and val is not None and not pd.isna(val):
            return (
                f'<td class="num"><span class="badge-score">'
                f"{_num_cell(val, decimals=int(fmt))}</span></td>"
            )
        return f'<td class="num">{_num_cell(val, decimals=int(fmt))}</td>'

    for idx, (_, row) in enumerate(df.iterrows()):
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        sc = row.get("screener_link") or screener_url(ticker)
        tv = row.get("tv_link") or tradingview_url(ticker, market)
        rank = row.get("rank", idx + 1)
        row_class = ' class="top3"' if idx < 3 else ""

        cells = [
            f'<td class="rank">{_cell(rank)}</td>',
            f"<td>{_fund_symbol_cell(ticker, row.get('name'), sc, tv)}</td>",
        ]
        for col, _, fmt in common_cols:
            cells.append(_metric_cell(col, row.get(col), fmt))
        for col, _, fmt in metric_cols:
            cells.append(_metric_cell(col, row.get(col), fmt))
        rows.append(f"<tr{row_class}>{''.join(cells)}</tr>")
    return "".join(rows)


_FUND_COMMON_COLS: list[tuple[str, str, str | int]] = [
    ("sector", "Sector", "text"),
    ("price", "Price (INR)", 2),
    ("market_cap_cr", "Mkt cap (Cr)", 1),
]


def _fundamentals_section(
    title: str,
    df: pd.DataFrame,
    *,
    metric_cols: list[tuple[str, str, str | int]],
    score_col: str | None = None,
    open_section: bool = False,
) -> str:
    count = len(df)
    all_cols = _FUND_COMMON_COLS + metric_cols
    headers: list[tuple[str, str]] = [("#", "col-rank"), ("Stock", "")]
    for _, label, fmt in all_cols:
        cls = "col-text" if fmt == "text" else "col-num"
        headers.append((label, cls))
    thead = "".join(
        f'<th class="{cls}">{html.escape(label)}</th>' for label, cls in headers
    )
    tbody = _fundamentals_table_rows(
        df,
        common_cols=_FUND_COMMON_COLS,
        metric_cols=metric_cols,
        score_col=score_col,
    )
    open_attr = " open" if open_section else ""
    return (
        f'<details class="fund-section"{open_attr}>'
        f'<summary>'
        f"<span>{html.escape(title)}</span>"
        f'<span class="fund-section-meta">{count} stocks</span>'
        f"</summary>"
        f'<div class="fund-section-body">'
        f'<table class="report"><thead><tr>{thead}</tr></thead>'
        f"<tbody>{tbody}</tbody></table>"
        f"</div></details>"
    )


def build_fundamentals_html(
    *,
    roce_df: pd.DataFrame,
    composite_df: pd.DataFrame,
    value_df: pd.DataFrame,
    title: str = "Fundamentals rank",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    sections = (
        _fundamentals_section(
            "Ranked by 50-50% weightage",
            composite_df,
            metric_cols=[
                ("composite_score", "Score", 1),
                ("roce_pct", "ROCE %", 2),
                ("ev_ebitda", "EV/EBITDA", 2),
            ],
            score_col="composite_score",
            open_section=True,
        ),
        _fundamentals_section(
            "Ranked by higher ROCE (strength)",
            roce_df,
            metric_cols=[("roce_pct", "ROCE %", 2), ("debt_to_equity", "D/E", 2)],
        ),
        _fundamentals_section(
            "Ranked by lower EV/EBITDA (valuation)",
            value_df,
            metric_cols=[("ev_ebitda", "EV/EBITDA", 2)],
        ),
    )
    meta = ""
    body = (
        f'<div class="fund-page">'
        f'<h1 class="fund-title">{html.escape(title)}</h1>'
        f"{meta}"
        f'<div class="fund-sections">{"".join(sections)}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def fundamentals_iframe_height(row_count: int) -> int:
    """Collapsed accordion headers + one open section."""
    return min(1200, max(480, 320 + min(row_count, 40) * 14))


_PEAD1_STOCK_COLS: list[tuple[str, str, str | int]] = [
    ("sector", "Sector", "text"),
    ("quarter_end", "Quarter", "text"),
    ("rev_jump", "Rev×", 2),
    ("op_jump", "Op×", 2),
    ("eps_jump", "EPS×", 2),
    ("opm_pct", "OPM%", 1),
    ("opm_room_pp", "Room pp", 1),
    ("gap_pct", "Gap%", 1),
    ("vol_ratio", "Vol×", 2),
    ("score", "Score", 2),
]


def _metric_table_rows(
    df: pd.DataFrame,
    *,
    metric_cols: list[tuple[str, str, str | int]],
) -> str:
    if df.empty:
        return '<tr><td colspan="99" class="muted">No data</td></tr>'

    df = attach_research_links(df) if "tv_link" not in df.columns else df.copy()
    rows: list[str] = []

    for idx, (_, row) in enumerate(df.iterrows()):
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        sc = row.get("screener_link") or screener_url(ticker, market)
        tv = row.get("tv_link") or tradingview_url(ticker, market)
        row_class = ' class="top3"' if idx < 3 else ""

        cells = [
            f'<td class="rank">{idx + 1}</td>',
            f"<td>{_fund_symbol_cell(ticker, row.get('name'), sc, tv)}</td>",
        ]
        for col, _, fmt in metric_cols:
            val = row.get(col)
            if col in ("quarter_end", "sector"):
                text = _format_date(val) if col == "quarter_end" else _cell(val)
                cells.append(f'<td class="muted col-text">{text}</td>')
            elif fmt == "text":
                cells.append(f'<td class="muted col-text">{_cell(val)}</td>')
            elif col in ("score", "criteria_score") and val is not None and not pd.isna(val):
                label = f"{int(val)}/4" if col == "criteria_score" else _num_cell(val, decimals=int(fmt))
                cells.append(
                    f'<td class="num"><span class="badge-score">{label}</span></td>'
                )
            else:
                cells.append(f'<td class="num">{_num_cell(val, decimals=int(fmt))}</td>')
        rows.append(f"<tr{row_class}>{''.join(cells)}</tr>")
    return "".join(rows)


def _metric_section(
    title: str,
    df: pd.DataFrame,
    *,
    metric_cols: list[tuple[str, str, str | int]],
    open_section: bool = False,
) -> str:
    headers: list[tuple[str, str]] = [("#", "col-rank"), ("Stock", "")]
    for _, label, fmt in metric_cols:
        cls = "col-text" if fmt == "text" else "col-num"
        headers.append((label, cls))
    thead = "".join(
        f'<th class="{cls}">{html.escape(label)}</th>' for label, cls in headers
    )
    tbody = _metric_table_rows(df, metric_cols=metric_cols)
    open_attr = " open" if open_section else ""
    return (
        f'<details class="fund-section"{open_attr}>'
        f"<summary>"
        f"<span>{html.escape(title)}</span>"
        f'<span class="fund-section-meta">{len(df)} stocks</span>'
        f"</summary>"
        f'<div class="fund-section-body">'
        f'<table class="report"><thead><tr>{thead}</tr></thead>'
        f"<tbody>{tbody}</tbody></table>"
        f"</div></details>"
    )


_PEAD_STOCK_COLS: list[tuple[str, str, str | int]] = [
    ("sector", "Sector", "text"),
    ("profit_streak_q", "Streak", "text"),
    ("quarter_end", "Quarter", "text"),
    ("yoy_sales_pct", "YoY sales", 1),
    ("yoy_sales_trend", "YoY trend", "text"),
    ("opm_pct", "OPM%", 1),
    ("opm_trend", "OPM trend", "text"),
    ("eps", "EPS", 2),
    ("price", "Price", 2),
    ("upside_pct", "Upside%", 1),
    ("price_potential", "P pot.", 2),
    ("score", "Score", 1),
    ("cwip_cr", "CWIP Cr", 1),
    ("cwip_qoq_pct", "CWIP QoQ", 1),
    ("cwip_yoy_pct", "CWIP YoY", 1),
]


def _format_date(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return _cell(value)


def _pead_table_rows(
    df: pd.DataFrame,
    *,
    metric_cols: list[tuple[str, str, str | int]] | None = None,
) -> str:
    if df.empty:
        return '<tr><td colspan="99" class="muted">No data</td></tr>'

    cols = _PEAD_STOCK_COLS if metric_cols is None else metric_cols
    df = attach_research_links(df) if "tv_link" not in df.columns else df.copy()
    rows: list[str] = []

    def _metric_cell(col: str, val, fmt: str | int) -> str:
        if col in ("quarter_end", "result_date"):
            return f'<td class="muted col-text">{_format_date(val)}</td>'
        if fmt == "text":
            return f'<td class="muted col-text">{_cell(val)}</td>'
        if col == "score" and val is not None and not pd.isna(val):
            return (
                f'<td class="num"><span class="badge-score">'
                f"{_num_cell(val, decimals=int(fmt))}</span></td>"
            )
        if col == "upside_pct" and val is not None and not pd.isna(val) and float(val) > 0:
            return (
                f'<td class="num"><span class="pct-up">'
                f"{_num_cell(val, decimals=int(fmt))}%</span></td>"
            )
        return f'<td class="num">{_num_cell(val, decimals=int(fmt))}</td>'

    for idx, (_, row) in enumerate(df.iterrows()):
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        sc = row.get("screener_link") or screener_url(ticker, market)
        tv = row.get("tv_link") or tradingview_url(ticker, market)
        row_class = ' class="top3"' if idx < 3 else ""

        cells = [
            f'<td class="rank">{idx + 1}</td>',
            f"<td>{_fund_symbol_cell(ticker, row.get('name'), sc, tv)}</td>",
        ]
        for col, _, fmt in cols:
            cells.append(_metric_cell(col, row.get(col), fmt))
        rows.append(f"<tr{row_class}>{''.join(cells)}</tr>")
    return "".join(rows)


def _pead_section(
    title: str,
    df: pd.DataFrame,
    *,
    open_section: bool = False,
) -> str:
    headers: list[tuple[str, str]] = [("#", "col-rank"), ("Stock", "")]
    for _, label, fmt in _PEAD_STOCK_COLS:
        cls = "col-text" if fmt == "text" else "col-num"
        headers.append((label, cls))
    thead = "".join(
        f'<th class="{cls}">{html.escape(label)}</th>' for label, cls in headers
    )
    tbody = _pead_table_rows(df)
    open_attr = " open" if open_section else ""
    return (
        f'<details class="fund-section"{open_attr}>'
        f"<summary>"
        f"<span>{html.escape(title)}</span>"
        f'<span class="fund-section-meta">{len(df)} stocks</span>'
        f"</summary>"
        f'<div class="fund-section-body">'
        f'<table class="report"><thead><tr>{thead}</tr></thead>'
        f"<tbody>{tbody}</tbody></table>"
        f"</div></details>"
    )


def _pead_summary_section(buy: pd.DataFrame, fundamental: pd.DataFrame) -> str:
    total = len(buy) + len(fundamental)
    if total == 0:
        body = '<p class="muted">No candidates matched the PEAD 1 screen.</p>'
    else:
        body = (
            f'<div class="hr-method">'
            f"<strong>{len(buy)}</strong> buy (gap + volume) · "
            f"<strong>{len(fundamental)}</strong> fundamental pass awaiting price · "
            f"actual earnings surprise · rev/op/EPS burst · margin improving · "
            f"fresh Q1–Q2 only"
            f"</div>"
        )
    return (
        f'<details class="fund-section" open>'
        f"<summary><span>Screen rules — Earnings Explosion</span></summary>"
        f'<div class="fund-section-body">{body}</div>'
        f"</details>"
    )


def build_pead_html(
    *,
    buy_df: pd.DataFrame | None = None,
    fundamental_df: pd.DataFrame | None = None,
    candidates_df: pd.DataFrame | None = None,
    title: str = "PEAD 1 — Earnings Explosion",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    buy = buy_df if buy_df is not None else pd.DataFrame()
    fundamental = fundamental_df if fundamental_df is not None else pd.DataFrame()
    if candidates_df is not None and not candidates_df.empty and buy.empty and fundamental.empty:
        if "signal" in candidates_df.columns:
            buy = candidates_df[candidates_df["signal"] == "EARNINGS_BUY"].copy()
            fundamental = candidates_df[candidates_df["signal"] == "EARNINGS_FUNDAMENTAL"].copy()
        else:
            buy = candidates_df.copy()

    sections = (
        _metric_section(
            "Buy — fundamentals + gap up on volume",
            buy,
            metric_cols=_PEAD1_STOCK_COLS,
            open_section=True,
        ),
        _metric_section(
            "Fundamental pass — awaiting price confirmation",
            fundamental,
            metric_cols=_PEAD1_STOCK_COLS,
        ),
        _pead_summary_section(buy, fundamental),
    )
    meta = ""
    body = (
        f'<div class="fund-page">'
        f'<h1 class="fund-title">{html.escape(title)}</h1>'
        f"{meta}"
        f'<div class="fund-sections">{"".join(sections)}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def pead_iframe_height(row_count: int) -> int:
    return min(1200, max(480, 320 + min(row_count, 40) * 14))


_CWIP_STOCK_COLS: list[tuple[str, str, str | int]] = [
    ("sector", "Sector", "text"),
    ("quarter_end", "Quarter", "text"),
    ("market_cap_cr", "Mkt cap Cr", 1),
    ("cwip_cr", "CWIP Cr", 1),
    ("cwip_qoq_pct", "CWIP QoQ%", 1),
    ("cwip_yoy_pct", "CWIP YoY%", 1),
    ("cwip_note", "Note", "text"),
]


def build_cwip_html(
    *,
    clean_df: pd.DataFrame,
    rising_df: pd.DataFrame | None = None,
    no_cwip_data: int = 0,
    title: str = "CWIP — Pass only",
    subtitle: str | None = None,
    standalone: bool = True,
    pass_only: bool = True,
) -> str:
    rising_count = len(rising_df) if rising_df is not None else 0
    summary_body = (
        f'<div class="hr-method">'
        f"<strong>{len(clean_df)}</strong> CWIP pass (falling) · "
        f"<strong>{rising_count:,}</strong> excluded (flat/rising) · "
        f"<strong>{no_cwip_data:,}</strong> without CWIP line · "
        f"strict: must fall QoQ + YoY when available · no rise in last 3 quarters"
        f"</div>"
    )
    sections: list[str] = [
        _metric_section(
            "CWIP pass — falling",
            clean_df,
            metric_cols=_CWIP_STOCK_COLS,
            open_section=True,
        ),
    ]
    if not pass_only and rising_df is not None and not rising_df.empty:
        sections.append(
            _metric_section(
                "CWIP flat or rising — avoid",
                rising_df,
                metric_cols=_CWIP_STOCK_COLS,
            )
        )
    sections.append(
        (
            f'<details class="fund-section" open>'
            f"<summary><span>Screen rules</span></summary>"
            f'<div class="fund-section-body">{summary_body}</div>'
            f"</details>"
        )
    )
    meta = ""
    body = (
        f'<div class="fund-page">'
        f'<h1 class="fund-title">{html.escape(title)}</h1>'
        f"{meta}"
        f'<div class="fund-sections">{"".join(sections)}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def cwip_iframe_height(row_count: int) -> int:
    return min(1200, max(480, 360 + min(row_count, 50) * 12))


_VALUATION_STOCK_COLS: list[tuple[str, str, str | int]] = [
    ("sector", "Sector", "text"),
    ("price", "Now ₹", 2),
    ("buy_headroom_pct", "Headroom %", 1),
    ("criteria_score", "Pass 3/3", 0),
    ("pb", "P/B", 2),
    ("pb_avg_5y", "P/B 5Y", 2),
    ("ps", "P/S", 2),
    ("ps_avg_5y", "P/S 5Y", 2),
    ("pcf", "P/CF", 2),
    ("pcf_avg_5y", "P/CF 5Y", 2),
    ("market_cap_cr", "Mkt cap Cr", 1),
]


def build_valuation_formula_html(
    *,
    candidates_df: pd.DataFrame,
    pass_count: int = 0,
    scanned: int = 0,
    title: str = "Valuation Formula",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    summary_body = (
        f'<div class="hr-method">'
        f"<strong>{pass_count}</strong> pass all 3 rules · "
        f"<strong>{len(candidates_df)}</strong> with data · "
        f"<strong>{scanned:,}</strong> scanned · "
        f"P/B &lt; 5Y avg · P/S &lt; 5Y avg · P/CF &lt; 5Y avg"
        f"</div>"
    )
    sections = (
        _metric_section(
            "Valuation — candidates",
            candidates_df,
            metric_cols=_VALUATION_STOCK_COLS,
            open_section=True,
        ),
        (
            f'<details class="fund-section" open>'
            f"<summary><span>Formula rules</span></summary>"
            f'<div class="fund-section-body">{summary_body}</div>'
            f"</details>"
        ),
    )
    meta = ""
    body = (
        f'<div class="fund-page">'
        f'<h1 class="fund-title">{html.escape(title)}</h1>'
        f"{meta}"
        f'<div class="fund-sections">{"".join(sections)}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def valuation_formula_iframe_height(row_count: int) -> int:
    return min(1200, max(480, 320 + min(row_count, 40) * 14))


_ROCE_EV_STOCK_COLS: list[tuple[str, str, str | int]] = [
    ("sector", "Sector", "text"),
    ("composite_score", "Score", 1),
    ("roce_pct", "ROCE %", 2),
    ("ev_ebitda", "EV/EBITDA", 2),
    ("debt_to_equity", "D/E", 2),
    ("market_cap_cr", "Mkt cap Cr", 1),
    ("price", "Price", 2),
]


def build_roce_ev_html(
    *,
    pass_df: pd.DataFrame,
    min_roce_pct: float,
    max_ev_ebitda: float,
    scored: int = 0,
    roce_only: int = 0,
    value_only: int = 0,
    title: str = "ROCE + EV/EBITDA",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    summary_body = (
        f'<div class="hr-method">'
        f"<strong>Pass</strong> = ROCE &ge; {min_roce_pct:.1f}% "
        f"<strong>and</strong> EV/EBITDA &le; {max_ev_ebitda:.1f} · "
        f"ranked by <strong>50/50 composite</strong> "
        f"(higher ROCE percentile + lower EV/EBITDA percentile) · "
        f"<strong>{scored:,}</strong> with both metrics · "
        f"<strong>{roce_only:,}</strong> ROCE-only · "
        f"<strong>{value_only:,}</strong> value-only"
        f"</div>"
    )
    sections = (
        _metric_section(
            f"Pass — ROCE ≥ {min_roce_pct:.0f}% · EV/EBITDA ≤ {max_ev_ebitda:.0f}",
            pass_df,
            metric_cols=_ROCE_EV_STOCK_COLS,
            open_section=True,
        ),
        (
            f'<details class="fund-section" open>'
            f"<summary><span>Screen rules</span></summary>"
            f'<div class="fund-section-body">{summary_body}</div>'
            f"</details>"
        ),
    )
    meta = ""
    body = (
        f'<div class="fund-page">'
        f'<h1 class="fund-title">{html.escape(title)}</h1>'
        f"{meta}"
        f'<div class="fund-sections">{"".join(sections)}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def roce_ev_iframe_height(row_count: int) -> int:
    return min(1200, max(480, 320 + min(row_count, 40) * 14))


_EARNINGS_STOCK_COLS: list[tuple[str, str, str | int]] = [
    ("sector", "Sector", "text"),
    ("quarter_end", "Quarter", "text"),
    ("rev_jump", "Rev×", 2),
    ("op_jump", "Op×", 2),
    ("eps_jump", "EPS×", 2),
    ("opm_pct", "OPM%", 1),
    ("opm_room_pp", "Room pp", 1),
    ("gap_pct", "Gap%", 1),
    ("vol_ratio", "Vol×", 2),
    ("score", "Score", 2),
]


def _earnings_table_rows(df: pd.DataFrame) -> str:
    if df.empty:
        return '<tr><td colspan="99" class="muted">No data</td></tr>'

    df = attach_research_links(df) if "tv_link" not in df.columns else df.copy()
    rows: list[str] = []

    for idx, (_, row) in enumerate(df.iterrows()):
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        sc = row.get("screener_link") or screener_url(ticker, market)
        tv = row.get("tv_link") or tradingview_url(ticker, market)
        row_class = ' class="top3"' if idx < 3 else ""

        cells = [
            f'<td class="rank">{idx + 1}</td>',
            f"<td>{_fund_symbol_cell(ticker, row.get('name'), sc, tv)}</td>",
        ]
        for col, _, fmt in _EARNINGS_STOCK_COLS:
            val = row.get(col)
            if col in ("quarter_end", "sector"):
                text = _format_date(val) if col == "quarter_end" else _cell(val)
                cells.append(f'<td class="muted col-text">{text}</td>')
            elif fmt == "text":
                cells.append(f'<td class="muted col-text">{_cell(val)}</td>')
            elif col == "score":
                cells.append(
                    f'<td class="num"><span class="badge-score">'
                    f"{_num_cell(val, decimals=int(fmt))}</span></td>"
                )
            else:
                cells.append(f'<td class="num">{_num_cell(val, decimals=int(fmt))}</td>')
        rows.append(f"<tr{row_class}>{''.join(cells)}</tr>")
    return "".join(rows)


def _earnings_section(title: str, df: pd.DataFrame, *, open_section: bool = False) -> str:
    headers: list[tuple[str, str]] = [("#", "col-rank"), ("Stock", "")]
    for _, label, fmt in _EARNINGS_STOCK_COLS:
        cls = "col-text" if fmt == "text" else "col-num"
        headers.append((label, cls))
    thead = "".join(
        f'<th class="{cls}">{html.escape(label)}</th>' for label, cls in headers
    )
    tbody = _earnings_table_rows(df)
    open_attr = " open" if open_section else ""
    return (
        f'<details class="fund-section"{open_attr}>'
        f"<summary>"
        f"<span>{html.escape(title)}</span>"
        f'<span class="fund-section-meta">{len(df)} stocks</span>'
        f"</summary>"
        f'<div class="fund-section-body">'
        f'<table class="report"><thead><tr>{thead}</tr></thead>'
        f"<tbody>{tbody}</tbody></table>"
        f"</div></details>"
    )


def build_earnings_html(
    *,
    buy_df: pd.DataFrame,
    fundamental_df: pd.DataFrame,
    title: str = "Earnings Explosion",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    sections = (
        _earnings_section(
            "Buy — fundamentals + gap up on volume",
            buy_df,
            open_section=True,
        ),
        _earnings_section(
            "Fundamental pass — awaiting price confirmation",
            fundamental_df,
        ),
    )
    meta = ""
    body = (
        f'<div class="fund-page">'
        f'<h1 class="fund-title">{html.escape(title)}</h1>'
        f"{meta}"
        f'<div class="fund-sections">{"".join(sections)}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def earnings_iframe_height(row_count: int) -> int:
    return min(1200, max(480, 320 + min(row_count, 40) * 14))


_HOLDINGS_COLS: list[tuple[str, str, str | int]] = [
    ("current_price", "Price", 2),
    ("chg_from_snapshot_pct", "Δ snap %", "pct"),
    ("industry", "Industry", "text"),
    ("sector", "Sector", "text"),
]


_HOLDINGS_INLINE_NEWS_CSS = """
<style>
  .hold-news-cell { min-width: 200px; max-width: 420px; vertical-align: top; }
  details.hold-news-drop { font-size: 12px; }
  details.hold-news-drop summary {
    list-style: none;
    cursor: pointer;
    display: flex;
    align-items: flex-start;
    gap: 8px;
    color: #374151;
    line-height: 1.45;
  }
  details.hold-news-drop summary::-webkit-details-marker { display: none; }
  details.hold-news-drop summary::after {
    content: "▾";
    margin-left: auto;
    color: #9ca3af;
    font-size: 10px;
    flex-shrink: 0;
    padding-top: 2px;
  }
  details.hold-news-drop[open] summary::after { content: "▴"; }
  .hold-news-sum {
    flex: 1;
    min-width: 0;
    font-weight: 500;
    color: #1f2937;
  }
  .hold-news-n {
    font-size: 10px;
    font-weight: 700;
    color: #6b7280;
    background: #e5e7eb;
    padding: 1px 6px;
    border-radius: 4px;
    flex-shrink: 0;
  }
  .hold-news-items { margin-top: 8px; padding-top: 8px; border-top: 1px solid #f0f1f3; }
  .hold-news-items .news-item { padding: 6px 0; border-bottom: 1px solid #f9fafb; }
  .hold-news-items .news-item:last-child { border-bottom: none; }
  .hold-news-items .news-link { font-size: 12px; color: #1d4ed8; text-decoration: none; }
  .hold-news-items .news-link:hover { text-decoration: underline; }
  .hold-news-items .news-when { font-size: 10px; color: #9ca3af; }
  .hold-news-items .news-item-top { display: flex; gap: 6px; align-items: center; margin-bottom: 3px; }
  .hold-news-items .news-tag {
    font-size: 9px; font-weight: 700; text-transform: uppercase;
    color: #047857; background: #d1fae5; padding: 1px 5px; border-radius: 3px;
  }
</style>
"""


def _news_map_from_feed(feed: list[dict] | None) -> dict[str, list[dict]]:
    if not feed:
        return {}
    out: dict[str, list[dict]] = {}
    for ticker, items in _group_news_by_ticker(feed):
        valid = [
            item
            for item in items
            if safe_str(item.get("title")) and safe_str(item.get("url"))
        ]
        if valid:
            out[ticker] = valid
    return out


def _holdings_news_cell(items: list[dict] | None) -> str:
    if not items:
        return '<td class="hold-news-cell muted">—</td>'

    latest = items[0]
    preview_when = _format_news_when(safe_str(latest.get("published")))
    preview_title = _truncate(safe_str(latest.get("title")), 64)
    preview = f"{preview_when} — {preview_title}" if preview_when != "—" else preview_title

    item_html: list[str] = []
    for idx, item in enumerate(items):
        title = html.escape(safe_str(item.get("title")))
        url = html.escape(safe_str(item.get("url")))
        when = html.escape(_format_news_when(safe_str(item.get("published"))))
        tag = '<span class="news-tag">Latest</span>' if idx == 0 else ""
        item_html.append(
            '<div class="news-item">'
            f'<div class="news-item-top">{tag}<span class="news-when">{when}</span></div>'
            f'<a class="news-link" href="{url}" target="_blank" rel="noopener noreferrer">'
            f"{title}</a></div>"
        )

    return (
        '<td class="hold-news-cell">'
        f'<details class="hold-news-drop"><summary>'
        f'<span class="hold-news-sum">{html.escape(preview)}</span>'
        f'<span class="hold-news-n">{len(items)}</span>'
        f"</summary>"
        f'<div class="hold-news-items">{"".join(item_html)}</div>'
        f"</details></td>"
    )


def _momentum_cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return '<td class="num muted">—</td>'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return '<td class="num muted">—</td>'
    if -5 <= v <= 5:
        cls = "mom-mid"
    elif v > 5:
        cls = "mom-up"
    else:
        cls = "mom-down"
    return f'<td class="num"><span class="{cls}">{html.escape(f"{v:.2f}%")}</span></td>'


def _holdings_table_rows(
    df: pd.DataFrame,
    *,
    news_map: dict[str, list[dict]] | None = None,
    include_sentiment: bool = False,
) -> str:
    if df.empty:
        return '<tr><td colspan="99" class="muted">No data</td></tr>'

    df = attach_research_links(df) if "tv_link" not in df.columns else df.copy()
    rows: list[str] = []
    show_news = news_map is not None

    for idx, (_, row) in enumerate(df.iterrows()):
        ticker = safe_str(row.get("ticker"))
        sym = ticker.upper()
        market = safe_str(row.get("market")) or None
        sc = row.get("screener_link") or screener_url(ticker, market)
        tv = row.get("tv_link") or tradingview_url(ticker, market)
        rank_val = row.get("momentum_rank")
        if rank_val is not None and not (isinstance(rank_val, float) and pd.isna(rank_val)):
            rank_n = int(rank_val)
        else:
            rank_n = idx + 1
        row_class = ' class="top3"' if rank_n <= 3 else ""

        cells = [
            f'<td class="rank">{rank_n}</td>',
            f"<td>{_fund_symbol_cell(ticker, row.get('name'), sc, tv)}</td>",
        ]
        for col, _, fmt in _HOLDINGS_COLS:
            val = row.get(col)
            if col == "current_price" and (
                val is None or (isinstance(val, float) and pd.isna(val))
            ):
                val = row.get("price")
            if fmt == "text":
                cells.append(f'<td class="muted col-text">{_cell(val)}</td>')
            elif fmt == "mom":
                cells.append(_momentum_cell(val))
            elif fmt == "pct":
                cells.append(_momentum_cell(val))
            else:
                cells.append(f'<td class="num">{_num_cell(val, decimals=int(fmt))}</td>')

        if include_sentiment:
            val = row.get("news_sentiment")
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                score = row.get("sentiment_score")
                label = _cell(val)
                if score is not None and not (isinstance(score, float) and pd.isna(score)):
                    cells.append(
                        f'<td class="muted col-text">{label} ({float(score):.2f})</td>'
                    )
                else:
                    cells.append(f'<td class="muted col-text">{label}</td>')
            else:
                cells.append('<td class="muted col-text">—</td>')

        if show_news:
            cells.append(_holdings_news_cell((news_map or {}).get(sym)))

        rows.append(f"<tr{row_class}>{''.join(cells)}</tr>")
    return "".join(rows)


def build_holdings_html(
    holdings_df: pd.DataFrame,
    *,
    title: str = "Holdings",
    subtitle: str | None = None,
    news_feed: list[dict] | None = None,
    standalone: bool = True,
) -> str:
    del subtitle
    if holdings_df.empty:
        df = holdings_df
    else:
        sort_cols = [c for c in ("name", "ticker") if c in holdings_df.columns]
        df = (
            holdings_df.sort_values(sort_cols, ascending=True, na_position="last")
            .reset_index(drop=True)
            if sort_cols
            else holdings_df.reset_index(drop=True)
        )
    show_news = news_feed is not None
    news_map = _news_map_from_feed(news_feed) if show_news else None
    has_sentiment = (
        not df.empty
        and "news_sentiment" in df.columns
        and df["news_sentiment"].notna().any()
    )

    headers: list[tuple[str, str]] = [("#", "col-rank"), ("Stock", "")]
    for _, label, fmt in _HOLDINGS_COLS:
        cls = "col-text" if fmt == "text" else "col-num"
        headers.append((label, cls))
    if has_sentiment:
        headers.append(("Sentiment", "col-text"))
    if show_news:
        headers.append(("News", "col-text"))

    thead = "".join(
        f'<th class="{cls}">{html.escape(label)}</th>' for label, cls in headers
    )
    tbody = _holdings_table_rows(
        df,
        news_map=news_map if show_news else None,
        include_sentiment=has_sentiment,
    )
    priced = int(df["current_price"].notna().sum()) if "current_price" in df.columns else len(df)
    body = (
        f'<div class="fund-page">'
        f'<div class="hr-head">'
        f"<div><h1 class=\"fund-title\">{html.escape(title)}</h1></div>"
        f'<div class="hr-stats">'
        f'<div class="hr-stat"><div class="hr-stat-label">Stocks</div>'
        f'<div class="hr-stat-value">{len(df)}</div></div>'
        f'<div class="hr-stat"><div class="hr-stat-label">Live price</div>'
        f'<div class="hr-stat-value">{priced}</div></div>'
        f"</div></div>"
        f'<details class="fund-section" open>'
        f"<summary><span>Portfolio</span>"
        f'<span class="fund-section-meta">{len(df)} stocks</span></summary>'
        f'<div class="fund-section-body">'
        f'<table class="report"><thead><tr>{thead}</tr></thead>'
        f"<tbody>{tbody}</tbody></table>"
        f"</div></details>"
        f"</div>"
    )
    css = _REPORT_CSS + (_HOLDINGS_INLINE_NEWS_CSS if show_news else "")
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{css}</head><body>{body}</body></html>"
        )
    return f"{css}{body}"


def holdings_iframe_height(row_count: int) -> int:
    return min(2400, max(520, 200 + row_count * 30))


_HOLDINGS_NEWS_RULES = """
  .news-page { padding: 8px 10px 12px; }
  .news-hint {
    font-size: 12px;
    color: #6b7280;
    margin: 0 0 10px;
  }
  .news-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  details.news-stock {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #fff;
    overflow: hidden;
  }
  details.news-stock summary {
    list-style: none;
    cursor: pointer;
    padding: 11px 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    background: #f9fafb;
    user-select: none;
  }
  details.news-stock summary::-webkit-details-marker { display: none; }
  details.news-stock summary::after {
    content: "▾";
    margin-left: auto;
    color: #9ca3af;
    font-size: 11px;
    flex-shrink: 0;
  }
  details.news-stock[open] summary::after { content: "▴"; }
  details.news-stock[open] summary {
    border-bottom: 1px solid #e5e7eb;
    background: #f3f4f6;
  }
  details.news-stock summary:hover { background: #f1f5f9; }
  .news-sym {
    font-weight: 800;
    font-size: 13px;
    color: #111827;
    min-width: 76px;
    flex-shrink: 0;
  }
  .news-preview {
    flex: 1;
    min-width: 0;
    color: #6b7280;
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .news-pill {
    font-size: 10px;
    font-weight: 700;
    color: #6b7280;
    background: #e5e7eb;
    padding: 2px 7px;
    border-radius: 4px;
    flex-shrink: 0;
  }
  .news-stock-body { padding: 2px 0 4px; }
  .news-item {
    padding: 10px 14px 10px 18px;
    border-bottom: 1px solid #f3f4f6;
  }
  .news-item:last-child { border-bottom: none; }
  .news-item-top {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 5px;
  }
  .news-when {
    font-size: 11px;
    color: #9ca3af;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .news-tag {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #047857;
    background: #d1fae5;
    padding: 2px 6px;
    border-radius: 4px;
  }
  .news-link {
    color: #1f2937;
    text-decoration: none;
    line-height: 1.5;
    font-weight: 500;
    font-size: 13px;
    display: block;
  }
  .news-link:hover { color: #1d4ed8; text-decoration: underline; }
  .news-empty {
    padding: 36px 16px;
    text-align: center;
    color: #6b7280;
    font-size: 13px;
  }
"""


def _holdings_news_styles() -> str:
    return f"<style>{_HOLDINGS_NEWS_RULES}</style>"


def _format_news_when(raw: str) -> str:
    s = safe_str(raw).strip()
    if not s:
        return "—"
    try:
        if len(s) >= 16 and s[4] == "-":
            dt = datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
            return dt.strftime("%d %b · %H:%M")
    except ValueError:
        pass
    return s[:16] if len(s) > 16 else s


def _group_news_by_ticker(feed: list[dict]) -> list[tuple[str, list[dict]]]:
    buckets: dict[str, list[dict]] = {}
    for item in feed:
        ticker = safe_str(item.get("ticker")).upper() or "—"
        buckets.setdefault(ticker, []).append(item)

    grouped: list[tuple[str, list[dict]]] = []
    for ticker, items in buckets.items():
        sorted_items = sorted(items, key=lambda x: safe_str(x.get("published")), reverse=True)
        grouped.append((ticker, sorted_items))

    def _latest(items: list[dict]) -> str:
        pubs = [safe_str(i.get("published")) for i in items if safe_str(i.get("published"))]
        return max(pubs) if pubs else ""

    grouped.sort(key=lambda pair: _latest(pair[1]), reverse=True)
    return grouped


def _truncate(text: str, limit: int = 72) -> str:
    s = safe_str(text).strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _holdings_news_accordion(feed: list[dict]) -> str:
    if not feed:
        return '<div class="news-empty">No headlines yet.</div>'

    blocks: list[str] = []
    for ticker, items in _group_news_by_ticker(feed):
        valid = [
            item
            for item in items
            if safe_str(item.get("title")) and safe_str(item.get("url"))
        ]
        if not valid:
            continue

        latest = valid[0]
        preview_when = _format_news_when(safe_str(latest.get("published")))
        preview_title = _truncate(safe_str(latest.get("title")))
        preview = f"{preview_when} — {preview_title}" if preview_when != "—" else preview_title

        item_html: list[str] = []
        for idx, item in enumerate(valid):
            title = html.escape(safe_str(item.get("title")))
            url = html.escape(safe_str(item.get("url")))
            when = html.escape(_format_news_when(safe_str(item.get("published"))))
            tag = '<span class="news-tag">Latest</span>' if idx == 0 else ""
            item_html.append(
                '<div class="news-item">'
                f'<div class="news-item-top">{tag}'
                f'<span class="news-when">{when}</span></div>'
                f'<a class="news-link" href="{url}" target="_blank" '
                f'rel="noopener noreferrer">{title}</a>'
                "</div>"
            )

        sym = html.escape(ticker)
        count = len(valid)
        blocks.append(
            f'<details class="news-stock">'
            f"<summary>"
            f'<span class="news-sym">{sym}</span>'
            f'<span class="news-preview">{html.escape(preview)}</span>'
            f'<span class="news-pill">{count}</span>'
            f"</summary>"
            f'<div class="news-stock-body">{"".join(item_html)}</div>'
            f"</details>"
        )

    if not blocks:
        return '<div class="news-empty">No articles returned.</div>'

    return f'<div class="news-list">{"".join(blocks)}</div>'


def build_holdings_news_html(
    feed: list[dict],
    *,
    holdings_count: int = 0,
    title: str = "Google News",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    article_count = len(feed)
    ticker_count = len({safe_str(i.get("ticker")).upper() for i in feed if safe_str(i.get("ticker"))})
    meta = subtitle or (
        f"{holdings_count} holdings · {ticker_count} with news · {article_count} headlines"
    )
    body = (
        f'<div class="fund-page news-page">'
        f"{_holdings_news_accordion(feed)}"
        f"</div>"
    )
    css = _REPORT_CSS + _holdings_news_styles()
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{css}</head><body>{body}</body></html>"
        )
    return f"{css}{body}"


def holdings_news_iframe_height(article_count: int, ticker_count: int) -> int:
    del article_count
    return min(960, max(380, 64 + ticker_count * 46))


_TURTLE_COLS: list[tuple[str, str, str | int]] = [
    ("sector", "Sector", "text"),
    ("bucket", "Bucket", "text"),
    ("score", "Score", 0),
    ("score_price", "ATH Px", 0),
    ("score_pat", "ATH PAT", 0),
    ("score_rs", "ATH RS", 0),
    ("price", "Price", 2),
]


def _turtle_table_rows(df: pd.DataFrame, *, highlight_holdings: bool = False) -> str:
    if df.empty:
        return '<tr><td colspan="99" class="muted">No data</td></tr>'

    df = attach_research_links(df) if "tv_link" not in df.columns else df.copy()
    rows: list[str] = []

    for idx, (_, row) in enumerate(df.iterrows()):
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        sc = row.get("screener_link") or screener_url(ticker, market)
        tv = row.get("tv_link") or tradingview_url(ticker, market)
        is_holding = bool(row.get("is_holding"))
        classes = []
        if idx < 3:
            classes.append("top3")
        if highlight_holdings and is_holding:
            classes.append("holding-row")
        row_class = f' class="{" ".join(classes)}"' if classes else ""

        cells = [
            f'<td class="rank">{idx + 1}</td>',
            f"<td>{_fund_symbol_cell(ticker, row.get('name'), sc, tv)}</td>",
        ]
        for col, _, fmt in _TURTLE_COLS:
            val = row.get(col)
            if fmt == "text":
                cells.append(f'<td class="muted col-text">{_cell(val)}</td>')
            elif col == "score" and val is not None and int(val) == 3:
                cells.append(
                    f'<td class="num"><span class="badge-score">'
                    f"{_num_cell(val, decimals=0)}</span></td>"
                )
            else:
                cells.append(f'<td class="num">{_num_cell(val, decimals=int(fmt))}</td>')
        rows.append(f"<tr{row_class}>{''.join(cells)}</tr>")
    return "".join(rows)


def _turtle_section(
    title: str,
    df: pd.DataFrame,
    *,
    open_section: bool = False,
    highlight_holdings: bool = False,
) -> str:
    headers: list[tuple[str, str]] = [("#", "col-rank"), ("Stock", "")]
    for _, label, fmt in _TURTLE_COLS:
        cls = "col-text" if fmt == "text" else "col-num"
        headers.append((label, cls))
    thead = "".join(
        f'<th class="{cls}">{html.escape(label)}</th>' for label, cls in headers
    )
    tbody = _turtle_table_rows(df, highlight_holdings=highlight_holdings)
    open_attr = " open" if open_section else ""
    return (
        f'<details class="fund-section"{open_attr}>'
        f"<summary>"
        f"<span>{html.escape(title)}</span>"
        f'<span class="fund-section-meta">{len(df)} stocks</span>'
        f"</summary>"
        f'<div class="fund-section-body">'
        f'<table class="report"><thead><tr>{thead}</tr></thead>'
        f"<tbody>{tbody}</tbody></table>"
        f"</div></details>"
    )


def build_turtle_html(
    *,
    score3_df: pd.DataFrame,
    consistent_df: pd.DataFrame,
    fresh_df: pd.DataFrame,
    all_df: pd.DataFrame,
    title: str = "Turtlewealth",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    sections = (
        _turtle_section(
            "Score 3 — research list",
            score3_df,
            open_section=True,
            highlight_holdings=True,
        ),
        _turtle_section("Consistent (score 3)", consistent_df, highlight_holdings=True),
        _turtle_section("Fresh (score 3)", fresh_df, highlight_holdings=True),
        _turtle_section("All scanned (scores 0–3)", all_df),
    )
    meta = ""
    body = (
        f'<div class="fund-page">'
        f'<h1 class="fund-title">{html.escape(title)}</h1>'
        f"{meta}"
        f'<div class="fund-sections">{"".join(sections)}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}"
            f"<style>.holding-row td{{background:#eff6ff!important}}</style>"
            f"</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}<style>.holding-row td{{background:#eff6ff!important}}</style>{body}"


def turtle_iframe_height(row_count: int) -> int:
    return min(2400, max(520, 400 + min(row_count, 80) * 12))


_TQ_COLS: list[tuple[str, str, str | int]] = [
    ("market", "Mkt", "text"),
    ("sector", "Sector", "text"),
    ("price", "Price", 2),
    ("rsi", "RSI", 1),
    ("supertrend", "ST", 2),
    ("adx", "ADX", 1),
    ("di_plus", "DI+", 1),
    ("di_minus", "DI-", 1),
    ("long_term_rs", "RS 52W", 4),
    ("short_term_rs", "RS 13W", 4),
    ("crossover_type", "Crossover", "text"),
    ("crossover_score", "X-score", 0),
    ("score", "Score", 1),
    ("date", "Signal", "text"),
]

_BB_COLS: list[tuple[str, str, str | int]] = [
    ("market", "Mkt", "text"),
    ("sector", "Sector", "text"),
    ("price", "Price", 2),
    ("upper_band", "Upper", 2),
    ("signal", "Signal", "text"),
    ("timeframe", "TF", "text"),
    ("date", "Signal", "text"),
]


def _strategy_stats_html(df: pd.DataFrame, *, kind: str) -> str:
    if df.empty:
        return ""
    stats: list[tuple[str, str]] = [("Signals", str(len(df)))]
    if kind == "tq" and "score" in df.columns:
        stats.append(("Avg score", f"{df['score'].mean():.1f}"))
    elif kind == "recovery" and "recovery_score" in df.columns:
        stats.append(("Avg score", f"{df['recovery_score'].mean():.1f}"))
    elif kind == "bb" and "signal" in df.columns:
        new_breakouts = int((df["signal"] == "NEW_BREAKOUT").sum())
        stats.append(("New breakouts", str(new_breakouts)))
    elif kind == "rsi" and "rsi" in df.columns:
        stats.append(("Avg RSI", f"{df['rsi'].mean():.1f}"))
    elif kind == "breakout" and "signal" in df.columns:
        new_breakouts = int((df["signal"] == "NEW_BREAKOUT").sum())
        stats.append(("New breakouts", str(new_breakouts)))
        if "month_pct" in df.columns:
            stats.append(("Avg month %", f"{df['month_pct'].mean():.1f}%"))
    elif kind == "quant" and "quant_score" in df.columns:
        stats.append(("Avg score", f"{df['quant_score'].mean():.1f}"))
        if "setup" in df.columns:
            long_n = int((df["setup"] == "MR_LONG").sum())
            short_n = int((df["setup"] == "MR_SHORT").sum())
            stats.append(("MR long", str(long_n)))
            stats.append(("MR short", str(short_n)))
    elif kind == "hit" and "hit_score" in df.columns:
        stats.append(("Avg score", f"{df['hit_score'].mean():.1f}"))
        if "hit_theme_label" in df.columns:
            for theme_label, count in df["hit_theme_label"].value_counts().head(4).items():
                stats.append((str(theme_label), str(count)))
    blocks = "".join(
        f'<div class="hr-stat"><div class="hr-stat-label">{html.escape(label)}</div>'
        f'<div class="hr-stat-value">{html.escape(value)}</div></div>'
        for label, value in stats
    )
    return f'<div class="hr-stats">{blocks}</div>'


def _strategy_table_rows(df: pd.DataFrame, cols: list[tuple[str, str, str | int]]) -> str:
    if df.empty:
        return '<tr><td colspan="99" class="muted">No signals in this scan.</td></tr>'

    df = attach_research_links(df) if "tv_link" not in df.columns else df.copy()
    rows: list[str] = []

    for idx, (_, row) in enumerate(df.iterrows()):
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        sc = row.get("screener_link") or screener_url(ticker, market)
        tv = row.get("tv_link") or tradingview_url(ticker, market)
        row_class = ' class="top3"' if idx < 3 else ""

        cells = [
            f'<td class="rank">{idx + 1}</td>',
            f"<td>{_fund_symbol_cell(ticker, row.get('name'), sc, tv)}</td>",
        ]
        for col, _, fmt in cols:
            val = row.get(col)
            if col == "tq_zone":
                zone = safe_str(val).lower()
                badge = {
                    "yellow": "badge-yellow",
                    "red": "badge-red",
                    "green": "badge-score",
                }.get(zone, "muted")
                cells.append(
                    f'<td class="col-text"><span class="{badge}">'
                    f"{html.escape(zone.upper() if zone else '—')}</span></td>"
                )
            elif fmt == "text":
                text = _format_date(val) if col == "date" else _cell(val)
                cells.append(f'<td class="muted col-text">{text}</td>')
            elif col == "score":
                cells.append(
                    f'<td class="num"><span class="badge-score">'
                    f"{_num_cell(val, decimals=int(fmt))}</span></td>"
                )
            elif col == "crossover_score" and val is not None and not (
                isinstance(val, float) and pd.isna(val)
            ):
                score = int(val)
                badge = "badge-score" if score >= 3 else "muted"
                cells.append(
                    f'<td class="num"><span class="{badge}">'
                    f"{_num_cell(val, decimals=0)}</span></td>"
                )
            else:
                cells.append(f'<td class="num">{_num_cell(val, decimals=int(fmt))}</td>')
        rows.append(f"<tr{row_class}>{''.join(cells)}</tr>")
    return "".join(rows)


def _strategy_section(
    title: str,
    df: pd.DataFrame,
    cols: list[tuple[str, str, str | int]],
    *,
    kind: str,
    open_section: bool = False,
) -> str:
    headers: list[tuple[str, str]] = [("#", "col-rank"), ("Stock", "")]
    for _, label, fmt in cols:
        cls = "col-text" if fmt == "text" else "col-num"
        headers.append((label, cls))
    thead = "".join(
        f'<th class="{cls}">{html.escape(label)}</th>' for label, cls in headers
    )
    stats = _strategy_stats_html(df, kind=kind)
    open_attr = " open" if open_section else ""
    return (
        f'<details class="fund-section"{open_attr}>'
        f"<summary>"
        f"<span>{html.escape(title)}</span>"
        f'<span class="fund-section-meta">{len(df)} signals</span>'
        f"</summary>"
        f'<div class="fund-section-body">'
        f"{stats}"
        f'<table class="report"><thead><tr>{thead}</tr></thead>'
        f"<tbody>{_strategy_table_rows(df, cols)}</tbody></table>"
        f"</div></details>"
    )


def build_strategy_html(
    *,
    tq_df: pd.DataFrame | None = None,
    bb_df: pd.DataFrame | None = None,
    bb_timeframe: str = "weekly",
    include_tq: bool = True,
    include_bb: bool = False,
    title: str = "Strategy scan",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    sections: list[str] = []
    if include_tq:
        sections.append(
            _strategy_section(
                "TQ — weekly trend + RS vs NIFTY",
                tq_df if tq_df is not None else pd.DataFrame(),
                _TQ_COLS,
                kind="tq",
                open_section=True,
            )
        )
    if include_bb:
        sections.append(
            _strategy_section(
                f"Bollinger Bands ({bb_timeframe})",
                bb_df if bb_df is not None else pd.DataFrame(),
                _BB_COLS,
                kind="bb",
                open_section=not include_tq,
            )
        )

    meta = ""
    body = (
        f'<div class="fund-page">'
        f'<h1 class="fund-title">{html.escape(title)}</h1>'
        f"{meta}"
        f'<div class="fund-sections">{"".join(sections)}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def strategy_iframe_height(
    *,
    tq_rows: int = 0,
    bb_rows: int = 0,
    sections: int = 1,
) -> int:
    rows = max(tq_rows, bb_rows)
    base = 300 + sections * 100
    return min(2000, max(480, base + min(rows, 50) * 16))


from stocks.dashboards.iframe_helpers import embed_html_iframe


def report_iframe_height(row_count: int, *, full_list: bool = False) -> int:
    if full_list:
        return min(2400, max(320, 52 + row_count * 40))
    return min(960, max(200, 44 + row_count * 54))
