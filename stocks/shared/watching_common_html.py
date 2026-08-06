"""Compact common-stock tiles for Watching / SuperStars (EarningsQ pick-card style)."""

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
    padding: 0 0 4px;
    overflow: visible;
  }
  .wc-head {
    display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
    margin: 0 0 6px; font-size: 11px; font-weight: 700; letter-spacing: .04em;
    text-transform: uppercase; color: #64748b;
  }
  .wc-head span { font-weight: 500; text-transform: none; letter-spacing: 0; color: #94a3b8; }
  .wc-gaps {
    margin: 0 0 6px; font-size: 11px; color: #64748b; line-height: 1.35;
  }
  .wc-gaps b { color: #b45309; font-weight: 700; }
  .wc-gaps.ok { color: #15803d; }
  .wc-picks {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 8px;
    width: 100%;
  }
  @media (max-width: 1100px) {
    .wc-picks { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  }
  @media (max-width: 720px) {
    .wc-picks { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }
  .wc-pick {
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 8px 9px 7px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .wc-pick-top {
    display: flex; align-items: baseline; justify-content: space-between; gap: 6px;
    min-width: 0;
  }
  .wc-pick-ticker {
    color: #0f172a; font-weight: 800; font-size: 12px; letter-spacing: -0.02em;
    line-height: 1.15; min-width: 0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .wc-pick-price {
    font-size: 12px; font-weight: 800; color: #0f172a;
    font-variant-numeric: tabular-nums; white-space: nowrap; flex-shrink: 0;
  }
  .wc-pick-price.wc-muted { font-size: 10px; font-weight: 600; color: #94a3b8; }
  .wc-pick-name {
    color: #64748b; font-size: 10px; line-height: 1.2;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .wc-pick-meta {
    display: flex; flex-wrap: wrap; gap: 3px; align-items: center;
    min-height: 18px;
  }
  .wc-chip {
    display: inline-block; padding: 1px 5px; border-radius: 999px;
    background: #f1f5f9; color: #475569; font-size: 8.5px; font-weight: 700;
    border: 1px solid #e2e8f0; max-width: 100%;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .wc-chip-list { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
  .wc-chip-sector { background: #f8fafc; color: #64748b; max-width: 72px; }
  .wc-pick-foot {
    display: flex; flex-wrap: wrap; gap: 3px; align-items: center; margin-top: 1px;
  }
  .wc-pick-foot a {
    display: inline-block; padding: 1px 5px; border-radius: 5px;
    background: #f1f5f9; color: #334155; font-size: 8.5px; font-weight: 700;
    text-decoration: none; border: 1px solid #e2e8f0;
  }
  .wc-pick-foot a:hover { background: #e2e8f0; color: #0f172a; }
  .wc-pick-foot a.wc-web { background: #ecfeff; border-color: #a5f3fc; color: #0e7490; }
  .wc-pick-foot a.wc-tv { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
  .wc-pick-foot a.wc-sc { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
  .cap-badge { font-size: 8.5px !important; padding: 1px 5px !important; }
</style>
"""

_LIST_CHIP_SHORT = {
    "Early Edge": "Edge",
    "Holdings": "Hold",
    "Negen": "Negen",
    "Niveshaay": "Niveshaay",
}


def _fmt_price_inline(val) -> str:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return '<span class="wc-pick-price wc-muted">—</span>'
    if n != n:
        return '<span class="wc-pick-price wc-muted">—</span>'
    return f'<span class="wc-pick-price">₹{n:,.2f}</span>'


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


def _list_chips(on_lists: str, *, chip_short: dict[str, str] | None = None) -> str:
    short_map = chip_short if chip_short is not None else _LIST_CHIP_SHORT
    bits: list[str] = []
    for raw in (on_lists or "").split("|"):
        label = safe_str(raw)
        if not label:
            continue
        short = short_map.get(label, label)
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
    return "".join(bits)


def _pick_card(row: pd.Series, *, chip_short: dict[str, str] | None = None) -> str:
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
    meta.append(_list_chips(safe_str(row.get("on_lists")), chip_short=chip_short))
    links = _links_html(row)
    return (
        f'<div class="wc-pick">'
        f'<div class="wc-pick-top">'
        f'<span class="wc-pick-ticker">{ticker}</span>'
        f"{_fmt_price_inline(row.get('price'))}"
        f"</div>"
        f'<div class="wc-pick-name">{name}</div>'
        f'<div class="wc-pick-meta">{"".join(meta)}</div>'
        f'<div class="wc-pick-foot">{links}</div>'
        f"</div>"
    )


def _gaps_html(gap_counts: dict[str, int] | None) -> str:
    if not gap_counts or not gap_counts.get("total"):
        return ""
    if not gap_counts.get("any_rows"):
        return ""
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
    include_heading: bool = True,
    heading: str = "On 2+ lists",
    chip_short: dict[str, str] | None = None,
) -> str:
    del limit  # caller already slices the frame
    work = df if df is not None else pd.DataFrame()
    if work.empty:
        return ""

    shown = len(work)
    total = total_common if total_common is not None else shown
    count_label = f"showing {shown} of {total}" if total > shown else str(shown)
    picks_html = "".join(
        _pick_card(row, chip_short=chip_short) for _, row in work.iterrows()
    )
    cap_css = cap_colors_css(include_chip=False, include_gov_filter=False)
    gaps_html = _gaps_html(gap_counts)
    head = (
        f'<div class="wc-head">{html.escape(heading)}'
        f"<span>{html.escape(count_label)}</span></div>"
        if include_heading
        else ""
    )
    return (
        f"{cap_css}{_COMMON_CSS}"
        f'<div class="wc-wrap">'
        f"{head}"
        f"{gaps_html}"
        f'<div class="wc-picks">{picks_html}</div>'
        f"</div>"
    )
