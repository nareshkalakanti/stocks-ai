"""Compact common-stock tiles for Watching (EarningsQ pick-card style, smaller)."""

from __future__ import annotations

import html

import pandas as pd

from stocks.core.text_utils import safe_str, sanitize_website
from stocks.shared.cap_colors import cap_colors_css
from stocks.shared.links import research_links

_COMMON_CSS = """
<style>
  .wc-wrap {
    font-family: "IBM Plex Sans", "Segoe UI", ui-sans-serif, system-ui, sans-serif;
    color: #1f2937;
    padding: 2px 0 10px;
  }
  .wc-head {
    display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
    margin: 0 0 8px; font-size: 11px; font-weight: 700; letter-spacing: .04em;
    text-transform: uppercase; color: #64748b;
  }
  .wc-head span { font-weight: 500; text-transform: none; letter-spacing: 0; color: #94a3b8; }
  .wc-gaps {
    margin: 0 0 8px; font-size: 11px; color: #64748b; line-height: 1.35;
  }
  .wc-gaps b { color: #b45309; font-weight: 700; }
  .wc-gaps.ok { color: #15803d; }
  .wc-picks {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(152px, 1fr));
    gap: 8px;
  }
  .wc-pick {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 9px 10px 8px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    min-height: 0;
  }
  .wc-pick-ticker {
    color: #0f172a; font-weight: 800; font-size: 13px; letter-spacing: -0.02em;
    line-height: 1.2;
  }
  .wc-pick-name {
    color: #64748b; font-size: 10.5px; margin-top: 2px; line-height: 1.25;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .wc-pick-price {
    margin-top: 5px; font-size: 14px; font-weight: 800; color: #0f172a;
    font-variant-numeric: tabular-nums;
  }
  .wc-pick-price.wc-muted { font-size: 11px; font-weight: 600; color: #94a3b8; }
  .wc-pick-meta {
    display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;
  }
  .wc-chip {
    display: inline-block; padding: 2px 6px; border-radius: 999px;
    background: #f1f5f9; color: #475569; font-size: 9px; font-weight: 700;
    border: 1px solid #e2e8f0; max-width: 100%;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .wc-chip-list { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
  .wc-chip-sector { background: #f8fafc; color: #64748b; max-width: 88px; }
  .wc-links {
    display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;
  }
  .wc-links a {
    display: inline-block; padding: 2px 6px; border-radius: 6px;
    background: #f1f5f9; color: #334155; font-size: 9px; font-weight: 700;
    text-decoration: none; border: 1px solid #e2e8f0;
  }
  .wc-links a:hover { background: #e2e8f0; color: #0f172a; }
  .wc-links a.wc-web { background: #ecfeff; border-color: #a5f3fc; color: #0e7490; }
  .wc-links a.wc-tv { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
  .wc-links a.wc-sc { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
</style>
"""

_LIST_CHIP_SHORT = {
    "Early Edge": "Edge",
    "Holdings": "Hold",
    "Negen": "Negen",
    "Niveshaay": "Niveshaay",
}


def _fmt_price(val) -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return '<span class="wc-pick-price wc-muted">—</span>'
    if n != n:
        return '<span class="wc-pick-price wc-muted">—</span>'
    txt = f"₹{n:,.2f}"
    return f'<div class="wc-pick-price">{html.escape(txt)}</div>'


def _fmt_mcap(val) -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return ""
    if n != n or n <= 0:
        return ""
    return f"{n:,.0f} Cr"


def _cap_badge(code: str, label: str = "") -> str:
    c = safe_str(code).upper()
    if not c:
        return ""
    tip = html.escape(label or c)
    return f'<span class="cap-badge cap-{c.lower()}" title="{tip}">{html.escape(c)}</span>'


def _list_chips(on_lists: str) -> str:
    bits: list[str] = []
    for raw in (on_lists or "").split("|"):
        label = safe_str(raw)
        if not label:
            continue
        short = _LIST_CHIP_SHORT.get(label, label)
        bits.append(
            f'<span class="wc-chip wc-chip-list" title="{html.escape(label)}">'
            f"{html.escape(short)}</span>"
        )
    return "".join(bits)


def _links_html(row: pd.Series) -> str:
    ticker = safe_str(row.get("ticker")).upper()
    market = safe_str(row.get("market")) or "NSE"
    sc = safe_str(row.get("sc"))
    tv = safe_str(row.get("tv"))
    if not sc or not tv:
        sc_fb, tv_fb = research_links(ticker, market)
        sc = sc or sc_fb
        tv = tv or tv_fb
    web = sanitize_website(row.get("website"))
    if web and not web.startswith(("http://", "https://")):
        web = f"https://{web.lstrip('/')}"
    bits: list[str] = []
    if web:
        bits.append(
            f'<a class="wc-web" href="{html.escape(web)}" target="_blank" '
            f'rel="noopener noreferrer" title="Company website">Web</a>'
        )
    if tv:
        bits.append(
            f'<a class="wc-tv" href="{html.escape(tv)}" target="_blank" '
            f'rel="noopener noreferrer" title="TradingView">TV</a>'
        )
    if sc:
        bits.append(
            f'<a class="wc-sc" href="{html.escape(sc)}" target="_blank" '
            f'rel="noopener noreferrer" title="screener.in">SC</a>'
        )
    if not bits:
        return ""
    return f'<div class="wc-links">{"".join(bits)}</div>'


def _pick_card(row: pd.Series) -> str:
    ticker = html.escape(safe_str(row.get("ticker")).upper() or "—")
    name = html.escape(safe_str(row.get("name")) or ticker)
    sector = safe_str(row.get("sector"))
    meta: list[str] = []
    cap_html = _cap_badge(safe_str(row.get("cap_code")), safe_str(row.get("cap_label")))
    if cap_html:
        meta.append(cap_html)
    mcap_txt = _fmt_mcap(row.get("market_cap_cr"))
    if mcap_txt:
        meta.append(f'<span class="wc-chip">{html.escape(mcap_txt)}</span>')
    if sector:
        meta.append(
            f'<span class="wc-chip wc-chip-sector" title="{html.escape(sector)}">'
            f"{html.escape(sector)}</span>"
        )
    meta.append(_list_chips(safe_str(row.get("on_lists"))))
    meta_html = "".join(meta)
    return (
        f'<div class="wc-pick">'
        f'<div class="wc-pick-ticker">{ticker}</div>'
        f'<div class="wc-pick-name">{name}</div>'
        f"{_fmt_price(row.get('price'))}"
        f'<div class="wc-pick-meta">{meta_html}</div>'
        f"{_links_html(row)}"
        f"</div>"
    )


def _gaps_html(gap_counts: dict[str, int] | None) -> str:
    if not gap_counts or not gap_counts.get("total"):
        return ""
    if not gap_counts.get("any_rows"):
        return '<div class="wc-gaps ok">No gaps in these tiles.</div>'
    bits: list[str] = []
    for key, label in (("price", "price"), ("sector", "sector"), ("mcap", "mcap"), ("web", "web")):
        n = int(gap_counts.get(key) or 0)
        if n:
            bits.append(f"{label} <b>{n}</b>")
    inner = " · ".join(bits)
    head = f"<b>{gap_counts['any_rows']}</b> need Fill missing"
    return f'<div class="wc-gaps">{head} · {inner}</div>' if inner else f'<div class="wc-gaps">{head}</div>'


def build_watching_common_html(
    df: pd.DataFrame,
    *,
    total_common: int | None = None,
    limit: int = 12,
    gap_counts: dict[str, int] | None = None,
) -> str:
    work = df if df is not None else pd.DataFrame()
    if work.empty:
        return ""

    shown = len(work)
    total = total_common if total_common is not None else shown
    count_label = f"showing {shown} of {total}" if total > shown else str(shown)
    picks_html = "".join(_pick_card(row) for _, row in work.iterrows())
    cap_css = cap_colors_css(include_chip=False, include_gov_filter=False)
    gaps_html = _gaps_html(gap_counts)
    return (
        f"{cap_css}{_COMMON_CSS}"
        f'<div class="wc-wrap">'
        f'<div class="wc-head">On 2+ lists<span>{html.escape(count_label)}</span></div>'
        f"{gaps_html}"
        f'<div class="wc-picks">{picks_html}</div>'
        f"</div>"
    )


def watching_common_iframe_height(card_count: int) -> int:
    if card_count <= 0:
        return 0
    rows = (card_count + 5) // 6
    return min(280, 72 + rows * 118)
