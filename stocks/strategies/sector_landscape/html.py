"""Dark sector / industry landscape dashboard (grid + detail panel)."""

from __future__ import annotations

import html
import json

_LANDSCAPE_CSS = """
<style>
  :root {
    --bg: #0c0f14;
    --panel: #12161e;
    --card: #151a24;
    --card-hover: #1a2030;
    --border: #252b38;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --dim: #64748b;
    --green: #22c55e;
    --red: #ef4444;
    --accent: #38bdf8;
    --bench: rgba(255,255,255,0.55);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
  }
  .sl-wrap { padding: 18px 20px 28px; min-height: 100vh; }
  .sl-header { margin-bottom: 16px; }
  .sl-title { font-size: 22px; font-weight: 700; margin: 0 0 4px; letter-spacing: -0.02em; }
  .sl-sub { color: var(--dim); font-size: 12px; margin: 0; }
  .sl-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    margin: 16px 0 18px;
    padding: 12px 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
  }
  .sl-search {
    flex: 1 1 200px;
    min-width: 180px;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--card);
    color: var(--text);
    font-size: 13px;
  }
  .sl-search::placeholder { color: var(--dim); }
  .sl-pills { display: inline-flex; gap: 4px; flex-wrap: wrap; }
  .sl-pill {
    padding: 6px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  .sl-pill.active {
    background: rgba(56,189,248,0.12);
    border-color: rgba(56,189,248,0.35);
    color: var(--accent);
  }
  .sl-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }
  .sl-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 14px 12px;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s, transform 0.1s;
  }
  .sl-card:hover, .sl-card.active {
    border-color: rgba(56,189,248,0.45);
    background: var(--card-hover);
  }
  .sl-card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
    margin-bottom: 2px;
  }
  .sl-card-name {
    font-size: 14px;
    font-weight: 600;
    line-height: 1.3;
    color: var(--text);
  }
  .sl-card-ret {
    font-size: 14px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .sl-card-ret.up { color: var(--green); }
  .sl-card-ret.down { color: var(--red); }
  .sl-card-meta { color: var(--dim); font-size: 11px; margin-bottom: 10px; }
  .sl-chart { width: 100%; height: 72px; display: block; }
  .sl-line-sector { fill: none; stroke: var(--green); stroke-width: 2; }
  .sl-line-bench { fill: none; stroke: var(--bench); stroke-width: 1.5; stroke-dasharray: 4 4; }
  .sl-layout { display: grid; grid-template-columns: 1fr; gap: 0; }
  .sl-layout.panel-open { grid-template-columns: 1fr 340px; gap: 16px; }
  @media (max-width: 1100px) {
    .sl-layout.panel-open { grid-template-columns: 1fr; }
  }
  .sl-panel {
    display: none;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    max-height: calc(100vh - 40px);
    overflow-y: auto;
    position: sticky;
    top: 12px;
  }
  .sl-panel.open { display: block; }
  .sl-panel-title { font-size: 18px; font-weight: 700; margin: 0 0 6px; }
  .sl-panel-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 12px;
  }
  .sl-panel-stats .up { color: var(--green); font-weight: 600; }
  .sl-panel-stats .down { color: var(--red); font-weight: 600; }
  .sl-panel-chart { width: 100%; height: 120px; margin-bottom: 14px; }
  .sl-stock-list { list-style: none; margin: 0; padding: 0; }
  .sl-stock {
    display: grid;
    grid-template-columns: 24px 1fr 56px 72px 72px;
    gap: 8px;
    align-items: center;
    padding: 9px 0;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
  }
  .sl-stock:last-child { border-bottom: none; }
  .sl-stock-rank { color: var(--dim); font-weight: 600; text-align: center; }
  .sl-stock-name { font-weight: 600; line-height: 1.25; }
  .sl-stock-sub { color: var(--dim); font-size: 10px; font-weight: 500; }
  .sl-stock-spark { width: 56px; height: 28px; }
  .sl-stock-ret { text-align: right; font-weight: 700; color: var(--green); font-variant-numeric: tabular-nums; }
  .sl-stock-ret.neg { color: var(--red); }
  .sl-stock-price { text-align: right; color: var(--muted); font-variant-numeric: tabular-nums; }
  .sl-empty { color: var(--dim); padding: 40px; text-align: center; }
  .sl-close {
    float: right;
    background: transparent;
    border: none;
    color: var(--dim);
    font-size: 18px;
    cursor: pointer;
    padding: 0 4px;
  }
  a.sl-link {
    color: var(--accent);
    text-decoration: none;
    font-size: 10px;
    font-weight: 600;
    margin-left: 4px;
  }
  .sl-show-all {
    margin-top: 10px;
    padding: 0;
    border: none;
    background: none;
    color: var(--accent);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  .sl-show-all:hover { text-decoration: underline; }
</style>
"""

_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
)


def landscape_iframe_height(group_count: int, *, panel_open: bool = False) -> int:
    rows = max(1, (group_count + 2) // 3)
    base = min(2400, max(520, 200 + rows * 130))
    if panel_open:
        base = max(base, 680)
    return base


def build_sector_landscape_html(
    payload: dict,
    *,
    title: str = "NSE Sector Landscape",
    subtitle: str = "",
    standalone: bool = True,
) -> str:
    if not payload or payload.get("error"):
        err = html.escape(str(payload.get("error") if payload else "No data"))
        body = f'<div class="sl-wrap"><div class="sl-empty">{err}</div></div>'
    else:
        data_json = json.dumps(payload, separators=(",", ":"))
        meta = html.escape(subtitle) if subtitle else ""
        sub_html = (
            f'<p class="sl-sub">{meta} · as of {html.escape(str(payload.get("as_of", "")))}</p>'
            if meta
            else ""
        )
        body = f"""
<div class="sl-wrap">
  <div class="sl-header">
    <h1 class="sl-title">{html.escape(title)}</h1>
    {sub_html}
  </div>
  <div class="sl-toolbar">
    <input class="sl-search" id="sl-search" type="search" placeholder="Search sectors…" />
    <div class="sl-pills" id="sl-type-pills">
      <button class="sl-pill active" data-type="all">All</button>
      <button class="sl-pill" data-type="sector">Sectors</button>
      <button class="sl-pill" data-type="industry">Industries</button>
    </div>
    <div class="sl-pills" id="sl-mover-pills">
      <button class="sl-pill active" data-mover="all">All</button>
      <button class="sl-pill" data-mover="top">Top 20</button>
      <button class="sl-pill" data-mover="bottom">Bottom 20</button>
    </div>
  </div>
  <div class="sl-layout" id="sl-layout">
    <div id="sl-grid" class="sl-grid"></div>
    <aside class="sl-panel" id="sl-panel"></aside>
  </div>
</div>
<script>
const DATA = {data_json};
let typeFilter = "all";
let moverFilter = "all";
let searchQuery = "";
let selectedKey = null;
let stocksExpanded = false;

function esc(s) {{
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
}}
function renderStockRow(s, g) {{
  const sp = linePath(s.spark || [], 56, 28, 2);
  const up = Number(s.return_pct) >= 0;
  const links = [];
  if (s.sc) links.push(`<a class="sl-link" href="${{esc(s.sc)}}" target="_blank" rel="noopener">SC</a>`);
  if (s.tv) links.push(`<a class="sl-link" href="${{esc(s.tv)}}" target="_blank" rel="noopener">TV</a>`);
  return `<li class="sl-stock">` +
    `<span class="sl-stock-rank">${{s.rank || ""}}</span>` +
    `<div><div class="sl-stock-name">${{esc(s.name || s.ticker)}}${{links.join("")}}</div>` +
    `<div class="sl-stock-sub">${{esc(s.industry || g.industry || "")}}</div></div>` +
    `<svg class="sl-stock-spark" viewBox="0 0 56 28"><path class="sl-line-sector" d="${{sp}}"/></svg>` +
    `<span class="sl-stock-ret ${{up ? '' : 'neg'}}">${{fmtRet(s.return_pct)}}</span>` +
    `<span class="sl-stock-price">₹${{Number(s.price || 0).toFixed(2)}}</span>` +
    `</li>`;
}}
function bindPanelActions() {{
  const close = document.getElementById("sl-close");
  if (close) close.onclick = (e) => {{
    e.stopPropagation();
    selectedKey = null;
    stocksExpanded = false;
    document.getElementById("sl-panel").classList.remove("open");
    document.getElementById("sl-layout").classList.remove("panel-open");
    render();
  }};
  const toggle = document.getElementById("sl-show-all");
  if (toggle) toggle.onclick = (e) => {{
    e.stopPropagation();
    stocksExpanded = !stocksExpanded;
    const panel = document.getElementById("sl-panel");
    panel.innerHTML = renderPanel(findGroup(selectedKey));
    bindPanelActions();
  }};
}}
function fmtRet(v) {{
  const n = Number(v);
  if (isNaN(n)) return "—";
  return (n >= 0 ? "+" : "") + n.toFixed(2) + "%";
}}
function allGroups() {{
  return [...(DATA.sector_groups || []), ...(DATA.industry_groups || [])];
}}
function filteredGroups() {{
  let groups = allGroups();
  if (typeFilter === "sector") groups = DATA.sector_groups || [];
  if (typeFilter === "industry") groups = DATA.industry_groups || [];
  if (searchQuery) {{
    const q = searchQuery.toLowerCase();
    groups = groups.filter(g => String(g.key || "").toLowerCase().includes(q));
  }}
  groups = [...groups].sort((a, b) => (b.return_pct || 0) - (a.return_pct || 0));
  if (moverFilter === "top") groups = groups.slice(0, 20);
  if (moverFilter === "bottom") groups = groups.slice(-20).reverse();
  return groups;
}}
function linePath(points, w, h, pad) {{
  if (!points || !points.length) return "";
  const vals = points.map(p => Number(p.v));
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  return points.map((p, i) => {{
    const x = pad + (i / Math.max(1, points.length - 1)) * (w - pad * 2);
    const y = h - pad - ((Number(p.v) - min) / span) * (h - pad * 2);
    return (i ? "L" : "M") + x.toFixed(1) + "," + y.toFixed(1);
  }}).join(" ");
}}
function groupId(g) {{
  return g.id || g.key;
}}
function renderCard(g) {{
  const up = Number(g.return_pct) >= 0;
  const bench = DATA.benchmark_series || [];
  const sectorPath = linePath(g.series, 260, 72, 4);
  const benchPath = linePath(bench, 260, 72, 4);
  const gid = groupId(g);
  const active = selectedKey === gid ? " active" : "";
  return `<div class="sl-card${{active}}" data-key="${{esc(gid)}}">` +
    `<div class="sl-card-head">` +
    `<div class="sl-card-name">${{esc(g.key)}}</div>` +
    `<div class="sl-card-ret ${{up ? 'up' : 'down'}}">${{fmtRet(g.return_pct)}}</div>` +
    `</div>` +
    `<div class="sl-card-meta">${{g.stock_count || 0}} stocks</div>` +
    `<svg class="sl-chart" viewBox="0 0 260 72" preserveAspectRatio="none">` +
    (benchPath ? `<path class="sl-line-bench" d="${{benchPath}}"/>` : "") +
    (sectorPath ? `<path class="sl-line-sector" d="${{sectorPath}}"/>` : "") +
    `</svg></div>`;
}}
function renderPanel(g) {{
  if (!g) return "";
  const benchRet = DATA.benchmark_return_pct;
  const bench = Number(benchRet);
  const benchCls = bench >= 0 ? "up" : "down";
  const secCls = Number(g.return_pct) >= 0 ? "up" : "down";
  const sectorPath = linePath(g.series, 300, 120, 6);
  const benchPath = linePath(DATA.benchmark_series || [], 300, 120, 6);
  const allStocks = g.stocks || [];
  const limit = stocksExpanded ? allStocks.length : Math.min(10, allStocks.length);
  let stocks = allStocks.slice(0, limit).map(s => renderStockRow(s, g)).join("");
  let more = "";
  if (allStocks.length > 10) {{
    const label = stocksExpanded
      ? "Show top 10"
      : `Show all ${{g.stock_count || allStocks.length}} stocks`;
    more = `<button type="button" class="sl-show-all" id="sl-show-all">${{label}}</button>`;
  }}
  return `<button class="sl-close" id="sl-close" title="Close">×</button>` +
    `<h2 class="sl-panel-title">${{esc(g.key)}}</h2>` +
    `<div class="sl-panel-stats">` +
    `<span class="${{secCls}}">Sector: ${{fmtRet(g.return_pct)}}</span>` +
    `<span class="${{benchCls}}">${{esc(DATA.benchmark || 'NIFTY 500')}}: ${{fmtRet(benchRet)}}</span>` +
    `<span>${{g.stock_count}} stocks</span>` +
  `</div>` +
    `<svg class="sl-panel-chart" viewBox="0 0 300 120" preserveAspectRatio="none">` +
    (benchPath ? `<path class="sl-line-bench" d="${{benchPath}}"/>` : "") +
    (sectorPath ? `<path class="sl-line-sector" d="${{sectorPath}}"/>` : "") +
    `</svg>` +
    `<div class="sl-card-meta">${{g.up_count || 0}} stocks up · ${{g.down_count || 0}} down</div>` +
    `<ul class="sl-stock-list">${{stocks}}</ul>${{more}}`;
}}
function findGroup(key) {{
  return allGroups().find(g => groupId(g) === key);
}}
function render() {{
  const groups = filteredGroups();
  const grid = document.getElementById("sl-grid");
  if (!groups.length) {{
    grid.innerHTML = '<div class="sl-empty">No groups match filters.</div>';
  }} else {{
    grid.innerHTML = groups.map(renderCard).join("");
    grid.querySelectorAll(".sl-card").forEach(el => {{
      el.onclick = () => {{
        selectedKey = el.dataset.key;
        stocksExpanded = false;
        document.getElementById("sl-layout").classList.add("panel-open");
        const panel = document.getElementById("sl-panel");
        panel.classList.add("open");
        panel.innerHTML = renderPanel(findGroup(selectedKey));
        bindPanelActions();
        render();
      }};
    }});
  }}
  const panel = document.getElementById("sl-panel");
  if (selectedKey && panel.classList.contains("open")) {{
    panel.innerHTML = renderPanel(findGroup(selectedKey));
    bindPanelActions();
  }}
}}
document.getElementById("sl-search").oninput = (e) => {{ searchQuery = e.target.value.trim(); render(); }};
document.querySelectorAll("#sl-type-pills .sl-pill").forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll("#sl-type-pills .sl-pill").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    typeFilter = btn.dataset.type;
    render();
  }};
}});
document.querySelectorAll("#sl-mover-pills .sl-pill").forEach(btn => {{
  btn.onclick = () => {{
    document.querySelectorAll("#sl-mover-pills .sl-pill").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    moverFilter = btn.dataset.mover;
    render();
  }};
}});
render();
</script>
"""

    if standalone:
        return (
            f"<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title>{_FONT_LINK}{_LANDSCAPE_CSS}</head>"
            f"<body>{body}</body></html>"
        )
    return f"{_FONT_LINK}{_LANDSCAPE_CSS}{body}"
