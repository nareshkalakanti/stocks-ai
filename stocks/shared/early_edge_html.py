"""Early Edge Watching — interactive HTML table with Cap / Sector filters."""

from __future__ import annotations

import html
import json

import pandas as pd

from stocks.core.json_utils import json_dumps, json_safe_scalar
from stocks.core.text_utils import safe_str
from stocks.dashboards.report_html import _REPORT_CSS

_EDGE_CSS = """
<style>
  .ee-wrap { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color: #111827; }
  .ee-toolbar {
    display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center;
    margin: 0 0 12px; padding: 10px 12px; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 10px;
  }
  .ee-search {
    flex: 1 1 180px; min-width: 140px; max-width: 280px;
    padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 13px;
  }
  .ee-filter-group { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .ee-filter-label {
    font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: #6b7280; margin-right: 2px;
  }
  .ee-chip {
    border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 999px;
    padding: 4px 10px; font-size: 12px; font-weight: 600; cursor: pointer; line-height: 1.3;
  }
  .ee-chip:hover { border-color: #9f1239; color: #9f1239; }
  .ee-chip.active { background: #9f1239; border-color: #9f1239; color: #fff; }
  .ee-sector-select {
    padding: 6px 10px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 12px; background: #fff; max-width: 220px;
  }
  .ee-count { font-size: 12px; color: #6b7280; margin-left: auto; white-space: nowrap; }
  .ee-table-wrap { overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 10px; background: #fff; }
  .ee-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .ee-table th {
    text-align: left; padding: 9px 10px; background: #f9fafb; border-bottom: 1px solid #e5e7eb;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: #6b7280;
    position: sticky; top: 0; z-index: 1; cursor: pointer; user-select: none; white-space: nowrap;
  }
  .ee-table th .sort-ind { opacity: 0.35; margin-left: 4px; font-size: 10px; }
  .ee-table th .sort-ind.active { opacity: 1; color: #9f1239; }
  .ee-table td { padding: 8px 10px; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
  .ee-table tr:hover td { background: #fff7f9; }
  .ee-co { font-weight: 650; color: #111827; }
  .ee-ticker { font-size: 11px; color: #6b7280; margin-top: 2px; }
  .ee-tags { display: inline-flex; gap: 4px; margin-left: 6px; vertical-align: middle; }
  .ee-tag {
    display: inline-block; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;
    color: #9f1239; background: #ffe4e6; text-transform: uppercase; letter-spacing: 0.04em;
  }
  .ee-tag-sme { color: #9a3412; background: #ffedd5; }
  .ee-links a {
    display: inline-block; margin-right: 4px; padding: 2px 7px; border-radius: 4px;
    background: #f3f4f6; color: #1d4ed8; text-decoration: none; font-size: 11px; font-weight: 700;
  }
  .ee-links a:hover { background: #dbeafe; }
  .ee-num { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .ee-cap {
    display: inline-block; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;
    background: #f3f4f6; color: #374151;
  }
  .ee-cap-nc { background: #fef3c7; color: #92400e; }
  .ee-cap-mic { background: #ffedd5; color: #9a3412; }
  .ee-cap-sc { background: #dbeafe; color: #1d4ed8; }
  .ee-cap-mc { background: #ede9fe; color: #5b21b6; }
  .ee-cap-lc { background: #d1fae5; color: #065f46; }
  .ee-muted { color: #9ca3af; }
  .ee-empty { padding: 28px; text-align: center; color: #6b7280; font-size: 13px; }
</style>
"""


def _rows_payload(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, row in df.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        market = safe_str(row.get("market")).upper() or "NSE"
        rows.append(
            {
                "ticker": ticker,
                "name": safe_str(row.get("name")) or ticker,
                "market": market,
                "sector": safe_str(row.get("sector")) or "",
                "sub_sector": safe_str(row.get("sub_sector"))
                or safe_str(row.get("industry"))
                or "",
                "industry": safe_str(row.get("industry")) or "",
                "market_cap_cr": json_safe_scalar(row.get("market_cap_cr")),
                "cap_code": safe_str(row.get("cap_code")) or "",
                "cap_label": safe_str(row.get("cap_label")) or "",
                "is_edge": True,
                "is_sme": market == "NSE SME",
                "sc": safe_str(row.get("sc")) or "",
                "tv": safe_str(row.get("tv")) or "",
                "matched_from": safe_str(row.get("holding_entity")) or "",
            }
        )
    return rows


def build_early_edge_html(
    df: pd.DataFrame,
    *,
    title: str = "Early Edge",
    standalone: bool = False,
) -> str:
    work = df if df is not None else pd.DataFrame()
    payload = _rows_payload(work)
    sectors = sorted(
        {
            safe_str(r.get("sector"))
            for r in payload
            if safe_str(r.get("sector"))
        }
    )
    data_json = json_dumps(payload, separators=(",", ":"))
    sectors_json = json.dumps(sectors, separators=(",", ":"))
    title_esc = html.escape(title)

    body = f"""
{_EDGE_CSS}
<div class="ee-wrap" id="ee-root">
  <div class="ee-toolbar">
    <input type="search" class="ee-search" id="ee-search" placeholder="Search ticker, name, sector…" autocomplete="off" />
    <div class="ee-filter-group" id="ee-cap-filter" role="group" aria-label="Cap filter">
      <span class="ee-filter-label">Cap</span>
      <button type="button" class="ee-chip active" data-cap="">All</button>
      <button type="button" class="ee-chip" data-cap="NC" title="Nano Cap (&lt; 100 Cr)">NC</button>
      <button type="button" class="ee-chip" data-cap="MIC" title="Micro Cap (100–500 Cr)">MIC</button>
      <button type="button" class="ee-chip" data-cap="SC" title="Small Cap (500–5,000 Cr)">SC</button>
      <button type="button" class="ee-chip" data-cap="MC" title="Mid Cap (5,000–20,000 Cr)">MC</button>
      <button type="button" class="ee-chip" data-cap="LC" title="Large Cap (≥ 20,000 Cr)">LC</button>
    </div>
    <div class="ee-filter-group">
      <span class="ee-filter-label">Sector</span>
      <select class="ee-sector-select" id="ee-sector" aria-label="Sector filter">
        <option value="">All sectors</option>
      </select>
    </div>
    <span class="ee-count" id="ee-count"></span>
  </div>
  <div class="ee-table-wrap">
    <table class="ee-table">
      <thead><tr id="ee-head"></tr></thead>
      <tbody id="ee-body"></tbody>
    </table>
  </div>
</div>
<script>
(function() {{
  const DATA = {data_json};
  const SECTORS = {sectors_json};
  const COLS = [
    {{ id: "company", label: "Company", sort: "name" }},
    {{ id: "sector", label: "Sector", sort: "sector" }},
    {{ id: "sub_sector", label: "Sub-sector", sort: "sub_sector" }},
    {{ id: "market_cap_cr", label: "Mcap Cr", sort: "market_cap_cr", num: true }},
    {{ id: "cap_code", label: "Cap", sort: "cap_code" }},
    {{ id: "market", label: "Market", sort: "market" }},
    {{ id: "links", label: "Links", sort: null }},
  ];
  let searchQuery = "";
  let capFilters = new Set();
  let sectorFilter = "";
  let sortCol = "sector";
  let sortDir = 1;

  const sectorEl = document.getElementById("ee-sector");
  if (sectorEl) {{
    SECTORS.forEach(s => {{
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      sectorEl.appendChild(opt);
    }});
  }}

  function esc(s) {{
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
  }}
  function num(v) {{
    if (v == null || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }}
  function fmtMcap(v) {{
    const n = num(v);
    if (n == null) return '<span class="ee-muted">—</span>';
    return `<span class="ee-num">${{n.toLocaleString("en-IN", {{ maximumFractionDigits: 1 }})}}</span>`;
  }}
  function fmtCap(code, label) {{
    const c = String(code || "").toUpperCase();
    if (!c) return '<span class="ee-muted">—</span>';
    const tip = esc(label || c);
    return `<span class="ee-cap ee-cap-${{c.toLowerCase()}}" title="${{tip}}">${{esc(c)}}</span>`;
  }}
  function companyCell(r) {{
    const tags = ['<span class="ee-tag" title="Early Edge watchlist">Edge</span>'];
    if (r.is_sme) tags.push('<span class="ee-tag ee-tag-sme" title="NSE Emerge / SME">SME</span>');
    return (
      `<div class="ee-co">${{esc(r.name || r.ticker)}}` +
      `<span class="ee-tags">${{tags.join("")}}</span></div>` +
      `<div class="ee-ticker">${{esc(r.ticker)}}</div>`
    );
  }}
  function linksCell(r) {{
    const bits = [];
    if (r.sc) bits.push(`<a href="${{esc(r.sc)}}" target="_blank" rel="noopener noreferrer">SC</a>`);
    if (r.tv) bits.push(`<a href="${{esc(r.tv)}}" target="_blank" rel="noopener noreferrer">TV</a>`);
    return bits.length ? `<span class="ee-links">${{bits.join("")}}</span>` : "—";
  }}
  function cell(col, r) {{
    switch (col.id) {{
      case "company": return companyCell(r);
      case "sector": return esc(r.sector) || '<span class="ee-muted">—</span>';
      case "sub_sector": return esc(r.sub_sector) || '<span class="ee-muted">—</span>';
      case "market_cap_cr": return fmtMcap(r.market_cap_cr);
      case "cap_code": return fmtCap(r.cap_code, r.cap_label);
      case "market": return esc(r.market) || "—";
      case "links": return linksCell(r);
      default: return "—";
    }}
  }}
  function capOk(r) {{
    if (!capFilters.size) return true;
    const c = String(r.cap_code || "").toUpperCase();
    return capFilters.has(c);
  }}
  function sectorOk(r) {{
    if (!sectorFilter) return true;
    return String(r.sector || "") === sectorFilter;
  }}
  function searchOk(r) {{
    if (!searchQuery) return true;
    const hay = [r.ticker, r.name, r.sector, r.sub_sector, r.industry, r.market, r.matched_from]
      .map(v => String(v || "").toLowerCase()).join(" ");
    return hay.includes(searchQuery);
  }}
  function compare(a, b) {{
    const col = COLS.find(c => c.id === sortCol) || COLS[0];
    const key = col.sort || "name";
    let av = a[key];
    let bv = b[key];
    if (col.num) {{
      av = num(av); bv = num(bv);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (av - bv) * sortDir;
    }}
    av = String(av || "").toLowerCase();
    bv = String(bv || "").toLowerCase();
    if (av < bv) return -1 * sortDir;
    if (av > bv) return 1 * sortDir;
    return String(a.ticker || "").localeCompare(String(b.ticker || ""));
  }}
  function syncCapButtons() {{
    const on = capFilters.size > 0;
    document.querySelectorAll("#ee-cap-filter .ee-chip").forEach(btn => {{
      const code = String(btn.getAttribute("data-cap") || "").toUpperCase();
      const active = code ? capFilters.has(code) : !on;
      btn.classList.toggle("active", active);
    }});
  }}
  function renderHead() {{
    const th = document.getElementById("ee-head");
    if (!th) return;
    th.innerHTML = "";
    COLS.forEach(c => {{
      const cell = document.createElement("th");
      const active = sortCol === c.id;
      const arrow = active ? (sortDir < 0 ? "↓" : "↑") : "↕";
      cell.innerHTML = `${{esc(c.label)}}<span class="sort-ind${{active ? " active" : ""}}">${{arrow}}</span>`;
      if (c.sort) {{
        cell.onclick = () => {{
          if (sortCol === c.id) sortDir *= -1;
          else {{ sortCol = c.id; sortDir = c.num ? -1 : 1; }}
          render();
        }};
      }} else {{
        cell.style.cursor = "default";
      }}
      th.appendChild(cell);
    }});
  }}
  function render() {{
    renderHead();
    syncCapButtons();
    let rows = DATA.filter(r => capOk(r) && sectorOk(r) && searchOk(r));
    rows = rows.slice().sort(compare);
    const countEl = document.getElementById("ee-count");
    if (countEl) {{
      const bits = [];
      if (capFilters.size) bits.push([...capFilters].join("+"));
      if (sectorFilter) bits.push(sectorFilter);
      if (searchQuery) bits.push("search");
      const filterBit = bits.length ? ` · ${{bits.join(" · ")}}` : "";
      countEl.textContent = `${{rows.length}} of ${{DATA.length}}${{filterBit}} · {title_esc}`;
    }}
    const tb = document.getElementById("ee-body");
    if (!tb) return;
    tb.innerHTML = "";
    if (!rows.length) {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="${{COLS.length}}"><div class="ee-empty">No names match these filters.</div></td>`;
      tb.appendChild(tr);
      return;
    }}
    rows.forEach(r => {{
      const tr = document.createElement("tr");
      COLS.forEach(c => {{
        const td = document.createElement("td");
        td.innerHTML = cell(c, r);
        tr.appendChild(td);
      }});
      tb.appendChild(tr);
    }});
  }}

  document.getElementById("ee-search").oninput = (e) => {{
    searchQuery = String(e.target.value || "").trim().toLowerCase();
    render();
  }};
  if (sectorEl) {{
    sectorEl.onchange = () => {{
      sectorFilter = String(sectorEl.value || "");
      render();
    }};
  }}
  document.querySelectorAll("#ee-cap-filter .ee-chip").forEach(btn => {{
    btn.onclick = () => {{
      const code = String(btn.getAttribute("data-cap") || "").toUpperCase();
      if (!code) {{
        capFilters.clear();
      }} else if (capFilters.has(code)) {{
        capFilters.delete(code);
      }} else {{
        capFilters.add(code);
      }}
      render();
    }};
  }});
  render();
}})();
</script>
"""

    if standalone:
        return (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{title_esc}</title>{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def early_edge_iframe_height(row_count: int) -> int:
    return min(2200, max(520, 340 + min(row_count, 80) * 30))
