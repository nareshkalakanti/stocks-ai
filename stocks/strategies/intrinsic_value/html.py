"""Light HTML tables for Intrinsic Value ranking and headwind/tailwind."""

from __future__ import annotations

import html
import json

import pandas as pd

from stocks.core.database import load_company_profiles_from_db
from stocks.core.text_utils import resolve_company_name, safe_str
from stocks.dashboards.expand_panel_html import CORP_TAGS_JS
from stocks.listings.sector_display import effective_industry_label
from stocks.shared.corp_tags import corp_tags_dict_for_ticker
from stocks.shared.superstars.holdings import superstar_pead_map
from stocks.strategies.intrinsic_value.strategy import rank_intrinsic_value


_IV_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
)
_IV_CSS = """
<style>
  :root {
    --bg: #f8fafc;
    --panel: #f1f5f9;
    --border: #e2e8f0;
    --text: #0f172a;
    --muted: #64748b;
    --green: #059669;
    --red: #dc2626;
    --amber: #d97706;
    --row-even: #ffffff;
    --row-odd: #f8fafc;
    --row-hover: #eff6ff;
  }
  body {
    margin: 0;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  .iv-wrap { padding: 16px 18px; background: #fff; border-radius: 8px; }
  .iv-title {
    font-size: 11px;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 4px;
    font-weight: 600;
  }
  .iv-h1 { font-size: 20px; font-weight: 700; margin: 0 0 10px; color: var(--text); }
  .iv-meta { color: var(--muted); margin-bottom: 14px; font-size: 12px; }
  table.iv {
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    table-layout: fixed;
  }
  table.iv th,
  table.iv td {
    padding: 11px 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  table.iv th {
    color: #475569;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .04em;
    background: var(--panel);
    font-weight: 600;
    text-align: left;
    white-space: nowrap;
  }
  table.iv th.num,
  table.iv td.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  #hw-table th:nth-child(1),
  #hw-table td:nth-child(1) { width: 24%; text-align: left; }
  #hw-table th:nth-child(2),
  #hw-table td:nth-child(2) { width: 7%; }
  #hw-table th:nth-child(3),
  #hw-table td:nth-child(3) { width: 92px; max-width: 100px; }
  #hw-table td:nth-child(3) .badge { display: inline-block; }
  table.iv th.col-rank,
  table.iv td.col-rank {
    width: 52px;
    text-align: center;
    color: var(--muted);
    font-weight: 600;
    font-size: 13px;
  }
  table.iv th.col-company,
  table.iv td.col-company {
    width: 28%;
    text-align: left;
  }
  table.iv th.col-sector,
  table.iv td.col-sector,
  table.iv th.col-industry,
  table.iv td.col-industry {
    width: 11%;
    text-align: left;
    color: #334155;
    font-size: 13px;
  }
  table.iv th.col-mcap { width: 9%; }
  table.iv th.col-growth { width: 12%; }
  table.iv th.col-roce { width: 10%; }
  table.iv th.col-pb { width: 7%; }
  table.iv th.col-pe { width: 7%; }
  table.iv th.col-fpe { width: 7%; }
  table.iv th.col-score { width: 7%; }
  .iv-expand-panel table.iv:not(.iv-stocks) { table-layout: fixed; }
  table.iv.iv-stocks {
    table-layout: fixed;
    width: 100%;
    min-width: 920px;
    font-size: 13px;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }
  table.iv.iv-stocks th {
    font-size: 10px;
    letter-spacing: 0.06em;
    padding: 10px 12px;
    white-space: nowrap;
    background: #f8fafc;
    border-bottom: 1px solid var(--border);
  }
  table.iv.iv-stocks th.sortable {
    cursor: pointer;
    user-select: none;
  }
  table.iv.iv-stocks th.sortable:hover { background: #f1f5f9; }
  table.iv.iv-stocks th .th-inner {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  table.iv.iv-stocks th.num .th-inner { justify-content: flex-end; width: 100%; }
  table.iv.iv-stocks th .sort-ind {
    color: #94a3b8;
    font-size: 10px;
    opacity: 0.75;
    font-weight: 600;
  }
  table.iv.iv-stocks th .sort-ind.active {
    color: #2563eb;
    opacity: 1;
    font-weight: 700;
  }
  table.iv.iv-stocks td {
    padding: 11px 12px;
    font-size: 13px;
    line-height: 1.35;
    vertical-align: middle;
    background: #fff;
    border-bottom: 1px solid #f1f5f9;
  }
  table.iv.iv-stocks tbody tr:last-child td { border-bottom: none; }
  table.iv.iv-stocks tbody tr:hover td { background: #fafafa !important; }
  table.iv.iv-stocks .col-rank {
    width: 32px;
    max-width: 32px;
    min-width: 32px;
    padding-left: 8px;
    padding-right: 4px;
    text-align: right;
    color: #94a3b8;
    font-weight: 600;
    font-size: 12px;
    white-space: nowrap;
  }
  table.iv.iv-stocks .col-company {
    width: 220px;
    min-width: 0;
    text-align: left;
    overflow: visible;
    white-space: normal;
    padding-left: 8px;
  }
  table.iv.iv-stocks .col-industry {
    width: 128px;
    min-width: 0;
    text-align: left;
    font-size: 12px;
    color: #475569;
    white-space: normal;
    overflow-wrap: anywhere;
    line-height: 1.3;
  }
  table.iv.iv-stocks .col-pcf {
    width: 1%;
    white-space: nowrap;
  }
  table.iv.iv-stocks .col-mcap,
  table.iv.iv-stocks .col-growth,
  table.iv.iv-stocks .col-roce,
  table.iv.iv-stocks .col-pb,
  table.iv.iv-stocks .col-pe,
  table.iv.iv-stocks .col-fpe,
  table.iv.iv-stocks .col-score {
    width: 1%;
    white-space: nowrap;
  }
  .pe-val { font-weight: 600; font-variant-numeric: tabular-nums; }
  .pe-val.neg { color: #dc2626; }
  .pe-val.pos { color: var(--text); }
  .fpe-good { color: #059669; font-weight: 600; font-variant-numeric: tabular-nums; }
  .fpe-mid { color: #d97706; font-weight: 600; font-variant-numeric: tabular-nums; }
  .fpe-bad { color: #dc2626; font-weight: 600; font-variant-numeric: tabular-nums; }
  table.iv.iv-stocks .col-score {
    text-align: right;
    color: var(--green);
    font-weight: 700;
    font-size: 13px;
    min-width: 64px;
    padding-left: 8px;
    padding-right: 10px;
    overflow: visible;
    text-overflow: clip;
    font-variant-numeric: tabular-nums;
  }
  table.iv.iv-stocks th.col-score {
    min-width: 64px;
    overflow: visible;
    text-overflow: clip;
  }
  table.iv.iv-stocks td.num { white-space: nowrap; }
  table.iv.iv-stocks td.col-company,
  table.iv.iv-stocks td.col-industry {
    overflow: visible;
    text-overflow: clip;
  }
  table.iv.iv-stocks td.col-company .company-name {
    word-break: normal;
    overflow-wrap: anywhere;
  }
  .na-cell {
    color: #94a3b8;
    font-weight: 500;
    font-size: 12px;
    cursor: help;
    border-bottom: 1px dotted #cbd5e1;
  }
  table.iv tbody tr:nth-child(even) td { background: var(--row-odd); }
  table.iv tbody tr:nth-child(odd) td { background: var(--row-even); }
  table.iv:not(.iv-stocks) tbody tr:hover td { background: var(--row-hover) !important; }
  .company-name {
    font-weight: 600;
    font-size: 14px;
    color: var(--text);
    line-height: 1.35;
    margin-bottom: 3px;
  }
  .company-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    font-size: 12px;
    line-height: 1.3;
  }
  .ticker {
    color: var(--muted);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    letter-spacing: .02em;
  }
  .metric-cell {
    display: inline-flex;
    align-items: baseline;
    justify-content: flex-end;
    gap: 5px;
    width: 100%;
    max-width: 100%;
  }
  .metric-val {
    font-weight: 500;
    color: var(--text);
    white-space: nowrap;
  }
  .metric-rank {
    color: var(--muted);
    font-size: 11px;
    font-weight: 500;
    white-space: nowrap;
    min-width: 1.6em;
    text-align: right;
  }
  .score-good { color: var(--green); font-weight: 700; font-size: 15px; }
  .score-bad { color: var(--red); font-weight: 700; }
  .badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
  }
  .badge-tail { background: #ecfdf5; color: var(--green); border: 1px solid #a7f3d0; }
  .badge-head { background: #fef2f2; color: var(--red); border: 1px solid #fecaca; }
  .badge-neutral { background: #fffbeb; color: var(--amber); border: 1px solid #fde68a; }
  .bar-wrap {
    position: relative;
    height: 8px;
    background: #e2e8f0;
    border-radius: 999px;
    min-width: 100px;
  }
  .bar-fill {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    border-radius: 999px;
    background: linear-gradient(90deg, #fca5a5, #fcd34d, #34d399);
  }
  .sub-rank { color: var(--muted); font-size: 11px; }
  .links { display: inline-flex; gap: 4px; }
  a.link {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    background: #eff6ff;
    color: #1d4ed8;
    text-decoration: none;
    font-weight: 600;
    font-size: 10px;
    line-height: 1.4;
  }
  a.link:hover { background: #dbeafe; text-decoration: underline; }
  .hw-board { display: flex; flex-direction: column; gap: 0; }
  .hw-row {
    display: grid;
    grid-template-columns: minmax(180px, 1.4fr) minmax(200px, 2fr) auto;
    align-items: center;
    gap: 16px;
    padding: 14px 4px;
    border-bottom: 1px solid var(--border);
  }
  .hw-row:last-child { border-bottom: none; }
  .hw-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    line-height: 1.35;
  }
  .hw-bar-area {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }
  .hw-bar {
    flex: 1;
    height: 10px;
    background: #e2e8f0;
    border-radius: 999px;
    overflow: hidden;
    min-width: 80px;
  }
  .hw-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #34d399, #10b981);
  }
  .hw-fill.head { background: linear-gradient(90deg, #f87171, #dc2626); }
  .hw-fill.neutral { background: linear-gradient(90deg, #fcd34d, #f59e0b); }
  .hw-score {
    font-size: 13px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text);
    white-space: nowrap;
    min-width: 4.5em;
    text-align: right;
  }
  .hw-signal { justify-self: end; white-space: nowrap; }
  table.iv tbody tr.iv-sector-row { cursor: pointer; }
  table.iv tbody tr.iv-sector-row.expanded td { background: var(--row-hover) !important; }
  table.iv tbody tr.iv-expand-row td {
    padding: 8px 10px 10px;
    background: #f8fafc !important;
    border-bottom: 1px solid var(--border);
  }
  .expand-hint {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-right: 2px solid #94a3b8;
    border-bottom: 2px solid #94a3b8;
    transform: rotate(-45deg);
    margin-right: 6px;
    vertical-align: middle;
    opacity: 0.7;
  }
  tr.iv-sector-row.expanded .expand-hint { transform: rotate(45deg); margin-top: -2px; }
  .iv-expand-panel {
    padding: 0;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    overflow: hidden;
    margin: 4px 0 2px;
  }
  .iv-expand-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 12px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    font-size: 11px;
    color: var(--muted);
    flex-wrap: wrap;
  }
  .iv-expand-toolbar strong {
    color: var(--text);
    font-size: 12px;
  }
  .ht-filter-bar {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin: 0 0 12px;
    padding: 8px 10px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
  }
  .ht-filter-group {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }
  .ht-filter-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-right: 2px;
  }
  .ht-filter-btn {
    padding: 5px 9px;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
    background: #fff;
    color: #64748b;
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }
  .ht-filter-btn:hover { background: #f1f5f9; border-color: #cbd5e1; }
  .ht-filter-btn.on {
    background: #2563eb;
    color: #fff;
    border-color: #2563eb;
  }
  .ht-filter-btn.fpe.on { background: #0f766e; border-color: #0f766e; }
  .ht-filter-btn.pcf.on { background: #b45309; border-color: #b45309; }
  .ht-filter-count {
    margin-left: auto;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
  }
  .iv-expand-scroll {
    max-height: min(58vh, 520px);
    overflow: auto;
    background: #fff;
  }
  .iv-expand-scroll table.iv.iv-stocks {
    border: none;
    border-radius: 0;
  }
  .iv-expand-scroll table.iv.iv-stocks thead th {
    position: sticky;
    top: 0;
    z-index: 1;
    box-shadow: 0 1px 0 #e2e8f0;
  }
  .hw-more-row td {
    text-align: center;
    padding: 10px 12px !important;
    background: #fafafa !important;
  }
  .hw-more-btn {
    appearance: none;
    border: 1px solid #cbd5e1;
    background: #fff;
    color: #334155;
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  .hw-more-btn:hover { background: #f8fafc; border-color: #94a3b8; }
  .iv-expand-head {
    padding: 10px 14px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
  }
  .iv-expand-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--text);
    margin: 0;
  }
  .iv-expand-meta {
    font-size: 11px;
    color: var(--muted);
    margin: 3px 0 0;
  }
  .iv-expand-body { padding: 0; }
  .company-cell { min-width: 0; }
  .company-top {
    display: flex;
    align-items: flex-start;
    justify-content: flex-start;
    gap: 8px;
    margin-bottom: 4px;
  }
  .company-cell .company-name {
    font-weight: 700;
    font-size: 14px;
    line-height: 1.35;
    letter-spacing: -0.01em;
    white-space: normal;
    word-break: break-word;
    flex: 1;
    min-width: 0;
    color: #0f172a;
    margin-bottom: 0;
  }
  .company-sub {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 5px;
    min-height: 0;
    margin-top: 4px;
  }
  .company-sub:empty { display: none; }
  .company-sub .corp-tag {
    font-size: 9px;
    padding: 2px 6px;
    border-radius: 4px;
  }
  .links-inline {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex-shrink: 0;
    margin-left: auto;
    white-space: nowrap;
  }
  .links-inline a.link,
  .links-inline a {
  table.iv .links a.link {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    background: #f1f5f9;
    color: #475569;
    text-decoration: none;
    font-size: 10px;
    font-weight: 700;
  }
  .links-inline a:hover,
  table.iv .links a.link:hover { background: #e2e8f0; color: #0f172a; }
  .corp-tags {
    display: inline-flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 5px;
    margin: 0;
  }
  .corp-tag {
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    line-height: 1.2;
    padding: 2px 6px;
    border-radius: 4px;
    white-space: nowrap;
  }
  .corp-tag-bg { color: #6d28d9; background: #f5f3ff; }
  .corp-tag-hold { color: #1d4ed8; background: #eff6ff; }
  .corp-tag-dem { color: #b45309; background: #fffbeb; }
  .corp-tag-spin { color: #0e7490; background: #ecfeff; }
  .corp-tag-spec { color: #be185d; background: #fdf2f8; }
  .corp-tag-ss { color: #854d0e; background: #fef9c3; max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
  table.iv.iv-stocks td.col-company { white-space: normal; overflow: visible; }
</style>
"""


def _fmt_pct(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v):.2f}%"


def _fmt_num(v, d=2) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    return f"{float(v):.{d}f}"


def _metric_cell(value: str, rank: int | None = None) -> str:
    rank_html = ""
    if rank is not None and rank > 0:
        rank_html = f'<span class="metric-rank">({rank})</span>'
    return f'<span class="metric-cell"><span class="metric-val">{value}</span>{rank_html}</span>'


def build_ranking_html(
    ranked: pd.DataFrame,
    *,
    title: str = "Intrinsic Value Ranking",
    subtitle: str = "",
    standalone: bool = True,
) -> str:
    if ranked is None or ranked.empty:
        body = '<div class="iv-wrap"><div class="iv-h1">No ranked companies</div></div>'
    else:
        rows_html: list[str] = []
        for _, row in ranked.iterrows():
            sc = safe_str(row.get("screener_link"))
            tv = safe_str(row.get("tv_link"))
            links = ""
            if sc or tv:
                link_bits = []
                if sc:
                    link_bits.append(
                        f'<a class="link" href="{html.escape(sc)}" target="_blank" rel="noopener">SC</a>'
                    )
                if tv:
                    link_bits.append(
                        f'<a class="link" href="{html.escape(tv)}" target="_blank" rel="noopener">TV</a>'
                    )
                links = f'<span class="links">{"".join(link_bits)}</span>'
            company = (
                f'<div class="company-name">{html.escape(resolve_company_name(row.get("name"), ticker=safe_str(row.get("ticker"))))}</div>'
                f'<div class="company-meta">'
                f'<span class="ticker">{html.escape(safe_str(row.get("ticker")))}</span>'
                f"{links}</div>"
            )
            rows_html.append(
                "<tr>"
                f'<td class="col-rank">{int(row.get("rank", 0))}</td>'
                f"<td class=\"col-company\">{company}</td>"
                f'<td class="col-sector">{html.escape(safe_str(row.get("sector")))}</td>'
                f'<td class="col-industry">{html.escape(safe_str(row.get("industry") or row.get("sub_sector")))}</td>'
                f'<td class="num col-mcap">₹{_fmt_num(row.get("market_cap_cr"), 1)} Cr</td>'
                f'<td class="num col-growth">{_metric_cell(_fmt_pct(row.get("sales_growth_3y")), int(row.get("growth_rank", 0)) or None)}</td>'
                f'<td class="num col-roce">{_metric_cell(_fmt_pct(row.get("roce_3y")), int(row.get("roce_rank", 0)) or None)}</td>'
                f'<td class="num col-pb">{_metric_cell(_fmt_num(row.get("pb")), int(row.get("pb_rank", 0)) or None)}</td>'
                f'<td class="num col-score score-good">{int(row.get("total_score", 0))}</td>'
                "</tr>"
            )
        meta = html.escape(subtitle) if subtitle else ""
        meta_html = f'<div class="iv-meta">{meta}</div>' if meta else ""
        body = (
            f'<div class="iv-wrap">'
            f'<div class="iv-title">Market Analysis Tool</div>'
            f'<h1 class="iv-h1">{html.escape(title)}</h1>'
            f"{meta_html}"
            f"<table class=\"iv\"><thead><tr>"
            f"<th class=\"col-rank\">Rank</th>"
            f"<th class=\"col-company\">Company</th>"
            f"<th class=\"col-sector\">Sector</th>"
            f"<th class=\"col-industry\">Industry</th>"
            f"<th class=\"num col-mcap\">Mkt cap</th>"
            f"<th class=\"num col-growth\">Sales growth 3Y ↑</th>"
            f"<th class=\"num col-roce\">ROCE 3Y ↑</th>"
            f"<th class=\"num col-pb\">P/B ↓</th>"
            f"<th class=\"num col-score\">Total score</th>"
            f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>"
        )

    if standalone:
        return (
            f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title>{_IV_FONT_LINK}{_IV_CSS}</head><body>{body}</body></html>"
        )
    return f"{_IV_FONT_LINK}{_IV_CSS}{body}"


def build_headwind_html(
    sectors: pd.DataFrame,
    *,
    title: str = "H&T sector board",
    standalone: bool = True,
) -> str:
    if sectors is None or sectors.empty:
        body = '<div class="iv-wrap"><div class="iv-h1">No sector data</div></div>'
    else:
        rows_html: list[str] = []
        for _, row in sectors.iterrows():
            ind = safe_str(row.get("indicator")).upper()
            if ind == "TAILWIND":
                badge_cls = "badge-tail"
            elif ind == "HEADWIND":
                badge_cls = "badge-head"
            else:
                badge_cls = "badge-neutral"
            sign = "+" if score >= 0 else ""
            rows_html.append(
                "<tr>"
                f'<td>{html.escape(safe_str(row.get("sector")))}</td>'
                f'<td class="num">{int(row.get("companies", 0))}</td>'
                f'<td><span class="badge {badge_cls}">{html.escape(ind)}</span></td>'
                f'<td class="num">{_fmt_pct(row.get("median_growth_3y"))}</td>'
                f'<td class="num">{_fmt_pct(row.get("median_roce_3y"))}</td>'
                f'<td class="num">{_fmt_num(row.get("median_pb"))}</td>'
                f'<td class="num">{_fmt_num(row.get("avg_total_score"), 1)}</td>'
                "</tr>"
            )
        body = (
            f'<div class="iv-wrap">'
            f'<div class="iv-title">H&T</div>'
            f'<h1 class="iv-h1">{html.escape(title)}</h1>'
            f'<div class="iv-meta">Sector signal vs market medians on 3Y sales growth, 3Y ROCE, and P/B</div>'
            f"<table class=\"iv\"><thead><tr>"
            f"<th>Sector</th><th class=\"num\">Stocks</th><th>Signal</th>"
            f"<th class=\"num\">Median growth 3Y</th><th class=\"num\">Median ROCE 3Y</th>"
            f"<th class=\"num\">Median P/B</th><th class=\"num\">Avg total score</th>"
            f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>"
        )
    if standalone:
        return (
            f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title>{_IV_FONT_LINK}{_IV_CSS}</head><body>{body}</body></html>"
        )
    return f"{_IV_FONT_LINK}{_IV_CSS}{body}"


def intrinsic_iframe_height(row_count: int) -> int:
    return min(900, max(220, 130 + row_count * 48))


def headwind_board_iframe_height(row_count: int) -> int:
    return min(2400, max(280, 80 + row_count * 52))


def build_headwind_board_html(
    sectors: pd.DataFrame,
    *,
    title: str = "H&T sector board",
    subtitle: str = "",
    standalone: bool = True,
) -> str:
    """IV Equity Advisors–style industry list with score bars (no table chrome)."""
    if sectors is None or sectors.empty:
        body = '<div class="iv-wrap"><div class="iv-h1">No industry data</div></div>'
    else:
        max_abs = max(0.05, float(sectors["score"].abs().max()))
        rows_html: list[str] = []
        for _, row in sectors.iterrows():
            score = float(row.get("score") or 0)
            pct = max(8, min(100, ((score + max_abs) / (2 * max_abs)) * 100))
            ind = safe_str(row.get("indicator")).upper()
            if ind == "TAILWIND":
                badge_cls = "badge-tail"
                fill_cls = ""
                arrow = "▲"
            elif ind == "HEADWIND":
                badge_cls = "badge-head"
                fill_cls = " head"
                arrow = "▼"
            else:
                badge_cls = "badge-neutral"
                fill_cls = " neutral"
                arrow = "●"
            sign = "+" if score >= 0 else ""
            name = safe_str(row.get("sector"))
            cos = int(row.get("companies", 0))
            rows_html.append(
                f'<div class="hw-row">'
                f'<div class="hw-name">{html.escape(name)}'
                f'<div class="sub-rank">{cos} companies</div></div>'
                f'<div class="hw-bar-area">'
                f'<div class="hw-bar"><div class="hw-fill{fill_cls}" style="width:{pct:.1f}%"></div></div>'
                f'<span class="hw-score">{sign}{score:.4f}</span></div>'
                f'<span class="hw-signal"><span class="badge {badge_cls}">{arrow} {html.escape(ind)}</span></span>'
                f"</div>"
            )
        meta = html.escape(subtitle) if subtitle else ""
        meta_html = f'<div class="iv-meta">{meta}</div>' if meta else ""
        body = (
            f'<div class="iv-wrap">'
            f'<div class="iv-title">H&T</div>'
            f'<h1 class="iv-h1">{html.escape(title)}</h1>'
            f"{meta_html}"
            f'<div class="hw-board">{"".join(rows_html)}</div></div>'
        )
    if standalone:
        return (
            f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title>{_IV_FONT_LINK}{_IV_CSS}</head><body>{body}</body></html>"
        )
    return f"{_IV_FONT_LINK}{_IV_CSS}{body}"


def _json_scalar(val):
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    return val


def _stock_row_json(
    src: pd.Series,
    *,
    ss_map: dict | None = None,
    website: str | None = None,
) -> dict:
    sector = safe_str(src.get("sector"))
    ticker = safe_str(src.get("ticker"))
    industry = effective_industry_label(
        sector=sector,
        industry=safe_str(src.get("industry")),
        sub_sector=safe_str(src.get("sub_sector")),
        source_sector=safe_str(src.get("source_sector")),
    )
    out = {
        "rank": int(src.get("rank") or 0),
        "ticker": ticker,
        "name": resolve_company_name(src.get("name"), ticker=ticker),
        "sector": sector,
        "industry": industry or None,
        "price": _json_scalar(src.get("price")),
        "market_cap_cr": _json_scalar(src.get("market_cap_cr")),
        "sales_growth_3y": _json_scalar(src.get("sales_growth_3y")),
        "roce_3y": _json_scalar(src.get("roce_3y")),
        "pb": _json_scalar(src.get("pb")),
        "pe_ratio": _json_scalar(src.get("pe_ratio")),
        "forward_pe": _json_scalar(src.get("forward_pe")),
        "pcf": _json_scalar(src.get("pcf")),
        "growth_rank": _json_scalar(src.get("growth_rank")),
        "roce_rank": _json_scalar(src.get("roce_rank")),
        "pb_rank": _json_scalar(src.get("pb_rank")),
        "total_score": _json_scalar(src.get("total_score")),
        "sc": safe_str(src.get("screener_link")) or None,
        "tv": safe_str(src.get("tv_link")) or None,
    }
    web = safe_str(website or src.get("website"))
    if web:
        out["website"] = web
    out.update(corp_tags_dict_for_ticker(ticker))
    if ss_map:
        ss = ss_map.get(ticker.upper()) or ss_map.get(ticker) or {}
        if ss.get("ss_holders_label"):
            out["ss_holders_label"] = ss["ss_holders_label"]
        if ss.get("ss_best"):
            out["ss_best"] = True
        if ss.get("ss_investor_count"):
            out["ss_investor_count"] = ss["ss_investor_count"]
    return out


def _sector_row_json(row: pd.Series, max_abs: float) -> dict:
    score = float(row.get("score") or 0)
    pct = max(0, min(100, ((score + max_abs) / (2 * max_abs)) * 100))
    return {
        "sector": safe_str(row.get("sector")),
        "companies": int(row.get("companies") or 0),
        "score": score,
        "score_pct": pct,
        "indicator": safe_str(row.get("indicator")).upper(),
        "median_growth_3y": _json_scalar(row.get("median_growth_3y")),
        "median_roce_3y": _json_scalar(row.get("median_roce_3y")),
        "median_pb": _json_scalar(row.get("median_pb")),
        "avg_total_score": _json_scalar(row.get("avg_total_score")),
    }


def _subset_for_sector_group(
    work: pd.DataFrame,
    key: str,
    industry_col: str,
) -> pd.DataFrame:
    """Match ranked rows to a sector-board group key (handles column mismatches)."""
    label = safe_str(key).strip()
    if not label or work.empty:
        return work.iloc[0:0].copy()
    if industry_col in work.columns:
        hit = work[work[industry_col].astype(str).str.strip() == label]
        if not hit.empty:
            return hit.copy()
    for col in ("sector", "sub_sector", "industry"):
        if col not in work.columns or col == industry_col:
            continue
        hit = work[work[col].astype(str).str.strip() == label]
        if not hit.empty:
            return hit.copy()
    return work.iloc[0:0].copy()


def _stocks_by_sector(
    sectors: pd.DataFrame,
    ranked: pd.DataFrame,
    industry_col: str,
) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if ranked is None or ranked.empty:
        return out
    work = ranked.copy()
    ss_map = superstar_pead_map(
        work["ticker"].astype(str).str.strip().str.upper().unique().tolist()
    )
    profiles = load_company_profiles_from_db(
        work["ticker"].astype(str).str.strip().str.upper().unique().tolist()
    )
    for _, sec in sectors.iterrows():
        key = safe_str(sec.get("sector"))
        if not key:
            continue
        subset = _subset_for_sector_group(work, key, industry_col)
        if subset.empty:
            out[key] = []
            continue
        ind_ranked = rank_intrinsic_value(subset)
        rows = [
            _stock_row_json(
                r,
                ss_map=ss_map,
                website=(profiles.get(safe_str(r.get("ticker")).upper()) or {}).get("website"),
            )
            for _, r in ind_ranked.iterrows()
        ]
        out[key] = rows
    return out


def headwind_drilldown_iframe_height(
    sector_count: int,
    *,
    max_sector_stocks: int = 0,
) -> int:
    """Size iframe for sector rows plus one expanded scroll panel."""
    base = 88 + max(1, sector_count) * 46
    if max_sector_stocks > 0:
        visible_rows = min(max_sector_stocks, 14)
        base += 92 + visible_rows * 36
    return min(2200, max(160, base))


def build_headwind_drilldown_html(
    sectors: pd.DataFrame,
    ranked: pd.DataFrame,
    industry_col: str,
    *,
    min_mcap_cr: float,
    title: str = "H&T — Industries",
    subtitle: str = "",
    standalone: bool = True,
    stocks_map: dict[str, list[dict]] | None = None,
) -> str:
    """Clickable sector table; expand row to show ranked stocks (PEAD-style)."""
    if sectors is None or sectors.empty:
        body = '<div class="iv-wrap"><div class="iv-h1">No sector data</div></div>'
    else:
        max_abs = max(0.05, float(sectors["score"].abs().max()))
        sector_rows = [_sector_row_json(r, max_abs) for _, r in sectors.iterrows()]
        if stocks_map is None:
            stocks_map = _stocks_by_sector(sectors, ranked, industry_col)
        meta = html.escape(subtitle) if subtitle else ""
        meta_html = f'<div class="iv-meta">{meta}</div>' if meta else ""
        data_sectors = json.dumps(sector_rows, separators=(",", ":"))
        data_stocks = json.dumps(stocks_map, separators=(",", ":"))
        body = f"""
<div class="iv-wrap">
  <div class="iv-title">H&T</div>
  <h1 class="iv-h1">{html.escape(title)}</h1>
  {meta_html}
  <div class="ht-filter-bar" id="ht-filter-bar">
    <div class="ht-filter-group" id="ht-fpe-filter">
      <span class="ht-filter-label">Fwd PE</span>
      <button type="button" class="ht-filter-btn fpe on" data-max="">All</button>
      <button type="button" class="ht-filter-btn fpe" data-max="15">≤15</button>
      <button type="button" class="ht-filter-btn fpe" data-max="20">≤20</button>
      <button type="button" class="ht-filter-btn fpe" data-max="30">≤30</button>
      <button type="button" class="ht-filter-btn fpe" data-max="40">≤40</button>
    </div>
    <div class="ht-filter-group" id="ht-pcf-filter">
      <span class="ht-filter-label">P/CF</span>
      <button type="button" class="ht-filter-btn pcf on" data-max="">All</button>
      <button type="button" class="ht-filter-btn pcf" data-max="8">≤8</button>
      <button type="button" class="ht-filter-btn pcf" data-max="10">≤10</button>
      <button type="button" class="ht-filter-btn pcf" data-max="15">≤15</button>
      <button type="button" class="ht-filter-btn pcf" data-max="20">≤20</button>
    </div>
    <div class="ht-filter-count" id="ht-filter-count"></div>
  </div>
  <table class="iv" id="hw-table">
    <thead><tr>
      <th>Sector</th><th class="num">Stocks</th><th>Signal</th>
      <th class="num">Median growth 3Y</th><th class="num">Median ROCE 3Y</th>
      <th class="num">Median P/B</th><th class="num">Avg total score</th>
    </tr></thead>
    <tbody id="hw-tbody"></tbody>
  </table>
</div>
<script>
const SECTORS = {data_sectors};
const STOCKS = {data_stocks};
const MIN_MCAP = {float(min_mcap_cr):.0f};
const SECTOR_COLS = 7;
const STOCK_COLS = 11;
const STOCK_PAGE = 60;
let expandedSector = null;
const stockPageLimits = {{}};
let fpeMax = null;
let pcfMax = null;
let stockSortCol = "total_score";
let stockSortDir = -1;
const STOCK_SORT_COLS = [
  {{id:"rank", label:"#", key:"rank", cls:"col-rank", sortable:false}},
  {{id:"company", label:"Company", key:"name", cls:"col-company", sortable:true}},
  {{id:"industry", label:"Industry", key:"industry", cls:"col-industry", sortable:true}},
  {{id:"market_cap_cr", label:"Mkt cap", key:"market_cap_cr", cls:"num col-mcap", sortable:true}},
  {{id:"sales_growth_3y", label:"Growth 3Y", key:"sales_growth_3y", cls:"num col-growth", sortable:true}},
  {{id:"roce_3y", label:"ROCE 3Y", key:"roce_3y", cls:"num col-roce", sortable:true}},
  {{id:"pb", label:"P/B", key:"pb", cls:"num col-pb", sortable:true}},
  {{id:"pe_ratio", label:"PE", key:"pe_ratio", cls:"num col-pe", sortable:true, title:"Option A: 4+ qtrs → sum last 4 EPS (TTM); 1–3 → sum available; else Yahoo trailingPE"}},
  {{id:"forward_pe", label:"Fwd PE", key:"forward_pe", cls:"num col-fpe", sortable:true, title:"Option B: price ÷ (latest quarter EPS × 4)"}},
  {{id:"pcf", label:"P/CF", key:"pcf", cls:"num col-pcf", sortable:true, title:"Price ÷ operating cash flow per share"}},
  {{id:"total_score", label:"Score", key:"total_score", cls:"num col-score", sortable:true}},
];

{CORP_TAGS_JS}

function esc(s) {{
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
}}
function num(v) {{
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}}
function fmtPct(v) {{
  const n = num(v);
  return n === null ? "—" : n.toFixed(2) + "%";
}}
function fmtNum(v, d=2) {{
  const n = num(v);
  return n === null ? "—" : n.toFixed(d);
}}
function badgeCls(ind) {{
  if (ind === "TAILWIND") return "badge-tail";
  if (ind === "HEADWIND") return "badge-head";
  return "badge-neutral";
}}
function metricCell(val, rank) {{
  const r = num(rank);
  const rankHtml = (r !== null && r > 0) ? `<span class="metric-rank">(${{Math.round(r)}})</span>` : "";
  return `<span class="metric-cell"><span class="metric-val">${{val}}</span>${{rankHtml}}</span>`;
}}
function displayName(s) {{
  const n = String(s.name || "").trim();
  const t = String(s.ticker || "").trim().toUpperCase();
  if (n && !n.includes(",") && !/\\.NS|\\.BO/i.test(n) && n.toUpperCase() !== t) return n;
  return t || n;
}}
function fmtWebPill(web) {{
  if (!web) return "";
  let href = String(web).trim();
  if (!/^https?:\\/\\//i.test(href)) href = "https://" + href;
  let title = href;
  try {{
    const host = new URL(href).hostname.replace(/^www\\./i, "");
    if (host) title = host;
  }} catch (_) {{}}
  return `<a class="link" href="${{esc(href)}}" target="_blank" rel="noopener noreferrer" title="${{esc(title)}}">Web</a>`;
}}
function fmtCompanyCell(s) {{
  const name = displayName(s);
  const links = [];
  if (s.sc) links.push(`<a class="link" href="${{esc(s.sc)}}" target="_blank" rel="noopener noreferrer" title="screener.in">SC</a>`);
  if (s.tv) links.push(`<a class="link" href="${{esc(s.tv)}}" target="_blank" rel="noopener noreferrer" title="TradingView">TV</a>`);
  const web = s.website;
  if (web) links.push(fmtWebPill(web));
  const tags = fmtCorpTags(s);
  const sub = tags ? `<div class="company-sub">${{tags}}</div>` : "";
  const linksHtml = links.length
    ? `<span class="links-inline">${{links.join("")}}</span>`
    : "";
  return (
    `<div class="company-cell">` +
    `<div class="company-top">` +
    `<span class="company-name">${{esc(name)}}</span>` +
    linksHtml +
    `</div>${{sub}}</div>`
  );
}}
const PE_TITLE = "Option A: 4+ qtrs → sum last 4 EPS; 1–3 qtrs → sum available; else Yahoo trailingPE";
function fmtPe(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return `<span class="na-cell" title="${{PE_TITLE}}">—</span>`;
  const cls = n < 0 ? "neg" : "pos";
  return `<span class="pe-val ${{cls}}" title="${{PE_TITLE}}">${{n.toFixed(1)}}</span>`;
}}
function fmtFpe(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return `<span class="na-cell" title="Option B: price ÷ (latest quarter EPS × 4)">—</span>`;
  if (n >= 500) return `<span class="fpe-bad" title="Option B: run-rate EPS ≤ 0 or PE capped">${{n.toFixed(1)}}</span>`;
  let cls = "fpe-good";
  if (n > 40) cls = "fpe-bad";
  else if (n > 20) cls = "fpe-mid";
  return `<span class="${{cls}}" title="Option B: price ÷ (latest quarter EPS × 4)">${{n.toFixed(1)}}</span>`;
}}
function fmtIndustry(s) {{
  const label = String(s.industry || s.sector || "").trim();
  return label ? esc(label) : '<span class="na-cell">—</span>';
}}
function passesValuationFilters(s) {{
  if (fpeMax !== null) {{
    const fpe = num(s.forward_pe);
    if (fpe === null || fpe >= 500 || fpe > fpeMax) return false;
  }}
  if (pcfMax !== null) {{
    const pcf = num(s.pcf);
    if (pcf === null || pcf <= 0 || pcf > pcfMax) return false;
  }}
  return true;
}}
function filteredStocks(sector) {{
  return (STOCKS[sector] || []).filter(passesValuationFilters);
}}
function sortKeyValue(s, key) {{
  if (key === "name") {{
    return String(displayName(s) || s.ticker || "").toLowerCase();
  }}
  if (key === "industry") {{
    return String(s.industry || s.sector || "").toLowerCase();
  }}
  let n = num(s[key]);
  if (key === "forward_pe" && n !== null && n >= 500) n = null;
  if (key === "pcf" && n !== null && n <= 0) n = null;
  return n;
}}
function compareStocks(a, b) {{
  const col = STOCK_SORT_COLS.find(c => c.id === stockSortCol) || STOCK_SORT_COLS[STOCK_SORT_COLS.length - 1];
  const key = col.key;
  const av = sortKeyValue(a, key);
  const bv = sortKeyValue(b, key);
  const aNull = av === null || av === "";
  const bNull = bv === null || bv === "";
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  if (typeof av === "string" || typeof bv === "string") {{
    return String(av).localeCompare(String(bv)) * stockSortDir;
  }}
  return (av - bv) * stockSortDir;
}}
function sortedStocks(sector) {{
  return filteredStocks(sector).slice().sort(compareStocks);
}}
function setStockSort(colId) {{
  const col = STOCK_SORT_COLS.find(c => c.id === colId);
  if (!col || !col.sortable) return;
  if (stockSortCol === colId) stockSortDir *= -1;
  else {{
    stockSortCol = colId;
    stockSortDir = (colId === "company" || colId === "industry") ? 1 : -1;
  }}
  Object.keys(stockPageLimits).forEach(k => delete stockPageLimits[k]);
  render();
}}
function renderStockHead(thead) {{
  thead.innerHTML = "";
  const tr = document.createElement("tr");
  STOCK_SORT_COLS.forEach(c => {{
    const th = document.createElement("th");
    th.className = c.cls + (c.sortable ? " sortable" : "");
    if (c.title) th.title = c.title;
    if (c.sortable) {{
      const active = stockSortCol === c.id;
      const arrow = active ? (stockSortDir < 0 ? "↓" : "↑") : "↕";
      th.innerHTML =
        `<span class="th-inner"><span class="th-label">${{c.label}}</span>` +
        `<span class="sort-ind${{active ? " active" : ""}}">${{arrow}}</span></span>`;
      th.onclick = (ev) => {{
        ev.stopPropagation();
        setStockSort(c.id);
      }};
    }} else {{
      th.textContent = c.label;
    }}
    tr.appendChild(th);
  }});
  thead.appendChild(tr);
}}
function updateFilterCount() {{
  let shown = 0;
  let total = 0;
  Object.keys(STOCKS).forEach(sec => {{
    const all = STOCKS[sec] || [];
    total += all.length;
    shown += all.filter(passesValuationFilters).length;
  }});
  const el = document.getElementById("ht-filter-count");
  if (!el) return;
  if (fpeMax === null && pcfMax === null) {{
    el.textContent = `${{total}} stocks`;
  }} else {{
    const bits = [];
    if (fpeMax !== null) bits.push("Fwd PE ≤" + fpeMax);
    if (pcfMax !== null) bits.push("P/CF ≤" + pcfMax);
    el.textContent = `${{shown}} of ${{total}} · ${{bits.join(" · ")}}`;
  }}
}}
function setFpeMax(val) {{
  fpeMax = (val === "" || val === null) ? null : Number(val);
  document.querySelectorAll("#ht-fpe-filter .ht-filter-btn").forEach(btn => {{
    const m = btn.dataset.max || "";
    const on = fpeMax === null ? m === "" : m !== "" && Number(m) === fpeMax;
    btn.classList.toggle("on", on);
  }});
  Object.keys(stockPageLimits).forEach(k => delete stockPageLimits[k]);
  render();
}}
function setPcfMax(val) {{
  pcfMax = (val === "" || val === null) ? null : Number(val);
  document.querySelectorAll("#ht-pcf-filter .ht-filter-btn").forEach(btn => {{
    const m = btn.dataset.max || "";
    const on = pcfMax === null ? m === "" : m !== "" && Number(m) === pcfMax;
    btn.classList.toggle("on", on);
  }});
  Object.keys(stockPageLimits).forEach(k => delete stockPageLimits[k]);
  render();
}}
document.querySelectorAll("#ht-fpe-filter .ht-filter-btn").forEach(btn => {{
  btn.onclick = () => setFpeMax(btn.dataset.max || "");
}});
document.querySelectorAll("#ht-pcf-filter .ht-filter-btn").forEach(btn => {{
  btn.onclick = () => setPcfMax(btn.dataset.max || "");
}});
function renderStocksForSector(sector, tbody) {{
  const all = sortedStocks(sector);
  tbody.innerHTML = "";
  if (!all.length) {{
    const tr = document.createElement("tr");
    const msg = (fpeMax !== null || pcfMax !== null)
      ? "No stocks match the Fwd PE / P/CF filters."
      : "No stock data for this sector.";
    tr.innerHTML = `<td colspan="${{STOCK_COLS}}" class="iv-expand-meta">${{msg}}</td>`;
    tbody.appendChild(tr);
    return;
  }}
  const limit = stockPageLimits[sector] || Math.min(STOCK_PAGE, all.length);
  const stocks = all.slice(0, limit);
  stocks.forEach(s => {{
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td class="col-rank">${{s.rank || ""}}</td>` +
      `<td class="col-company">${{fmtCompanyCell(s)}}</td>` +
      `<td class="col-industry">${{fmtIndustry(s)}}</td>` +
      `<td class="num col-mcap">₹${{fmtNum(s.market_cap_cr, 1)}} Cr</td>` +
      `<td class="num col-growth">${{metricCell(fmtPct(s.sales_growth_3y), s.growth_rank)}}</td>` +
      `<td class="num col-roce">${{metricCell(fmtPct(s.roce_3y), s.roce_rank)}}</td>` +
      `<td class="num col-pb">${{metricCell(fmtNum(s.pb), s.pb_rank)}}</td>` +
      `<td class="num col-pe">${{fmtPe(s.pe_ratio)}}</td>` +
      `<td class="num col-fpe">${{fmtFpe(s.forward_pe)}}</td>` +
      `<td class="num col-pcf" title="Price ÷ operating cash flow per share">${{fmtNum(s.pcf, 2)}}</td>` +
      `<td class="num col-score">${{Math.round(num(s.total_score) || 0)}}</td>`;
    tbody.appendChild(tr);
  }});
  if (all.length > limit) {{
    const remaining = all.length - limit;
    const tr = document.createElement("tr");
    tr.className = "hw-more-row";
    const step = Math.min(STOCK_PAGE, remaining);
    tr.innerHTML =
      `<td colspan="${{STOCK_COLS}}">` +
      `<button type="button" class="hw-more-btn">Show ${{step}} more (${{remaining}} left)</button>` +
      `</td>`;
    tr.querySelector("button").onclick = (ev) => {{
      ev.stopPropagation();
      stockPageLimits[sector] = limit + step;
      render();
    }};
    tbody.appendChild(tr);
  }}
}}
function renderSectorRow(r, isOpen) {{
  const ind = (r.indicator || "").toUpperCase();
  const stockCount = filteredStocks(r.sector).length;
  const tr = document.createElement("tr");
  tr.className = "iv-sector-row" + (isOpen ? " expanded" : "");
  if (stockCount === 0 && (fpeMax !== null || pcfMax !== null)) {{
    tr.style.opacity = "0.45";
  }}
  tr.innerHTML =
    `<td><span class="expand-hint"></span>${{esc(r.sector)}}</td>` +
    `<td class="num">${{stockCount}}</td>` +
    `<td><span class="badge ${{badgeCls(ind)}}">${{esc(ind)}}</span></td>` +
    `<td class="num">${{fmtPct(r.median_growth_3y)}}</td>` +
    `<td class="num">${{fmtPct(r.median_roce_3y)}}</td>` +
    `<td class="num">${{fmtNum(r.median_pb)}}</td>` +
    `<td class="num">${{fmtNum(r.avg_total_score, 1)}}</td>`;
  tr.onclick = (e) => {{
    if (e.target.closest("a") || e.target.closest("button") || e.target.closest("th.sortable")) return;
    const next = expandedSector === r.sector ? null : r.sector;
    if (next !== r.sector) delete stockPageLimits[r.sector];
    expandedSector = next;
    render();
  }};
  return tr;
}}
function render() {{
  updateFilterCount();
  const tb = document.getElementById("hw-tbody");
  tb.innerHTML = "";
  SECTORS.forEach((r, si) => {{
    const isOpen = expandedSector === r.sector;
    tb.appendChild(renderSectorRow(r, isOpen));
    if (isOpen) {{
      const tr2 = document.createElement("tr");
      tr2.className = "iv-expand-row";
      const td = document.createElement("td");
      td.colSpan = SECTOR_COLS;
      const stockCount = filteredStocks(r.sector).length;
      const filterBits = [];
      if (fpeMax !== null) filterBits.push("Fwd PE ≤" + fpeMax);
      if (pcfMax !== null) filterBits.push("P/CF ≤" + pcfMax);
      const sortCol = STOCK_SORT_COLS.find(c => c.id === stockSortCol);
      const sortLabel = sortCol ? sortCol.label : "Score";
      const sortArrow = stockSortDir < 0 ? "↓" : "↑";
      td.innerHTML =
        `<div class="iv-expand-panel">` +
        `<div class="iv-expand-toolbar">` +
        `<span><strong>${{esc(r.sector)}}</strong> · ${{stockCount}} stocks` +
        `${{MIN_MCAP > 0 ? " · ≥ ₹" + MIN_MCAP + " Cr" : ""}}` +
        `${{filterBits.length ? " · " + filterBits.join(" · ") : ""}}</span>` +
        `<span>Sorted by ${{esc(sortLabel)}} ${{sortArrow}} · click headers to sort</span>` +
        `</div>` +
        `<div class="iv-expand-body">` +
        `<div class="iv-expand-scroll">` +
        `<table class="iv iv-stocks"><colgroup>` +
        `<col style="width:32px"><col style="width:220px"><col style="width:128px">` +
        `<col style="width:72px"><col style="width:88px"><col style="width:72px"><col style="width:56px">` +
        `<col style="width:56px"><col style="width:56px"><col style="width:52px"><col style="width:68px">` +
        `</colgroup><thead id="hw-stocks-head-${{si}}"></thead>` +
        `<tbody id="hw-stocks-${{si}}"></tbody></table></div></div></div>`;
      tr2.appendChild(td);
      tb.appendChild(tr2);
      const stockHead = document.getElementById("hw-stocks-head-" + si);
      const stockBody = document.getElementById("hw-stocks-" + si);
      if (stockHead) renderStockHead(stockHead);
      if (stockBody) renderStocksForSector(r.sector, stockBody);
    }}
  }});
}}
render();
</script>
"""

    if standalone:
        return (
            f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title>{_IV_FONT_LINK}{_IV_CSS}</head><body>{body}</body></html>"
        )
    return f"{_IV_FONT_LINK}{_IV_CSS}{body}"
