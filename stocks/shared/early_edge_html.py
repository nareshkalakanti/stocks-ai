"""Early Edge Watching — interactive HTML table with Cap / SME / Sector filters."""

from __future__ import annotations

import html
import json

import pandas as pd

from stocks.core.json_utils import json_dumps, json_safe_scalar
from stocks.core.text_utils import safe_str
from stocks.dashboards.report_html import _REPORT_CSS

_EDGE_CSS = """
<style>
  .ee-wrap {
    font-family: "Google Sans", "Product Sans", ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    color: #202124;
  }
  .ee-hero {
    display: flex; flex-direction: column; align-items: center;
    padding: 18px 12px 8px; margin: 0 0 4px;
  }
  .ee-search-shell {
    display: flex; align-items: center; gap: 14px;
    width: min(720px, 100%);
    min-height: 56px;
    padding: 4px 20px 4px 22px;
    background: #fff;
    border: 1px solid #dfe1e5;
    border-radius: 28px;
    box-shadow: 0 1px 6px rgba(32, 33, 36, 0.08);
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
  }
  .ee-search-shell:hover {
    box-shadow: 0 1px 8px rgba(32, 33, 36, 0.14);
  }
  .ee-search-shell:focus-within {
    border-color: transparent;
    box-shadow: 0 1px 8px rgba(32, 33, 36, 0.22);
  }
  .ee-search-icon {
    flex: 0 0 auto; width: 22px; height: 22px; color: #9aa0a6;
  }
  .ee-search {
    flex: 1 1 auto; min-width: 0; width: 100%;
    border: 0; outline: none; background: transparent;
    font-size: 18px; line-height: 1.35; color: #202124;
    padding: 12px 0;
    -webkit-appearance: none; appearance: none;
  }
  .ee-search::placeholder { color: #80868b; font-size: 17px; }
  .ee-search::-webkit-search-cancel-button { -webkit-appearance: none; }
  .ee-search-hint {
    margin-top: 10px; font-size: 12px; color: #70757a; letter-spacing: 0.01em;
    text-align: center;
  }
  .ee-search-hint code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px; color: #5f6368; background: #f1f3f4;
    padding: 1px 5px; border-radius: 4px;
  }
  .ee-count {
    margin-top: 8px; font-size: 13px; color: #70757a; text-align: center;
  }
  .ee-toolbar {
    display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; justify-content: center;
    margin: 0 0 14px; padding: 4px 8px 10px;
    background: transparent; border: 0;
  }
  .ee-filter-group { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; }
  .ee-filter-label {
    font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: #80868b; margin-right: 2px;
  }
  .ee-chip {
    border: 1px solid #dadce0; background: #fff; color: #3c4043; border-radius: 999px;
    padding: 5px 12px; font-size: 12px; font-weight: 600; cursor: pointer; line-height: 1.3;
  }
  .ee-chip.active, .ee-chip:hover {
    background: #e8f0fe; border-color: #aecbfa; color: #1967d2;
  }
  #ee-sme-filter .ee-chip[data-sme="1"].active,
  #ee-sme-filter .ee-chip[data-sme="1"]:hover {
    background: #ffedd5; border-color: #f97316; color: #9a3412;
  }
  .ee-sector-select {
    padding: 6px 10px; border: 1px solid #dadce0; border-radius: 999px; font-size: 12px; background: #fff; max-width: 220px;
    color: #3c4043;
  }
  .ee-page-group { display: none; align-items: center; gap: 2px; }
  .ee-page-group .ee-chip { min-width: 28px; padding: 4px 8px; }
  .ee-page-group .ee-chip:disabled { opacity: 0.35; cursor: default; }
  .ee-page-label { font-size: 11px; color: #70757a; font-weight: 600; padding: 0 4px; white-space: nowrap; }
  .ee-table-wrap { overflow-x: auto; border: 1px solid #e8eaed; border-radius: 12px; background: #fff; }
  .ee-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .ee-table th {
    text-align: left; padding: 9px 10px; background: #f8f9fa; border-bottom: 1px solid #e8eaed;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: #70757a;
    position: sticky; top: 0; z-index: 1; cursor: pointer; user-select: none; white-space: nowrap;
  }
  .ee-table th .sort-ind { opacity: 0.35; margin-left: 4px; font-size: 10px; }
  .ee-table th .sort-ind.active { opacity: 1; color: #1967d2; }
  .ee-table td { padding: 8px 10px; border-bottom: 1px solid #f1f3f4; vertical-align: top; }
  .ee-table tr:hover td { background: #f8f9fa; }
  .ee-co { font-weight: 650; color: #202124; }
  .ee-ticker { font-size: 11px; color: #70757a; margin-top: 2px; }
  .ee-tags { display: inline-flex; gap: 4px; margin-left: 6px; vertical-align: middle; }
  .ee-tag {
    display: inline-block; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 4px;
    color: #1967d2; background: #e8f0fe; text-transform: uppercase; letter-spacing: 0.04em;
  }
  .ee-tag-sme { color: #9a3412; background: #ffedd5; }
  .ee-tag-hold { color: #1d4ed8; background: #dbeafe; }
  .ee-tag-fund { color: #5b21b6; background: #ede9fe; }
  .ee-links a {
    display: inline-block; margin-right: 4px; padding: 2px 7px; border-radius: 4px;
    background: #f1f3f4; color: #1967d2; text-decoration: none; font-size: 11px; font-weight: 700;
  }
  .ee-links a:hover { background: #e8f0fe; }
  .ee-num { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .ee-muted { color: #9aa0a6; }
  .ee-empty { padding: 36px 28px; text-align: center; color: #70757a; font-size: 14px; }
  .ee-table tr.ee-row { cursor: pointer; }
  .ee-table tr.ee-row.expanded td { background: #f8f9fa; }
  .ee-table tr.ee-about-row td {
    padding: 0 12px 12px; background: #f8f9fa; border-bottom: 2px solid #e8eaed;
  }
  .ee-about {
    color: #3c4043; font-size: 12px; line-height: 1.5; max-width: 72rem;
  }
  .ee-about.collapsed {
    display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
  }
  .ee-about-more {
    border: 0; background: none; color: #1967d2; font-size: 11px; font-weight: 700;
    padding: 6px 0 0; cursor: pointer;
  }
  .ee-about-label {
    font-size: 10px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase;
    color: #5f6368; margin: 0 0 4px;
  }
  .ee-about-hit {
    display: inline-block; margin-left: 6px; font-size: 10px; font-weight: 700;
    color: #1967d2; background: #e8f0fe; padding: 1px 6px; border-radius: 4px;
    text-transform: none; letter-spacing: 0;
  }
  .ee-about-meta {
    font-size: 12px; color: #3c4043; line-height: 1.45; margin: 0 0 6px; max-width: 72rem;
  }
  .ee-about-meta b { color: #5f6368; font-weight: 700; margin-right: 4px; }
  .ee-about-meta a { color: #1967d2; font-weight: 700; text-decoration: none; }
  .ee-about-meta a:hover { text-decoration: underline; }
  .ee-about mark {
    background: #fef08a; color: #854d0e; padding: 0 2px; border-radius: 2px;
  }
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
                "price": json_safe_scalar(row.get("price")),
                "market_cap_cr": json_safe_scalar(row.get("market_cap_cr")),
                "cap_code": safe_str(row.get("cap_code")) or "",
                "cap_label": safe_str(row.get("cap_label")) or "",
                "is_edge": bool(row.get("is_edge")),
                "is_holding": bool(row.get("is_holding")),
                "list_tag": safe_str(row.get("list_tag")) or "",
                "is_sme": market == "NSE SME",
                "sc": safe_str(row.get("sc")) or "",
                "tv": safe_str(row.get("tv")) or "",
                "website": safe_str(row.get("website")) or "",
                "about": safe_str(row.get("about")) or "",
                "products": safe_str(row.get("products")) or "",
                "end_markets": safe_str(row.get("end_markets")) or "",
                "theme_tags": safe_str(row.get("theme_tags")) or "",
                "ir_url": safe_str(row.get("ir_url")) or "",
                "matched_from": safe_str(row.get("holding_entity")) or "",
            }
        )
    return rows


def build_early_edge_html(
    df: pd.DataFrame,
    *,
    title: str = "Early Edge",
    standalone: bool = False,
    client_page_size: int | None = None,
) -> str:
    work = df if df is not None else pd.DataFrame()
    payload = _rows_payload(work)
    page_size = int(client_page_size) if client_page_size and int(client_page_size) > 0 else 0
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
  <div class="ee-hero">
    <div class="ee-search-shell">
      <svg class="ee-search-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path fill="currentColor" d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
      </svg>
      <input type="search" class="ee-search" id="ee-search"
        placeholder="Search companies"
        autocomplete="off" spellcheck="false" />
    </div>
    <div class="ee-search-hint">
      <code>+</code> AND &nbsp;·&nbsp; <code>|</code> OR &nbsp;·&nbsp; e.g. copper | aluminium | cobalt
    </div>
    <div class="ee-count" id="ee-count"></div>
  </div>
  <div class="ee-toolbar">
    <div class="ee-filter-group" id="ee-cap-filter" role="group" aria-label="Cap filter">
      <span class="ee-filter-label">Cap</span>
      <button type="button" class="cap-chip active" data-cap="" title="All cap bands">All</button>
      <button type="button" class="cap-chip" data-cap="NC" title="Nano Cap (&lt; 100 Cr)">NC</button>
      <button type="button" class="cap-chip" data-cap="MIC" title="Micro Cap (100–500 Cr)">MIC</button>
      <button type="button" class="cap-chip" data-cap="SC" title="Small Cap (500–5,000 Cr)">SC</button>
      <button type="button" class="cap-chip" data-cap="MC" title="Mid Cap (5,000–20,000 Cr)">MC</button>
      <button type="button" class="cap-chip" data-cap="LC" title="Large Cap (≥ 20,000 Cr)">LC</button>
    </div>
    <div class="ee-filter-group" id="ee-sme-filter" role="group" aria-label="SME filter">
      <span class="ee-filter-label">Market</span>
      <button type="button" class="ee-chip active" data-sme="" title="All markets">All</button>
      <button type="button" class="ee-chip" data-sme="1" title="NSE Emerge / SME only">SME</button>
    </div>
    <div class="ee-filter-group">
      <span class="ee-filter-label">Sector</span>
      <select class="ee-sector-select" id="ee-sector" aria-label="Sector filter">
        <option value="">All sectors</option>
      </select>
    </div>
    <div class="ee-filter-group ee-page-group" id="ee-page-group">
      <button type="button" class="ee-chip" id="ee-page-prev" title="Previous page">‹</button>
      <span class="ee-page-label" id="ee-page-label"></span>
      <button type="button" class="ee-chip" id="ee-page-next" title="Next page">›</button>
    </div>
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
  const PAGE_SIZE = {page_size};
  const COLS = [
    {{ id: "company", label: "Company", sort: "name" }},
    {{ id: "price", label: "Price", sort: "price", num: true }},
    {{ id: "sector", label: "Sector", sort: "sector" }},
    {{ id: "sub_sector", label: "Sub-sector", sort: "sub_sector" }},
    {{ id: "market_cap_cr", label: "Mcap Cr", sort: "market_cap_cr", num: true }},
    {{ id: "links", label: "Links", sort: null }},
  ];
  let searchQuery = "";
  let searchTerms = [];
  let searchMode = "and"; // "and" (+) or "or" (| or ,)
  let capFilters = new Set();
  let smeOnly = false;
  let sectorFilter = "";
  let sortCol = "sector";
  let sortDir = 1;
  let expanded = null;
  let collapsedManual = new Set(); // tickers user closed while search auto-opens About
  let pageIndex = 0;

  // Common about-text spelling variants (Yahoo often uses US spelling).
  const TERM_SYNONYMS = {{
    aluminium: ["aluminium", "aluminum"],
    aluminum: ["aluminium", "aluminum"],
  }};

  function resetPage() {{
    pageIndex = 0;
  }}

  function parseSearch(raw) {{
    // "copper + rods" → AND; "copper | aluminium | cobalt" or commas → OR.
    const q = String(raw || "").toLowerCase().trim();
    if (!q) return {{ mode: "and", terms: [] }};
    let mode = "and";
    let parts;
    if (q.includes("|")) {{
      mode = "or";
      parts = q.split("|");
    }} else if (q.includes(",")) {{
      mode = "or";
      parts = q.split(",");
    }} else {{
      parts = q.split("+");
    }}
    const terms = parts.map(t => t.trim()).filter(Boolean);
    return {{ mode, terms }};
  }}
  function termVariants(term) {{
    const t = String(term || "").trim().toLowerCase();
    if (!t) return [];
    return TERM_SYNONYMS[t] || [t];
  }}
  function hayHasTerm(hay, term) {{
    return termVariants(term).some(v => hay.includes(v));
  }}
  function searchLabel() {{
    const join = searchMode === "or" ? " | " : " + ";
    return searchTerms.join(join);
  }}
  function rowHay(r) {{
    return [r.ticker, r.name, r.sector, r.sub_sector, r.industry, r.market, r.matched_from,
            r.about]
      .map(v => String(v || "").toLowerCase()).join(" ");
  }}

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
  function fmtPrice(v) {{
    const n = num(v);
    if (n == null) return '<span class="ee-muted">—</span>';
    return `<span class="ee-num">₹${{n.toLocaleString("en-IN", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }})}}</span>`;
  }}
  function fmtCap(code, label) {{
    const c = String(code || "").toUpperCase();
    if (!c) return '<span class="ee-muted">—</span>';
    const tip = esc(label || c);
    return `<span class="cap-badge cap-${{c.toLowerCase()}}" title="${{tip}}">${{esc(c)}}</span>`;
  }}
  function companyCell(r) {{
    const tags = [];
    if (r.is_edge) tags.push('<span class="ee-tag" title="Early Edge watchlist">Edge</span>');
    if (r.is_holding) tags.push('<span class="ee-tag ee-tag-hold" title="In your Holdings portfolio">Holding</span>');
    if (r.list_tag && !r.is_edge && !r.is_holding) {{
      tags.push(`<span class="ee-tag ee-tag-fund" title="${{esc(r.list_tag)}}">${{esc(r.list_tag)}}</span>`);
    }}
    if (r.is_sme) tags.push('<span class="ee-tag ee-tag-sme" title="NSE Emerge / SME">SME</span>');
    const tagHtml = tags.length ? `<span class="ee-tags">${{tags.join("")}}</span>` : "";
    return (
      `<div class="ee-co">${{esc(r.name || r.ticker)}}${{tagHtml}}</div>` +
      `<div class="ee-ticker">${{esc(r.ticker)}}</div>`
    );
  }}
  function linksCell(r) {{
    const bits = [];
    let web = r.website || "";
    if (web && !/^https?:\\/\\//i.test(web)) web = "https://" + web;
    if (web) bits.push(`<a href="${{esc(web)}}" target="_blank" rel="noopener noreferrer" title="Company website">Web</a>`);
    if (r.sc) bits.push(`<a href="${{esc(r.sc)}}" target="_blank" rel="noopener noreferrer">SC</a>`);
    if (r.tv) bits.push(`<a href="${{esc(r.tv)}}" target="_blank" rel="noopener noreferrer">TV</a>`);
    return bits.length ? `<span class="ee-links">${{bits.join("")}}</span>` : "—";
  }}
  function cell(col, r) {{
    switch (col.id) {{
      case "company": return companyCell(r);
      case "price": return fmtPrice(r.price);
      case "sector": return esc(r.sector) || '<span class="ee-muted">—</span>';
      case "sub_sector": return esc(r.sub_sector) || '<span class="ee-muted">—</span>';
      case "market_cap_cr": return fmtMcap(r.market_cap_cr);
      case "links": return linksCell(r);
      default: return "—";
    }}
  }}
  function capOk(r) {{
    if (!capFilters.size) return true;
    const c = String(r.cap_code || "").toUpperCase();
    return capFilters.has(c);
  }}
  function smeOk(r) {{
    if (!smeOnly) return true;
    return !!r.is_sme || String(r.market || "").toUpperCase() === "NSE SME";
  }}
  function sectorOk(r) {{
    if (!sectorFilter) return true;
    return String(r.sector || "") === sectorFilter;
  }}
  function searchOk(r) {{
    if (!searchTerms.length) return true;
    const hay = rowHay(r);
    if (searchMode === "or") return searchTerms.some(t => hayHasTerm(hay, t));
    return searchTerms.every(t => hayHasTerm(hay, t));
  }}
  function aboutMatch(r) {{
    if (!searchTerms.length) return false;
    const about = String(r.about || "").toLowerCase();
    return searchTerms.some(t => hayHasTerm(about, t));
  }}
  function highlightAbout(text) {{
    const raw = String(text || "");
    if (!searchTerms.length || !raw) return esc(raw);
    const lower = raw.toLowerCase();
    const terms = [];
    searchTerms.forEach(t => termVariants(t).forEach(v => terms.push(v)));
    terms.sort((a, b) => b.length - a.length);
    const marks = [];
    for (const q of terms) {{
      if (!q) continue;
      let from = 0;
      while (from < raw.length) {{
        const at = lower.indexOf(q, from);
        if (at < 0) break;
        marks.push([at, at + q.length]);
        from = at + q.length;
      }}
    }}
    if (!marks.length) return esc(raw);
    marks.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    const merged = [];
    for (const m of marks) {{
      const last = merged[merged.length - 1];
      if (last && m[0] <= last[1]) last[1] = Math.max(last[1], m[1]);
      else merged.push(m.slice());
    }}
    let out = "";
    let i = 0;
    for (const [a, b] of merged) {{
      out += esc(raw.slice(i, a));
      out += "<mark>" + esc(raw.slice(a, b)) + "</mark>";
      i = b;
    }}
    out += esc(raw.slice(i));
    return out;
  }}
  function aboutPanel(r) {{
    const about = String(r.about || "").trim();
    const hit = aboutMatch(r);
    const labelHit = hit
      ? `<span class="ee-about-hit">matched “${{esc(searchLabel())}}”</span>`
      : "";
    if (!about) {{
      return (
        `<div class="ee-about-label">About${{labelHit}}</div>` +
        `<div class="ee-about ee-muted">No about text yet.</div>`
      );
    }}
    const long = about.length > 280 && !hit;
    const id = "ee-about-" + esc(r.ticker);
    return (
      `<div class="ee-about-label">About${{labelHit}}</div>` +
      `<div class="ee-about${{long ? " collapsed" : ""}}" id="${{id}}">${{highlightAbout(about)}}</div>` +
      (long
        ? `<button type="button" class="ee-about-more" data-target="${{id}}">Show more</button>`
        : "")
    );
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
    document.querySelectorAll("#ee-cap-filter .cap-chip").forEach(btn => {{
      const code = String(btn.getAttribute("data-cap") || "").toUpperCase();
      const active = code ? capFilters.has(code) : !on;
      btn.classList.toggle("active", active);
    }});
  }}
  function syncSmeButtons() {{
    document.querySelectorAll("#ee-sme-filter .ee-chip").forEach(btn => {{
      const wantSme = String(btn.getAttribute("data-sme") || "") === "1";
      const active = wantSme ? smeOnly : !smeOnly;
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
    syncSmeButtons();
    let rows = DATA.filter(r => capOk(r) && smeOk(r) && sectorOk(r) && searchOk(r));
    rows = rows.slice().sort(compare);
    const totalFiltered = rows.length;
    let pageRows = rows;
    const pageGroup = document.getElementById("ee-page-group");
    if (PAGE_SIZE > 0 && totalFiltered > PAGE_SIZE) {{
      const totalPages = Math.max(1, Math.ceil(totalFiltered / PAGE_SIZE));
      if (pageIndex >= totalPages) pageIndex = totalPages - 1;
      if (pageIndex < 0) pageIndex = 0;
      const start = pageIndex * PAGE_SIZE;
      pageRows = rows.slice(start, start + PAGE_SIZE);
      if (pageGroup) pageGroup.style.display = "inline-flex";
      const lbl = document.getElementById("ee-page-label");
      if (lbl) lbl.textContent = `${{pageIndex + 1}}/${{totalPages}}`;
      const prevBtn = document.getElementById("ee-page-prev");
      const nextBtn = document.getElementById("ee-page-next");
      if (prevBtn) prevBtn.disabled = pageIndex <= 0;
      if (nextBtn) nextBtn.disabled = pageIndex >= totalPages - 1;
    }} else if (pageGroup) {{
      pageGroup.style.display = "none";
      pageIndex = 0;
    }}
    const countEl = document.getElementById("ee-count");
    if (countEl) {{
      const bits = [];
      if (capFilters.size) bits.push([...capFilters].join("+"));
      if (smeOnly) bits.push("SME");
      if (sectorFilter) bits.push(sectorFilter);
      if (searchQuery) {{
        const aboutHits = rows.filter(aboutMatch).length;
        bits.push(aboutHits ? `search (${{aboutHits}} in about)` : "search");
      }}
      const filterBit = bits.length ? ` · ${{bits.join(" · ")}}` : "";
      if (PAGE_SIZE > 0 && totalFiltered > PAGE_SIZE) {{
        const start = pageIndex * PAGE_SIZE + 1;
        const end = Math.min((pageIndex + 1) * PAGE_SIZE, totalFiltered);
        countEl.textContent = `${{start}}–${{end}} of ${{totalFiltered}}${{filterBit}} · {title_esc}`;
      }} else {{
        countEl.textContent = `${{totalFiltered}} of ${{DATA.length}}${{filterBit}} · {title_esc}`;
      }}
    }}
    const tb = document.getElementById("ee-body");
    if (!tb) return;
    tb.innerHTML = "";
    if (!pageRows.length) {{
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="${{COLS.length}}"><div class="ee-empty">No names match these filters.</div></td>`;
      tb.appendChild(tr);
      return;
    }}
    if (expanded && !pageRows.some(r => r.ticker === expanded)) expanded = null;
    pageRows.forEach(r => {{
      const aboutHit = aboutMatch(r);
      const open = expanded === r.ticker
        || (aboutHit && !collapsedManual.has(r.ticker));
      const tr = document.createElement("tr");
      tr.className = "ee-row" + (open ? " expanded" : "");
      tr.title = "Click to show About";
      COLS.forEach(c => {{
        const td = document.createElement("td");
        td.innerHTML = cell(c, r);
        tr.appendChild(td);
      }});
      tr.onclick = (e) => {{
        if (e.target.closest("a, button")) return;
        if (open) {{
          expanded = null;
          if (aboutHit) collapsedManual.add(r.ticker);
        }} else {{
          collapsedManual.delete(r.ticker);
          expanded = r.ticker;
        }}
        render();
      }};
      tb.appendChild(tr);
      if (open) {{
        const aboutTr = document.createElement("tr");
        aboutTr.className = "ee-about-row";
        aboutTr.innerHTML = `<td colspan="${{COLS.length}}">${{aboutPanel(r)}}</td>`;
        tb.appendChild(aboutTr);
      }}
    }});
    tb.querySelectorAll(".ee-about-more").forEach(btn => {{
      btn.onclick = (e) => {{
        e.stopPropagation();
        const el = document.getElementById(btn.getAttribute("data-target"));
        if (!el) return;
        const collapsed = el.classList.toggle("collapsed");
        btn.textContent = collapsed ? "Show more" : "Show less";
      }};
    }});
  }}

  document.getElementById("ee-search").oninput = (e) => {{
    searchQuery = String(e.target.value || "").trim().toLowerCase();
    const parsed = parseSearch(searchQuery);
    searchMode = parsed.mode;
    searchTerms = parsed.terms;
    collapsedManual.clear();
    resetPage();
    render();
  }};
  if (sectorEl) {{
    sectorEl.onchange = () => {{
      sectorFilter = String(sectorEl.value || "");
      resetPage();
      render();
    }};
  }}
  document.querySelectorAll("#ee-cap-filter .cap-chip").forEach(btn => {{
    btn.onclick = () => {{
      const code = String(btn.getAttribute("data-cap") || "").toUpperCase();
      if (!code) {{
        capFilters.clear();
      }} else if (capFilters.has(code)) {{
        capFilters.delete(code);
      }} else {{
        capFilters.add(code);
      }}
      resetPage();
      render();
    }};
  }});
  document.querySelectorAll("#ee-sme-filter .ee-chip").forEach(btn => {{
    btn.onclick = () => {{
      smeOnly = String(btn.getAttribute("data-sme") || "") === "1";
      resetPage();
      render();
    }};
  }});
  const pagePrev = document.getElementById("ee-page-prev");
  const pageNext = document.getElementById("ee-page-next");
  if (pagePrev) {{
    pagePrev.onclick = () => {{
      if (pageIndex > 0) {{
        pageIndex -= 1;
        expanded = null;
        render();
      }}
    }};
  }}
  if (pageNext) {{
    pageNext.onclick = () => {{
      pageIndex += 1;
      expanded = null;
      render();
    }};
  }}
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
    return min(2700, max(640, 440 + min(row_count, 80) * 32))
