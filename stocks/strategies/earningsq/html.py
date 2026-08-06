"""EarningsQ HTML report — friendly live-earnings table."""

from __future__ import annotations

import html

import pandas as pd

from urllib.parse import quote

from stocks.core.text_utils import safe_str, sanitize_website
from stocks.dashboards.interactive_table import wrap_interactive_page
from stocks.shared.links import research_links
from stocks.strategies.earningsq.scores import annotate_quality


def _pct_cell(val, *, pp: bool = False) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return '<td class="eq-muted">—</td>'
    try:
        n = float(val)
    except (TypeError, ValueError):
        return '<td class="eq-muted">—</td>'
    cls = "eq-up" if n > 0 else "eq-down" if n < 0 else "eq-flat"
    suffix = " pp" if pp else "%"
    return f'<td class="{cls}">{n:+.1f}{suffix}</td>'


def _score_cell(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return '<td class="eq-muted">—</td>'
    try:
        n = float(val)
    except (TypeError, ValueError):
        return '<td class="eq-muted">—</td>'
    width = max(4, min(100, abs(n) * 8))
    tone = "eq-bar-pos" if n >= 0 else "eq-bar-neg"
    return (
        f'<td class="eq-score"><div class="eq-bar-wrap">'
        f'<div class="eq-bar {tone}" style="width:{width:.0f}%"></div>'
        f"<span>{n:.2f}</span></div></td>"
    )


def _hours_cell(val: str | None) -> str:
    h = safe_str(val).upper()
    if not h:
        return '<td class="eq-muted">—</td>'
    label = {"BEFORE": "Before open", "DURING": "In session", "AFTER": "After close"}.get(h, h)
    cls = {
        "BEFORE": "eq-hrs-before",
        "DURING": "eq-hrs-during",
        "AFTER": "eq-hrs-after",
    }.get(h, "eq-hrs-other")
    return f'<td><span class="eq-hrs {cls}" title="{html.escape(h)}">{html.escape(label)}</span></td>'


def _badge_cell(tag: str) -> str:
    t = safe_str(tag).lower() or "watch"
    labels = {
        "strong": ("Strong", "eq-badge-strong"),
        "soft": ("Mild", "eq-badge-soft"),
        "fade": ("Caution", "eq-badge-fade"),
        "watch": ("Watch", "eq-badge-watch"),
    }
    label, cls = labels.get(t, ("Watch", "eq-badge-watch"))
    return f'<td><span class="eq-badge {cls}">{label}</span></td>'


def _fmt_when(val) -> str:
    s = safe_str(val)
    if not s:
        return "—"
    # Prefer short "24 Jul · 18:36"
    try:
        ts = pd.Timestamp(s)
        return ts.strftime("%d %b · %H:%M")
    except Exception:
        return s[:16]


def _fmt_price(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    if n >= 1000:
        return f"₹{n:,.1f}"
    if n >= 100:
        return f"₹{n:.1f}"
    return f"₹{n:.2f}"


def _fmt_mcap(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    if n >= 1000:
        return f"₹{n:,.0f} Cr"
    if n >= 100:
        return f"₹{n:.0f} Cr"
    return f"₹{n:.1f} Cr"


def _price_cell(val) -> str:
    text = _fmt_price(val)
    if text == "—":
        return '<td class="eq-muted">—</td>'
    return f'<td class="eq-price">{html.escape(text)}</td>'


def _mcap_cell(val) -> str:
    text = _fmt_mcap(val)
    if text == "—":
        return '<td class="eq-muted">—</td>'
    return f'<td class="eq-mcap">{html.escape(text)}</td>'


def _sector_cell(val) -> str:
    s = safe_str(val)
    if not s:
        return '<td class="eq-muted">—</td>'
    return f'<td class="eq-sector" title="{html.escape(s)}">{html.escape(s)}</td>'


_EQ_CSS = """
<style>
  .eq-wrap {
    font-family: "IBM Plex Sans", "Segoe UI", ui-sans-serif, system-ui, sans-serif;
    color: #1f2937;
    background: #f8fafc;
    padding: 4px 4px 16px;
    border-radius: 12px;
  }
  .eq-legend {
    display:flex; flex-wrap:wrap; gap:10px 16px; align-items:center;
    margin:0 0 14px; padding:10px 12px; border-radius:10px;
    background:#fff; border:1px solid #e2e8f0; color:#475569; font-size:12px;
  }
  .eq-legend strong { color:#0f172a; }
  .eq-toolbar {
    display:flex; flex-wrap:wrap; gap:8px; align-items:center;
    margin:0 0 12px;
  }
  .eq-search {
    flex:1; min-width:180px; max-width:320px;
    padding:8px 12px; border:1px solid #cbd5e1; border-radius:8px;
    font-size:13px; background:#fff; color:#0f172a;
  }
  .eq-search:focus { outline:2px solid #93c5fd; border-color:#60a5fa; }
  .eq-chip {
    border:1px solid #cbd5e1; background:#fff; color:#334155;
    border-radius:999px; padding:6px 12px; font-size:12px; font-weight:600;
    cursor:pointer;
  }
  .eq-chip.is-on { background:#0f172a; color:#fff; border-color:#0f172a; }
  .eq-count { color:#64748b; font-size:12px; margin-left:auto; }
  .eq-picks {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 8px;
    margin: 0 0 14px;
    width: 100%;
  }
  @media (max-width: 1100px) {
    .eq-picks { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  }
  @media (max-width: 720px) {
    .eq-picks { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }
  .eq-pick {
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
  .eq-pick.strong { border-color: #86efac; background: linear-gradient(180deg, #f0fdf4, #fff); }
  .eq-pick.fade { border-color: #fecaca; background: linear-gradient(180deg, #fef2f2, #fff); }
  .eq-pick .eq-pick-top {
    display: flex; align-items: baseline; justify-content: space-between; gap: 6px;
    min-width: 0;
  }
  .eq-pick .eq-pick-ticker {
    color: #0f172a; font-weight: 800; font-size: 12px; letter-spacing: -0.02em;
    line-height: 1.15; min-width: 0; text-decoration: none;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .eq-pick .eq-pick-ticker:hover { color: #1d4ed8; text-decoration: underline; }
  .eq-pick .eq-pick-price {
    font-size: 12px; font-weight: 800; color: #0f172a;
    font-variant-numeric: tabular-nums; white-space: nowrap; flex-shrink: 0;
  }
  .eq-pick .eq-pick-price.eq-muted { font-size: 10px; font-weight: 600; color: #94a3b8; }
  .eq-pick .eq-pick-name {
    color: #64748b; font-size: 10px; line-height: 1.2;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .eq-pick .eq-pick-meta {
    display: flex; flex-wrap: wrap; gap: 3px; align-items: center;
    min-height: 18px;
  }
  .eq-chip-meta {
    display: inline-block; padding: 1px 5px; border-radius: 999px;
    background: #f1f5f9; color: #475569; font-size: 8.5px; font-weight: 700;
    border: 1px solid #e2e8f0; max-width: 100%;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .eq-chip-meta.eq-mcap-chip { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
  .eq-chip-meta.eq-sme-chip {
    background: #ffedd5; border-color: #fdba74; color: #9a3412; font-weight: 700;
  }
  .eq-chip-meta.eq-chip-sector { background: #f8fafc; color: #64748b; max-width: 72px; }
  .eq-chip-meta.eq-chip-strong { background: #dcfce7; border-color: #86efac; color: #166534; }
  .eq-chip-meta.eq-chip-soft { background: #e0f2fe; border-color: #7dd3fc; color: #0369a1; }
  .eq-chip-meta.eq-chip-fade { background: #fee2e2; border-color: #fca5a5; color: #b91c1c; }
  .eq-chip-meta.eq-chip-watch { background: #f1f5f9; border-color: #e2e8f0; color: #475569; }
  .eq-pick .eq-surprise {
    display: flex; align-items: baseline; justify-content: space-between; gap: 6px;
    margin-top: 2px; padding: 5px 7px; border-radius: 8px;
    background: #fff7ed; border: 1px solid #fed7aa;
  }
  .eq-pick.strong .eq-surprise { background: #f0fdf4; border-color: #bbf7d0; }
  .eq-pick .eq-surprise span {
    color: #9a3412; font-size: 9px; font-weight: 700; letter-spacing: .04em;
    text-transform: uppercase;
  }
  .eq-pick.strong .eq-surprise span { color: #166534; }
  .eq-pick .eq-surprise b {
    color: #0f172a; font-size: 14px; font-weight: 800;
    font-variant-numeric: tabular-nums;
  }
  .eq-pick .eq-pick-stats {
    display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 3px; margin-top: 1px;
  }
  .eq-pick .eq-stat {
    background: #f8fafc; border-radius: 6px; padding: 4px 5px 3px;
    border: 1px solid #eef2f7; min-width: 0;
  }
  .eq-pick .eq-stat b {
    display: block; color: #0f172a; font-size: 11px; margin-top: 1px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .eq-pick .eq-stat span {
    color: #64748b; font-size: 8px; font-weight: 700; letter-spacing: .02em;
    text-transform: uppercase;
  }
  .eq-pick .eq-stat.eq-up b { color: #15803d; }
  .eq-pick .eq-stat.eq-down b { color: #b91c1c; }
  .eq-sme-inline {
    display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 999px;
    background: #ffedd5; color: #9a3412; border: 1px solid #fdba74;
    font-size: 10px; font-weight: 700; vertical-align: middle;
  }
  .eq-price {
    font-weight: 700; color: #0f172a; font-variant-numeric: tabular-nums;
  }
  .eq-mcap {
    font-weight: 600; color: #334155; font-variant-numeric: tabular-nums;
  }
  .eq-sector {
    max-width: 140px; overflow: hidden; text-overflow: ellipsis; color: #475569;
  }
  .eq-links {
    display: flex; flex-wrap: wrap; gap: 3px; align-items: center; margin-top: 1px;
  }
  .eq-links a {
    display: inline-block; padding: 1px 5px; border-radius: 5px;
    background: #f1f5f9; color: #334155; font-size: 8.5px; font-weight: 700;
    text-decoration: none; border: 1px solid #e2e8f0;
  }
  .eq-links a:hover { background: #e2e8f0; color: #0f172a; }
  .eq-links a.eq-web { background: #ecfeff; border-color: #a5f3fc; color: #0e7490; }
  .eq-links a.eq-tv { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
  .eq-links a.eq-sc { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
  .eq-ticker .eq-links { margin-top: 4px; }
  .eq-ticker .eq-links a { padding: 2px 7px; font-size: 10.5px; border-radius: 6px; }
  .eq-section-label {
    font-size:11px; font-weight:700; letter-spacing:.04em; text-transform:uppercase;
    color:#64748b; margin:4px 0 8px;
  }
  .eq-table-wrap {
    overflow:auto; max-height: 72vh;
    border:1px solid #e2e8f0; border-radius:12px;
    background:#ffffff;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  }
  table.eq-table { width:100%; border-collapse:collapse; font-size:12.5px; background:#fff; }
  table.eq-table th, table.eq-table td {
    padding:8px 10px; border-bottom:1px solid #f1f5f9; white-space:nowrap;
  }
  table.eq-table thead th {
    position:sticky; top:0; background:#f8fafc; color:#475569;
    font-weight:600; z-index:1; border-bottom:1px solid #e2e8f0;
    text-align:left;
  }
  table.eq-table tbody tr:hover { background:#f8fafc; }
  table.eq-table tr.is-hidden { display:none; }
  .eq-up { color:#15803d; font-weight:600; font-variant-numeric: tabular-nums; }
  .eq-down { color:#b91c1c; font-weight:600; font-variant-numeric: tabular-nums; }
  .eq-flat { color:#334155; font-variant-numeric: tabular-nums; }
  .eq-muted { color:#94a3b8; }
  .eq-ticker { font-weight:700; color:#0f172a; }
  .eq-ticker a { color:#1d4ed8; text-decoration:none; }
  .eq-ticker a:hover { text-decoration:underline; }
  .eq-ticker .eq-meta {
    font-weight:500; color:#64748b; font-size:11px; max-width:200px;
    overflow:hidden; text-overflow:ellipsis;
  }
  .eq-score .eq-bar-wrap { position:relative; min-width:68px; }
  .eq-score .eq-bar {
    position:absolute; left:0; top:2px; bottom:2px; border-radius:3px;
  }
  .eq-bar-pos { background:rgba(34, 197, 94, 0.22); }
  .eq-bar-neg { background:rgba(239, 68, 68, 0.22); }
  .eq-score span { position:relative; z-index:1; padding-left:4px; color:#0f172a; font-weight:600; }
  .eq-hrs {
    display:inline-block; padding:3px 8px; border-radius:999px;
    font-weight:600; font-size:11px; border:1px solid transparent;
  }
  .eq-hrs-before { background:#fff7ed; color:#c2410c; border-color:#fed7aa; }
  .eq-hrs-during { background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe; }
  .eq-hrs-after { background:#f5f3ff; color:#6d28d9; border-color:#ddd6fe; }
  .eq-hrs-other { background:#f1f5f9; color:#475569; border-color:#e2e8f0; }
  .eq-badge {
    display:inline-block; padding:3px 8px; border-radius:999px;
    font-weight:700; font-size:11px;
  }
  .eq-badge-strong { background:#dcfce7; color:#166534; }
  .eq-badge-soft { background:#e0f2fe; color:#0369a1; }
  .eq-badge-fade { background:#fee2e2; color:#b91c1c; }
  .eq-badge-watch { background:#f1f5f9; color:#475569; }
</style>
"""

_EQ_JS = """
<script>
(function(){
  const root = document.currentScript.closest('.eq-wrap') || document;
  const search = root.querySelector('.eq-search');
  const chips = root.querySelectorAll('.eq-chip');
  const rows = root.querySelectorAll('table.eq-table tbody tr');
  const countEl = root.querySelector('.eq-count');
  let filter = 'all';

  function apply() {
    const q = (search && search.value || '').trim().toLowerCase();
    let shown = 0;
    rows.forEach(function(tr){
      const tag = (tr.getAttribute('data-tag') || '').toLowerCase();
      const hay = (tr.getAttribute('data-q') || '').toLowerCase();
      let ok = true;
      if (filter === 'strong') ok = tag === 'strong';
      else if (filter === 'fade') ok = tag === 'fade';
      else if (filter === 'soft') ok = tag === 'soft' || tag === 'strong';
      else if (filter === 'sme') ok = (tr.getAttribute('data-sme') || '') === 'sme';
      if (q && hay.indexOf(q) < 0) ok = false;
      tr.classList.toggle('is-hidden', !ok);
      if (ok) shown += 1;
    });
    if (countEl) countEl.textContent = shown + ' shown';
  }

  chips.forEach(function(btn){
    btn.addEventListener('click', function(){
      filter = btn.getAttribute('data-filter') || 'all';
      chips.forEach(function(b){ b.classList.toggle('is-on', b === btn); });
      apply();
    });
  });
  if (search) search.addEventListener('input', apply);
  apply();
})();
</script>
"""


def _web_url(r: pd.Series, *, ticker: str, name: str) -> str:
    web = sanitize_website(r.get("website"))
    if not web:
        snap = r.get("snapshot")
        if isinstance(snap, dict):
            web = sanitize_website(snap.get("website"))
    if web:
        return web
    q = quote(f"{name or ticker} official website")
    return f"https://www.google.com/search?q={q}"


def _links_html(r: pd.Series, *, compact: bool = False) -> str:
    ticker = safe_str(r.get("ticker")).upper()
    name = safe_str(r.get("name")) or ticker
    sc, tv = research_links(ticker, safe_str(r.get("market")) or "NSE")
    web = _web_url(r, ticker=ticker, name=name)
    cls = "eq-links"
    return (
        f'<div class="{cls}">'
        f'<a class="eq-web" href="{html.escape(web)}" target="_blank" rel="noopener noreferrer" title="Company website">Web</a>'
        f'<a class="eq-tv" href="{html.escape(tv)}" target="_blank" rel="noopener noreferrer" title="TradingView">TV</a>'
        f'<a class="eq-sc" href="{html.escape(sc)}" target="_blank" rel="noopener noreferrer" title="screener.in">SC</a>'
        f"</div>"
    )


def _is_sme_row(r: pd.Series) -> bool:
    if bool(r.get("is_sme")):
        return True
    market = safe_str(r.get("market")).upper()
    return market == "NSE SME" or "SME" in market


def _sme_chip_html(r: pd.Series) -> str:
    if not _is_sme_row(r):
        return ""
    return (
        '<span class="eq-chip-meta eq-sme-chip" title="NSE Emerge / SME listing">SME</span>'
    )


def _sme_inline_html(r: pd.Series) -> str:
    if not _is_sme_row(r):
        return ""
    return '<span class="eq-sme-inline" title="NSE Emerge / SME listing">SME</span>'


def _quality_chip(tag: str) -> str:
    t = safe_str(tag).lower() or "watch"
    labels = {
        "strong": ("Strong", "eq-chip-strong"),
        "soft": ("Mild", "eq-chip-soft"),
        "fade": ("Caution", "eq-chip-fade"),
        "watch": ("Watch", "eq-chip-watch"),
    }
    label, cls = labels.get(t, ("Watch", "eq-chip-watch"))
    return f'<span class="eq-chip-meta {cls}">{label}</span>'


def _stat_pct(label: str, val) -> str:
    tone = ""
    text = "—"
    if val is not None and not (isinstance(val, float) and pd.isna(val)):
        try:
            n = float(val)
            text = f"{n:+.1f}%"
            tone = " eq-up" if n > 0 else " eq-down" if n < 0 else ""
        except (TypeError, ValueError):
            text = "—"
    return (
        f'<div class="eq-stat{tone}"><span>{html.escape(label)}</span>'
        f"<b>{html.escape(text)}</b></div>"
    )


def _fmt_surprise(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        return f"{float(val):+.2f}"
    except (TypeError, ValueError):
        return "—"


def _pick_card(r: pd.Series) -> str:
    ticker = safe_str(r.get("ticker")).upper()
    _sc, tv = research_links(ticker, safe_str(r.get("market")) or "NSE")
    name = html.escape(safe_str(r.get("name")) or ticker)
    tag = safe_str(r.get("quality_tag")).lower() or "watch"
    price_txt = _fmt_price(r.get("price_now"))
    price_cls = "eq-pick-price" if price_txt != "—" else "eq-pick-price eq-muted"
    sector = safe_str(r.get("sector")) or safe_str(r.get("industry"))
    mcap_txt = _fmt_mcap(r.get("market_cap_cr"))

    meta_bits: list[str] = [_quality_chip(tag)]
    if _is_sme_row(r):
        meta_bits.append(_sme_chip_html(r))
    if mcap_txt != "—":
        meta_bits.append(
            f'<span class="eq-chip-meta eq-mcap-chip">{html.escape(mcap_txt)}</span>'
        )
    if sector:
        meta_bits.append(
            f'<span class="eq-chip-meta eq-chip-sector" title="{html.escape(sector)}">'
            f"{html.escape(sector)}</span>"
        )

    surprise_txt = _fmt_surprise(r.get("surprise_score"))
    return f"""
    <div class="eq-pick {html.escape(tag)}">
      <div class="eq-pick-top">
        <a class="eq-pick-ticker" href="{html.escape(tv)}" target="_blank" rel="noopener noreferrer">{html.escape(ticker)}</a>
        <span class="{price_cls}">{html.escape(price_txt)}</span>
      </div>
      <div class="eq-pick-name">{name}</div>
      <div class="eq-pick-meta">{"".join(meta_bits)}</div>
      <div class="eq-surprise"><span>Surprise</span><b>{html.escape(surprise_txt)}</b></div>
      <div class="eq-pick-stats">
        {_stat_pct("Sales YoY", r.get("rev_yoy"))}
        {_stat_pct("Profit YoY", r.get("np_yoy"))}
        {_stat_pct("EPS YoY", r.get("eps_yoy"))}
      </div>
      {_links_html(r)}
    </div>
    """


def build_earningsq_html(
    df: pd.DataFrame,
    *,
    title: str = "EarningsQ — NSE live",
    subtitle: str | None = None,
    standalone: bool = True,
    top_n: int = 12,
    scan_stats: dict | None = None,
) -> str:
    if df is None or df.empty:
        body = (
            '<div class="eq-wrap"><p class="eq-muted" style="padding:12px">'
            "No NSE result prints in this window.</p></div>"
        )
        return wrap_interactive_page(title="", sections_html=_EQ_CSS + body, standalone=standalone)

    work = annotate_quality(df)
    # Top cards: surprise-first (then blend); prefer Strong when enough exist.
    ranked = work.copy()
    if "surprise_score" in ranked.columns:
        sort_cols = ["surprise_score"]
        if "blend_rank" in ranked.columns:
            sort_cols.append("blend_rank")
        ranked = ranked.sort_values(
            sort_cols, ascending=False, kind="mergesort", na_position="last"
        )
    elif "blend_rank" in ranked.columns:
        ranked = ranked.sort_values("blend_rank", ascending=False, kind="mergesort")

    strong = ranked[ranked["quality_tag"] == "strong"]
    picks = strong.head(top_n) if len(strong) >= 3 else ranked.head(top_n)
    picks_html = "".join(_pick_card(r) for _, r in picks.iterrows())

    if "blend_rank" in work.columns:
        work = work.sort_values("blend_rank", ascending=False, kind="mergesort")

    rows_html: list[str] = []
    for _, r in work.iterrows():
        ticker = safe_str(r.get("ticker")).upper()
        _sc, tv = research_links(ticker, safe_str(r.get("market")) or "NSE")
        name = html.escape(safe_str(r.get("name")) or ticker)
        tag = safe_str(r.get("quality_tag")).lower() or "watch"
        sme_flag = "sme" if _is_sme_row(r) else ""
        q = f"{ticker} {safe_str(r.get('name'))} {tag} {sme_flag}".lower()
        rows_html.append(
            f'<tr data-tag="{html.escape(tag)}" data-q="{html.escape(q)}" data-sme="{sme_flag}">'
            f"{_badge_cell(tag)}"
            f'<td class="eq-ticker"><a href="{html.escape(tv)}" target="_blank" rel="noopener noreferrer">{html.escape(ticker)}</a>'
            f"{_sme_inline_html(r)}"
            f'<div class="eq-meta">{name}</div>{_links_html(r, compact=True)}</td>'
            f"{_sector_cell(r.get('sector') or r.get('industry'))}"
            f"{_mcap_cell(r.get('market_cap_cr'))}"
            f"{_price_cell(r.get('price_now'))}"
            f"<td>{html.escape(_fmt_when(r.get('broadcast_at')))}</td>"
            f"{_hours_cell(r.get('market_hours'))}"
            f"{_score_cell(r.get('surprise_score'))}"
            f"{_score_cell(r.get('return_score'))}"
            f"{_pct_cell(r.get('rev_yoy'))}"
            f"{_pct_cell(r.get('np_yoy'))}"
            f"{_pct_cell(r.get('eps_yoy'))}"
            f"{_pct_cell(r.get('ret_1d'))}"
            "</tr>"
        )

    meta = subtitle or f"{len(work)} prints"
    strong_n = int((work["quality_tag"] == "strong").sum())
    fade_n = int((work["quality_tag"] == "fade").sum())
    stats = scan_stats or dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
    raw_n = int(stats.get("nse_announcements_raw") or 0)
    uniq_n = int(stats.get("unique_tickers") or 0)
    uni_n = int(stats.get("nse_equity_universe") or 0)
    coverage = ""
    if raw_n or uniq_n or uni_n:
        parts = []
        if raw_n:
            parts.append(f"{raw_n:,} NSE announcements scanned")
        if uniq_n:
            parts.append(f"{uniq_n:,} result stocks scored")
        if uni_n:
            parts.append(f"{uni_n:,} NSE equities listed")
        coverage = " · ".join(parts)

    section = f"""
{_EQ_CSS}
<div class="eq-wrap">
  <div class="eq-legend">
    <strong>How to read</strong>
    <span>Top cards ranked by <b>Surprise</b> — Sales / Profit / EPS YoY underneath (Watching-style tiles).</span>
    <span><span class="eq-badge eq-badge-strong">Strong</span> good print</span>
    <span><span class="eq-badge eq-badge-soft">Mild</span> positive but softer</span>
    <span><span class="eq-badge eq-badge-fade">Caution</span> big surprise, weak price</span>
    {f'<span><strong>Coverage</strong> {html.escape(coverage)}</span>' if coverage else ''}
  </div>

  <div class="eq-section-label">Top by surprise · {html.escape(meta)} · {len(picks)} cards</div>
  <div class="eq-picks">{picks_html or '<div class="eq-muted">No strong picks in this filter.</div>'}</div>

  <div class="eq-section-label">All prints · {strong_n} strong · {fade_n} caution</div>
  <div class="eq-toolbar">
    <input class="eq-search" type="search" placeholder="Search ticker or name…" />
    <button type="button" class="eq-chip is-on" data-filter="all">All</button>
    <button type="button" class="eq-chip" data-filter="strong">Strong only</button>
    <button type="button" class="eq-chip" data-filter="soft">Positive</button>
    <button type="button" class="eq-chip" data-filter="fade">Caution</button>
    <button type="button" class="eq-chip" data-filter="sme">SME</button>
    <span class="eq-count"></span>
  </div>
  <div class="eq-table-wrap">
    <table class="eq-table">
      <thead>
        <tr>
          <th>Quality</th>
          <th>Stock</th>
          <th>Sector</th>
          <th>Mcap</th>
          <th>Price</th>
          <th>Printed</th>
          <th>When</th>
          <th title="Earnings surprise score">Surprise</th>
          <th title="Post-result price reaction score">Return</th>
          <th>Sales YoY</th>
          <th>Profit YoY</th>
          <th>EPS YoY</th>
          <th>1D %</th>
        </tr>
      </thead>
      <tbody>
        {"".join(rows_html)}
      </tbody>
    </table>
  </div>
</div>
{_EQ_JS}
"""
    # Avoid duplicate H1 from wrap_interactive_page — page already has Streamlit title.
    return wrap_interactive_page(title="", sections_html=section, standalone=standalone)


def earningsq_iframe_height(row_count: int) -> int:
    # Larger cards + toolbar + table
    return min(6200, max(900, 680 + min(row_count, 120) * 32))


__all__ = ["build_earningsq_html", "earningsq_iframe_height"]
