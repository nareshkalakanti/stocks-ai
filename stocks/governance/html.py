"""PEAD-style HTML report for Governance Map (director → companies)."""

from __future__ import annotations

import html
import json

import pandas as pd

from stocks.core.json_utils import json_dumps, json_safe_obj, json_safe_scalar
from stocks.core.text_utils import safe_str
from stocks.dashboards.report_html import _REPORT_CSS


GOVERNANCE_MAP_CSS = """
<style>
  .gov-score {
    font-weight: 700;
    color: #059669;
    font-variant-numeric: tabular-nums;
  }
  .gov-badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 4px;
    background: #ecfdf5;
    color: #047857;
    margin-left: 6px;
  }
  .gov-badge.name {
    background: #fff7ed;
    color: #c2410c;
  }
  .gov-badge.suspect {
    background: #fef2f2;
    color: #b91c1c;
  }
  .gov-dir-cell .sub { color: #6b7280; font-size: 11px; margin-top: 2px; }
  .gov-cos {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 4px 0 8px;
  }
  .gov-co {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 12px 14px;
    background: #fff;
  }
  .gov-co-top {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
  }
  .gov-co-name {
    font-weight: 700;
    font-size: 14px;
    color: #111827;
  }
  .gov-co-tags {
    display: inline-flex;
    gap: 4px;
    margin-left: 8px;
    vertical-align: middle;
  }
  .gov-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 4px;
  }
  .gov-tag-hold {
    color: #1d4ed8;
    background: #dbeafe;
  }
  .gov-tag-sme {
    color: #9a3412;
    background: #ffedd5;
  }
  .gov-tickers {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 10px;
    align-items: flex-start;
    line-height: 1.35;
    word-break: break-word;
  }
  .gov-ticker-stack {
    display: inline-flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    vertical-align: top;
  }
  .gov-ticker-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
  }
  .gov-cap-tag {
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0 5px;
    border-radius: 3px;
    line-height: 1.4;
  }
  .gov-cap-nc { color: #6b7280; background: #f3f4f6; }
  .gov-cap-mic { color: #9a3412; background: #ffedd5; }
  .gov-cap-sc { color: #a16207; background: #fef9c3; }
  .gov-cap-mc { color: #1d4ed8; background: #dbeafe; }
  .gov-cap-lc { color: #047857; background: #d1fae5; }
  .gov-ticker-hold {
    color: #1d4ed8;
    font-weight: 700;
    background: #dbeafe;
    padding: 0 4px;
    border-radius: 3px;
  }
  .gov-ticker-focus {
    color: #1d4ed8;
    font-weight: 700;
    background: #dbeafe;
    padding: 0 4px;
    border-radius: 3px;
  }
  .gov-co-sub {
    color: #6b7280;
    font-size: 12px;
    margin-top: 2px;
  }
  .gov-co-mcap {
    font-size: 13px;
    font-weight: 800;
    color: #111827;
    white-space: nowrap;
  }
  .gov-co-mcap .gov-mcap-label {
    font-weight: 600;
    color: #6b7280;
    font-size: 11px;
    margin-right: 4px;
  }
  th.gov-sortable {
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  th.gov-sortable:hover { color: #1d4ed8; }
  .gov-sort-ind {
    margin-left: 4px;
    opacity: 0.35;
    font-size: 10px;
  }
  .gov-sort-ind.active {
    opacity: 1;
    color: #1d4ed8;
    font-weight: 700;
  }
  .gov-co-links {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 8px;
  }
  .gov-co-links a {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 4px;
    background: #eff6ff;
    color: #1d4ed8;
    text-decoration: none;
    font-size: 11px;
    font-weight: 600;
  }
  .gov-co-links a:hover { background: #dbeafe; }
  .gov-about {
    margin-top: 8px;
    color: #4b5563;
    font-size: 12px;
    line-height: 1.45;
  }
  .gov-about.collapsed {
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .gov-about-more {
    border: 0;
    background: none;
    color: #1d4ed8;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 0 0;
    cursor: pointer;
  }
  .gov-breakdown {
    margin: 0 0 10px;
    font-size: 11px;
    color: #6b7280;
  }
  tr.strat-row { cursor: pointer; }
  tr.strat-row.expanded td { background: #f0f9ff; }
  tr.strat-expand td {
    background: #f8fafc;
    border-bottom: 2px solid #e5e7eb;
  }
  .gov-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
    margin: 0 0 12px;
  }
  .gov-search {
    flex: 1 1 240px;
    min-width: 180px;
    max-width: 420px;
    padding: 8px 12px;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    font-size: 13px;
    color: #111827;
    background: #fff;
  }
  .gov-search:focus {
    outline: none;
    border-color: #93c5fd;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
  }
  .gov-search-meta {
    font-size: 12px;
    color: #6b7280;
  }
  .gov-empty {
    padding: 18px 8px;
    color: #6b7280;
    font-size: 13px;
  }
  .gov-mode {
    display: inline-flex;
    padding: 2px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #fff;
  }
  .gov-mode button {
    border: 0;
    background: transparent;
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 10px;
    border-radius: 6px;
    color: #6b7280;
    cursor: pointer;
  }
  .gov-mode button.active {
    background: #eff6ff;
    color: #1d4ed8;
  }
  .govhub-hero {
    margin: 0 12px 8px;
    padding: 12px 14px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #f8fbff;
  }
  .govhub-hero-top {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .govhub-name {
    font-weight: 700;
    font-size: 15px;
    color: #111827;
    margin: 0 0 2px;
  }
  .govhub-sub {
    color: #6b7280;
    font-size: 12px;
    font-weight: 500;
    margin: 0;
  }
  .govhub-stats {
    display: flex;
    gap: 16px;
    font-weight: 600;
  }
  .govhub-stats div { text-align: right; }
  .govhub-stats b {
    display: block;
    font-size: 15px;
    color: #111827;
    font-variant-numeric: tabular-nums;
  }
  .govhub-stats span {
    font-size: 11px;
    color: #6b7280;
    font-weight: 500;
  }
  .gov-role-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 0 12px 10px;
  }
  .gov-role-chip {
    border: 1px solid #e5e7eb;
    background: #fff;
    color: #374151;
    font: inherit;
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 999px;
    cursor: pointer;
  }
  .gov-role-chip:hover { border-color: #93c5fd; color: #1d4ed8; }
  .gov-role-chip.active {
    background: #eff6ff;
    border-color: #93c5fd;
    color: #1d4ed8;
  }
  .gov-cap-filter {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
    padding: 2px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #fff;
  }
  .gov-cap-filter .gov-cap-filter-label {
    font-size: 11px;
    font-weight: 600;
    color: #6b7280;
    padding: 0 6px 0 8px;
  }
  .gov-cap-filter button {
    border: 0;
    background: transparent;
    font: inherit;
    font-size: 11px;
    font-weight: 700;
    padding: 5px 8px;
    border-radius: 6px;
    color: #6b7280;
    cursor: pointer;
    letter-spacing: 0.02em;
  }
  .gov-cap-filter button.active {
    color: #111827;
  }
  .gov-cap-filter button[data-cap=""].active { background: #f3f4f6; }
  .gov-cap-filter button[data-cap="NC"].active { background: #f3f4f6; color: #6b7280; }
  .gov-cap-filter button[data-cap="MIC"].active { background: #ffedd5; color: #9a3412; }
  .gov-cap-filter button[data-cap="SC"].active { background: #fef9c3; color: #a16207; }
  .gov-cap-filter button[data-cap="MC"].active { background: #dbeafe; color: #1d4ed8; }
  .gov-cap-filter button[data-cap="LC"].active { background: #d1fae5; color: #047857; }
  .gov-ticker-stack.filter-miss {
    opacity: 0.42;
  }
  .gov-ticker-stack.filter-hit {
    outline: 1px solid #93c5fd;
    outline-offset: 2px;
    border-radius: 4px;
    padding: 1px 2px;
  }
  .gov-co.filter-miss {
    opacity: 0.55;
  }
  .gov-co.filter-hit {
    border-color: #93c5fd;
    background: #f8fbff;
  }
  .gov-hold-filter button[data-hold=""].active { background: #f3f4f6; }
  .gov-hold-filter button[data-hold="HOLD"].active {
    background: #dbeafe;
    color: #1d4ed8;
  }
  }
  .gov-role-tag {
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.03em;
    padding: 0 5px;
    border-radius: 3px;
    line-height: 1.4;
    color: #6d28d9;
    background: #ede9fe;
  }
  .gov-co.role-hit {
    border-color: #c4b5fd;
    background: #faf5ff;
  }
</style>
"""


def _rows_for_json(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, row in df.iterrows():
        companies = row.get("companies") or []
        if not isinstance(companies, list):
            companies = []
        rows.append(
            {
                "rank": json_safe_scalar(row.get("rank")),
                "person_id": safe_str(row.get("person_id")),
                "name": safe_str(row.get("name") or row.get("director")),
                "din": safe_str(row.get("din")) or None,
                "din_backed": bool(row.get("din_backed")),
                "name_collision": bool(row.get("name_collision")),
                "board_count": json_safe_scalar(row.get("board_count")),
                "dir_score": json_safe_scalar(row.get("dir_score")),
                "big_n": json_safe_scalar(row.get("big_n")),
                "small_n": json_safe_scalar(row.get("small_n")),
                "bridge": bool(row.get("bridge")),
                "tickers": safe_str(row.get("tickers")),
                "companies": json_safe_obj(companies),
                "score_breakdown": json_safe_obj(row.get("score_breakdown") or {}),
            }
        )
    return rows


GOVERNANCE_MAP_COLS = [
    {"id": "rank", "label": "#", "sort": "num"},
    {"id": "director", "label": "Director", "sort": "text"},
    {"id": "dir_score", "label": "Dir Score", "sort": "num"},
    {"id": "board_count", "label": "Boards", "sort": "num"},
    {"id": "big_n", "label": "Big", "sort": "num"},
    {"id": "small_n", "label": "Small", "sort": "num"},
    {"id": "tickers", "label": "Companies", "sort": "text"},
]


def build_governance_map_html(
    df: pd.DataFrame,
    *,
    title: str = "Governance Map",
    standalone: bool = True,
    initial_query: str = "",
) -> str:
    work = df.copy() if df is not None else pd.DataFrame()
    data_json = json_dumps(_rows_for_json(work), separators=(",", ":"))
    cols_str = json.dumps(GOVERNANCE_MAP_COLS, separators=(",", ":"))
    initial = json.dumps(safe_str(initial_query))
    section = f"""
<details class="fund-section" open id="govmap-wrap">
  <summary>
    <span>{html.escape(title)}</span>
    <span class="fund-section-meta" id="govmap-meta">{len(work)} directors · click row for companies</span>
  </summary>
  <div class="fund-section-body">
    <div class="gov-toolbar">
      <input class="gov-search" id="govmap-search" type="search"
        placeholder="Search ticker, company, director, or role…"
        autocomplete="off" value={initial} />
      <div class="gov-mode" role="group" aria-label="View mode">
        <button type="button" id="govmap-mode-hub">By company</button>
        <button type="button" class="active" id="govmap-mode-dir">By director</button>
        <button type="button" id="govmap-mode-role">By role</button>
      </div>
      <div class="gov-cap-filter" role="group" aria-label="Cap tag filter" id="govmap-cap-filter">
        <span class="gov-cap-filter-label">Cap</span>
        <button type="button" class="active" data-cap="" title="Show all cap tags">All</button>
        <button type="button" data-cap="NC" title="Nano Cap (&lt; 100 Cr)">NC</button>
        <button type="button" data-cap="MIC" title="Micro Cap (100–500 Cr)">MIC</button>
        <button type="button" data-cap="SC" title="Small Cap (500–5,000 Cr)">SC</button>
        <button type="button" data-cap="MC" title="Mid Cap (5,000–20,000 Cr)">MC</button>
        <button type="button" data-cap="LC" title="Large Cap (≥ 20,000 Cr)">LC</button>
      </div>
      <div class="gov-cap-filter gov-hold-filter" role="group" aria-label="Holdings filter" id="govmap-hold-filter">
        <span class="gov-cap-filter-label">Holdings</span>
        <button type="button" class="active" data-hold="" title="Show all companies">All</button>
        <button type="button" data-hold="HOLD" title="Only companies in your Holdings">Holding</button>
      </div>
      <span class="gov-search-meta" id="govmap-count"></span>
    </div>
    <div id="gov-role-chips" class="gov-role-chips" hidden></div>
    <div id="govhub-hero"></div>
    <div class="table-wrap">
      <table class="report strat-table">
        <thead><tr id="govmap-head"></tr></thead>
        <tbody id="govmap-body"></tbody>
      </table>
    </div>
  </div>
</details>
{GOVERNANCE_MAP_CSS}
<script>
(function() {{
  const DATA = {data_json};
  const COLS = {cols_str};
  let expanded = null;
  let searchQuery = {initial}.trim().toLowerCase();
  let viewMode = "director"; // director | company | role
  let capFilter = ""; // "" | NC | MIC | SC | MC | LC
  let holdFilter = ""; // "" | HOLD
  let sortCol = "dir_score";
  let sortDir = -1; // -1 = high→low (top), +1 = low→high
  const ROLE_FAMILIES = [
    {{ id: "compliance", label: "Compliance / CS", keys: ["compliance", "company secretary"] }},
    {{ id: "cfo", label: "CFO", keys: ["chief financial", "cfo"] }},
    {{ id: "ceo", label: "CEO / MD", keys: ["chief executive", "managing director", "ceo-md", "ceo", "md"] }},
    {{ id: "executive", label: "Executive Dir", keys: ["executive director"] }},
    {{ id: "chairman", label: "Chairman", keys: ["chairman", "chairperson"] }},
    {{ id: "independent", label: "Independent", keys: ["independent"] }},
    {{ id: "non_exec", label: "Non-Exec", keys: ["non-exec-ex-ind"] }},
    {{ id: "nominee", label: "Nominee", keys: ["nominee"] }},
    {{ id: "promoter", label: "Promoter", keys: ["promoter"] }},
    {{ id: "shareholder", label: "Shareholder Dir", keys: ["shareholder director"] }},
    {{ id: "coo", label: "COO", keys: ["chief operating", "coo"] }},
    {{ id: "cto", label: "CTO", keys: ["chief technology", "cto"] }},
  ];
  const SHORT_ROLE_TOKENS = new Set([
    "cfo", "ceo", "coo", "cto", "chro", "cmo", "cio", "cro", "wtd", "md", "cs",
  ]);

  function esc(s) {{
    return String(s == null ? "" : s)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  }}
  function keyMatchesDesignation(d, key) {{
    const k = String(key || "").trim().toLowerCase();
    if (!d || !k) return false;
    // Executive Dir — not Non-Executive
    if (k === "executive director") {{
      return d.includes("executive director")
        && !d.includes("non-executive")
        && !d.includes("non executive");
    }}
    // Non-Exec excl Independent (NED / Non Independent)
    if (k === "non-exec-ex-ind") {{
      return (d.includes("non-executive") || d.includes("non executive"))
        && !d.includes("independent");
    }}
    // Short tokens (cfo/ceo/cto/md…) — word-ish boundary so "cto" ≠ "direcTor"
    if (SHORT_ROLE_TOKENS.has(k) || k.length <= 3) {{
      if (!/^[a-z0-9-]{{1,12}}$/i.test(k)) return false;
      const re = new RegExp("(?:^|[^a-z0-9])" + k + "(?:[^a-z0-9]|$)", "i");
      return re.test(d);
    }}
    return d.includes(k);
  }}
  function fmtScore(v) {{
    if (v == null || isNaN(v)) return "—";
    return `<span class="gov-score">${{Number(v).toFixed(1)}}</span>`;
  }}
  function fmtDirector(r) {{
    const badge = r.din_backed
      ? `<span class="gov-badge">DIN</span>`
      : `<span class="gov-badge name">name</span>`;
    const suspect = r.name_collision
      ? `<span class="gov-badge suspect" title="Name-only match with many boards — may be several people">suspect</span>`
      : "";
    const din = r.din ? `DIN ${{esc(r.din)}}` : "name match";
    const bridge = r.bridge ? ` · bridge` : "";
    const collision = r.name_collision ? ` · likely name collision` : "";
    return (
      `<div class="gov-dir-cell">` +
      `<div><strong>${{esc(r.name)}}</strong>${{badge}}${{suspect}}</div>` +
      `<div class="sub">${{din}}${{bridge}}${{collision}}</div>` +
      `</div>`
    );
  }}
  function fmtMcap(v) {{
    if (v == null || isNaN(v)) {{
      return `<span class="gov-mcap-label">Mcap</span>—`;
    }}
    return `<span class="gov-mcap-label">Mcap</span><strong>${{Number(v).toFixed(1)}} Cr</strong>`;
  }}
  function webHref(w) {{
    if (!w) return "";
    return /^https?:\\/\\//i.test(w) ? w : ("https://" + w);
  }}
  function sortValue(r, colId) {{
    switch (colId) {{
      case "rank": return Number(r.rank);
      case "director": return String(r.name || "").toLowerCase();
      case "dir_score": return Number(r.dir_score);
      case "board_count": return Number(r.board_count);
      case "big_n": return Number(r.big_n);
      case "small_n": return Number(r.small_n);
      case "tickers": return String(r.tickers || "").toLowerCase();
      default: return 0;
    }}
  }}
  function compareRows(a, b) {{
    const col = COLS.find(c => c.id === sortCol) || COLS[2];
    const av = sortValue(a, col.id);
    const bv = sortValue(b, col.id);
    if (col.sort === "text") {{
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    }}
    const an = (av == null || isNaN(av)) ? -Infinity : av;
    const bn = (bv == null || isNaN(bv)) ? -Infinity : bv;
    if (an < bn) return -1 * sortDir;
    if (an > bn) return 1 * sortDir;
    return 0;
  }}
  function rowMatches(r, q) {{
    if (!q) return true;
    const bits = [
      r.name, r.din, r.tickers, r.person_id
    ].map(x => String(x || "").toLowerCase());
    if (bits.some(b => b.includes(q))) return true;
    return (r.companies || []).some(c => {{
      const t = String(c.ticker || "").toLowerCase();
      const n = String(c.name || "").toLowerCase();
      const m = String(c.market || "").toLowerCase();
      return t.includes(q) || n.includes(q) || m.includes(q);
    }});
  }}
  function designationText(c) {{
    return String(c && c.designation ? c.designation : "").toLowerCase();
  }}
  function roleNeedle() {{
    return String(searchQuery || "").trim().toLowerCase();
  }}
  function activeRoleFamily() {{
    const q = roleNeedle();
    if (!q) return null;
    return ROLE_FAMILIES.find(f =>
      f.id === q ||
      f.label.toLowerCase() === q ||
      f.keys.some(k => q === k.trim() || q.includes(k.trim()))
    ) || null;
  }}
  function companyMatchesCap(c) {{
    if (!capFilter) return true;
    return String(c.cap_code || "").toUpperCase() === capFilter;
  }}
  function companyMatchesHold(c) {{
    if (!holdFilter) return true;
    return !!c.is_holding;
  }}
  function companyMatchesFilters(c) {{
    return companyMatchesCap(c) && companyMatchesHold(c);
  }}
  function matchingCompanies(r) {{
    return (r.companies || []).filter(companyMatchesFilters);
  }}
  /** Cap/Hold filter which directors appear; always show full board in the row. */
  function displayCompanies(r) {{
    const all = r.companies || [];
    if (!activeFilters()) return all;
    const hits = [];
    const rest = [];
    all.forEach(c => {{
      if (companyMatchesFilters(c)) hits.push(c);
      else rest.push(c);
    }});
    return hits.concat(rest);
  }}
  function rowHasMatchingCompany(r) {{
    if (!capFilter && !holdFilter) return true;
    return matchingCompanies(r).length > 0;
  }}
  function activeFilters() {{
    return !!(capFilter || holdFilter);
  }}
  function filterBits() {{
    const bits = [];
    if (capFilter) bits.push(`Cap ${{capFilter}}`);
    if (holdFilter) bits.push("Holding");
    return bits;
  }}
  function designationMatchesRole(desig, needle, family) {{
    const d = String(desig || "").toLowerCase();
    if (!d) return false;
    if (family) return family.keys.some(k => keyMatchesDesignation(d, k));
    if (!needle) return false;
    // Free-text role search — still protect short tokens like cto/cfo.
    if (SHORT_ROLE_TOKENS.has(needle) || needle.length <= 3) {{
      return keyMatchesDesignation(d, needle);
    }}
    return d.includes(needle);
  }}
  function seatMatchesRole(c) {{
    return designationMatchesRole(designationText(c), roleNeedle(), activeRoleFamily());
  }}
  function roleSeatCount(r) {{
    return (r.companies || []).filter(seatMatchesRole).length;
  }}
  function hasRole(r) {{
    return roleSeatCount(r) > 0;
  }}
  function resolveHub() {{
    if (!searchQuery) return null;
    const q = searchQuery;
    let exact = null;
    const byTicker = {{}};
    DATA.forEach(r => {{
      (r.companies || []).forEach(c => {{
        const t = String(c.ticker || "").toUpperCase();
        if (!t) return;
        if (!byTicker[t]) byTicker[t] = c;
        if (t.toLowerCase() === q) exact = c;
      }});
    }});
    if (exact) return exact;
    const nameHits = Object.values(byTicker).filter(c => {{
      const n = String(c.name || "").toLowerCase();
      const t = String(c.ticker || "").toLowerCase();
      return n.includes(q) || t.includes(q);
    }});
    if (nameHits.length === 1) return nameHits[0];
    return null;
  }}
  function sitsOnHub(r, hub) {{
    if (!hub) return false;
    const ht = String(hub.ticker || "").toUpperCase();
    return (r.companies || []).some(c => String(c.ticker || "").toUpperCase() === ht);
  }}
  function compareRoleRows(a, b) {{
    const ra = roleSeatCount(a);
    const rb = roleSeatCount(b);
    if (ra !== rb) return rb - ra;
    return compareRows(a, b);
  }}
  function filteredRows() {{
    let rows;
    if (viewMode === "company") {{
      const hub = resolveHub();
      rows = hub
        ? DATA.filter(r => sitsOnHub(r, hub))
        : (searchQuery ? DATA.filter(r => rowMatches(r, searchQuery)) : []);
      rows.sort(compareRows);
    }} else if (viewMode === "role") {{
      if (!roleNeedle()) {{
        rows = [];
      }} else {{
        rows = DATA.filter(hasRole);
        rows.sort(compareRoleRows);
      }}
    }} else {{
      rows = DATA.filter(r => rowMatches(r, searchQuery));
      rows.sort(compareRows);
    }}
    if (capFilter || holdFilter) rows = rows.filter(rowHasMatchingCompany);
    return rows;
  }}
  function renderRoleChips() {{
    const wrap = document.getElementById("gov-role-chips");
    if (!wrap) return;
    if (viewMode !== "role") {{
      wrap.hidden = true;
      wrap.innerHTML = "";
      return;
    }}
    wrap.hidden = false;
    const fam = activeRoleFamily();
    wrap.innerHTML = ROLE_FAMILIES.map(f => {{
      const active = fam && fam.id === f.id;
      return `<button type="button" class="gov-role-chip${{active ? " active" : ""}}" data-role="${{esc(f.id)}}">${{esc(f.label)}}</button>`;
    }}).join("");
    wrap.querySelectorAll("[data-role]").forEach(btn => {{
      btn.onclick = () => {{
        const id = btn.getAttribute("data-role");
        const family = ROLE_FAMILIES.find(f => f.id === id);
        searchQuery = family ? family.keys[0] : id;
        const searchEl = document.getElementById("govmap-search");
        if (searchEl) searchEl.value = family ? family.label : id;
        render();
      }};
    }});
  }}
  function renderHubHero(rows) {{
    const el = document.getElementById("govhub-hero");
    if (!el) return;
    if (viewMode === "role") {{
      const fam = activeRoleFamily();
      const label = fam ? fam.label : (roleNeedle() || "Role");
      if (!roleNeedle()) {{
        el.innerHTML =
          `<div class="govhub-hero"><div class="govhub-sub">` +
          `Pick a role chip or search e.g. <strong>compliance</strong>, <strong>cfo</strong>, <strong>company secretary</strong> — ` +
          `shows multi-board people who hold that title on one or more seats.` +
          `</div></div>`;
        return;
      }}
      const multiRole = rows.filter(r => roleSeatCount(r) >= 2).length;
      const roleCos = new Set();
      rows.forEach(r => (r.companies || []).forEach(c => {{
        if (seatMatchesRole(c) && c.ticker) roleCos.add(String(c.ticker).toUpperCase());
      }}));
      el.innerHTML =
        `<div class="govhub-hero"><div class="govhub-hero-top"><div>` +
        `<div class="govhub-name">${{esc(label)}}</div>` +
        `<p class="govhub-sub">Role hub · same title across companies (Yahoo designations)</p>` +
        `</div><div class="govhub-stats">` +
        `<div><b>${{rows.length}}</b><span>people</span></div>` +
        `<div><b>${{multiRole}}</b><span>role on 2+</span></div>` +
        `<div><b>${{roleCos.size}}</b><span>companies</span></div>` +
        `</div></div></div>`;
      return;
    }}
    if (viewMode !== "company") {{
      el.innerHTML = "";
      return;
    }}
    const hub = resolveHub();
    if (!hub) {{
      el.innerHTML =
        `<div class="govhub-hero"><div class="govhub-sub">` +
        (searchQuery
          ? `No unique company match for “${{esc(searchQuery)}}”. Try an exact ticker (e.g. KAMDHENU).`
          : `Search a ticker to open <strong>Gov Hub</strong> — multi-board directors who share that board.`) +
        `</div></div>`;
      return;
    }}
    const holdTag = hub.is_holding
      ? `<span class="gov-co-tags"><span class="gov-tag gov-tag-hold">Holding</span></span>`
      : "";
    const smeTag = hub.is_sme
      ? `<span class="gov-co-tags"><span class="gov-tag gov-tag-sme" title="NSE Emerge / SME listing">SME</span></span>`
      : "";
    const web = webHref(hub.website);
    const webLink = web
      ? `<a href="${{esc(web)}}" target="_blank" rel="noopener noreferrer">Web</a>`
      : "";
    const mcapLabel = (hub.market_cap_cr != null && !isNaN(hub.market_cap_cr))
      ? `${{Number(hub.market_cap_cr).toFixed(1)}} Cr`
      : "—";
    el.innerHTML =
      `<div class="govhub-hero"><div class="govhub-hero-top"><div>` +
      `<div class="govhub-name">${{esc(hub.name || hub.ticker)}}${{holdTag}}${{smeTag}}</div>` +
      `<p class="govhub-sub">${{esc(hub.ticker)}} · ${{esc(hub.market || "")}} · board hub</p>` +
      `<div class="gov-co-links" style="margin-top:8px">` +
      `<a href="${{esc(hub.sc || "#")}}" target="_blank" rel="noopener noreferrer">SC</a>` +
      `<a href="${{esc(hub.tv || "#")}}" target="_blank" rel="noopener noreferrer">TV</a>` +
      webLink +
      `</div></div><div class="govhub-stats">` +
      `<div><b>${{rows.length}}</b><span>on map</span></div>` +
      `<div><b>${{mcapLabel}}</b><span>mcap</span></div>` +
      `</div></div></div>`;
  }}
  function renderCompanies(r) {{
    const hub = viewMode === "company" ? resolveHub() : null;
    const hubT = hub ? String(hub.ticker || "").toUpperCase() : "";
    const bd = r.score_breakdown || {{}};
    const roleN = viewMode === "role" ? roleSeatCount(r) : 0;
    const cosList = displayCompanies(r);
    const matchN = matchingCompanies(r).length;
    const filterNote = filterBits().length
      ? ` · filter <strong>${{esc(filterBits().join(" · "))}}</strong> hit ${{matchN}}/${{cosList.length}} (all boards shown)`
      : "";
    const breakdown =
      `<div class="gov-breakdown">` +
      (viewMode === "role"
        ? `Role seats <strong>${{roleN}}</strong> · `
        : "") +
      `Score base ${{bd.base != null ? bd.base : "—"}}` +
      ` · bonus ${{bd.bonus != null ? bd.bonus : 0}}` +
      ` · overload −${{bd.overload_penalty != null ? bd.overload_penalty : 0}}` +
      ` · match ×${{bd.match_weight != null ? bd.match_weight : "—"}}` +
      ` · big ${{r.big_n || 0}} / small ${{r.small_n || 0}}` +
      filterNote +
      `</div>`;
    if (!cosList.length) {{
      return breakdown + `<div class="gov-empty">No companies on this board.</div>`;
    }}
    const cos = cosList.map((c, i) => {{
      const about = c.about || "";
      const long = about.length > 180;
      const web = webHref(c.website);
      const webLink = web
        ? `<a href="${{esc(web)}}" target="_blank" rel="noopener noreferrer">Web</a>`
        : "";
      const aboutHtml = about
        ? `<div class="gov-about${{long ? " collapsed" : ""}}" id="gov-about-${{esc(r.person_id)}}-${{i}}">${{esc(about)}}</div>` +
          (long
            ? `<button type="button" class="gov-about-more" data-target="gov-about-${{esc(r.person_id)}}-${{i}}">Show more</button>`
            : "")
        : `<div class="gov-about muted">No about text yet</div>`;
      const isHub = hubT && String(c.ticker || "").toUpperCase() === hubT;
      const isRole = viewMode === "role" && seatMatchesRole(c);
      const isFilterHit = activeFilters() && companyMatchesFilters(c);
      const isFilterMiss = activeFilters() && !companyMatchesFilters(c);
      const highlight = isHub || isRole || isFilterHit || (searchQuery && viewMode !== "role" && (
        String(c.ticker || "").toLowerCase().includes(searchQuery) ||
        String(c.name || "").toLowerCase().includes(searchQuery)
      ));
      const holdTag = c.is_holding
        ? `<span class="gov-co-tags"><span class="gov-tag gov-tag-hold" title="In your Holdings portfolio">Holding</span></span>`
        : "";
      const smeTag = c.is_sme
        ? `<span class="gov-co-tags"><span class="gov-tag gov-tag-sme" title="NSE Emerge / SME listing">SME</span></span>`
        : "";
      const capCode = String(c.cap_code || "").toUpperCase();
      const capTag = capCode
        ? `<span class="gov-co-tags"><span class="gov-cap-tag gov-cap-${{capCode.toLowerCase()}}" title="${{esc(c.cap_label || capCode)}}">${{esc(capCode)}}</span></span>`
        : "";
      const coCls = [
        "gov-co",
        isRole ? "role-hit" : "",
        isFilterHit ? "filter-hit" : "",
        isFilterMiss ? "filter-miss" : "",
      ].filter(Boolean).join(" ");
      const coStyle = highlight && !isRole && !isFilterHit
        ? ' style="border-color:#93c5fd;background:#f8fbff"'
        : "";
      return (
        `<div class="${{coCls}}"${{coStyle}}>` +
        `<div class="gov-co-top">` +
        `<div>` +
        `<div class="gov-co-name">${{esc(c.name || c.ticker)}}${{capTag}}${{smeTag}}${{holdTag}}</div>` +
        `<div class="gov-co-sub">${{esc(c.ticker)}} · ${{esc(c.market || "")}} · ${{esc(c.designation || "Director")}}</div>` +
        `</div>` +
        `<div class="gov-co-mcap">${{fmtMcap(c.market_cap_cr)}}</div>` +
        `</div>` +
        `<div class="gov-co-links">` +
        `<a href="${{esc(c.sc || "#")}}" target="_blank" rel="noopener noreferrer">SC</a>` +
        `<a href="${{esc(c.tv || "#")}}" target="_blank" rel="noopener noreferrer">TV</a>` +
        webLink +
        `</div>` +
        aboutHtml +
        `</div>`
      );
    }}).join("");
    return breakdown + `<div class="gov-cos">${{cos}}</div>`;
  }}
  function fmtTickers(r) {{
    const cos = displayCompanies(r);
    if (!cos.length) return esc(r.tickers || "—");
    const hub = viewMode === "company" ? resolveHub() : null;
    const hubT = hub ? String(hub.ticker || "").toUpperCase() : "";
    return (
      `<span class="gov-tickers">` +
      cos.map((c) => {{
        const raw = String(c.ticker || "");
        if (!raw) return "";
        const t = esc(raw);
        const isHub = hubT && raw.toUpperCase() === hubT;
        let name = t;
        if (isHub) name = `<span class="gov-ticker-focus" title="Hub ticker">${{t}}</span>`;
        else if (c.is_holding) name = `<span class="gov-ticker-hold" title="In your Holdings">${{t}}</span>`;
        const tags = [];
        const code = String(c.cap_code || "").toUpperCase();
        if (code) {{
          const tip = esc(c.cap_label || code);
          const cls = "gov-cap-" + code.toLowerCase();
          tags.push(`<span class="gov-cap-tag ${{cls}}" title="${{tip}}">${{esc(code)}}</span>`);
        }}
        if (c.is_sme) {{
          tags.push(`<span class="gov-tag gov-tag-sme" title="NSE Emerge / SME listing">SME</span>`);
        }}
        if (c.is_holding) {{
          tags.push(`<span class="gov-tag gov-tag-hold" title="In your Holdings">Holding</span>`);
        }}
        const tagHtml = tags.length
          ? `<div class="gov-ticker-tags">${{tags.join("")}}</div>`
          : "";
        const hit = activeFilters() && companyMatchesFilters(c);
        const miss = activeFilters() && !companyMatchesFilters(c);
        const stackCls = [
          "gov-ticker-stack",
          hit ? "filter-hit" : "",
          miss ? "filter-miss" : "",
        ].filter(Boolean).join(" ");
        return `<span class="${{stackCls}}"><span>${{name}}</span>${{tagHtml}}</span>`;
      }}).join("") +
      `</span>`
    );
  }}
  function fmtCell(c, r) {{
    switch (c.id) {{
      case "rank": return r.rank != null ? String(r.rank) : "—";
      case "director": return fmtDirector(r);
      case "dir_score": return fmtScore(r.dir_score);
      case "board_count": return r.board_count != null ? String(r.board_count) : "—";
      case "big_n": return r.big_n != null ? String(r.big_n) : "0";
      case "small_n": return r.small_n != null ? String(r.small_n) : "0";
      case "tickers": return fmtTickers(r);
      default: return "—";
    }}
  }}
  function renderHead() {{
    const th = document.getElementById("govmap-head");
    if (!th) return;
    th.innerHTML = "";
    COLS.forEach(c => {{
      const cell = document.createElement("th");
      cell.className = "gov-sortable";
      const active = sortCol === c.id;
      const arrow = active ? (sortDir < 0 ? "↓" : "↑") : "↕";
      cell.innerHTML =
        `<span>${{c.label}}</span>` +
        `<span class="gov-sort-ind${{active ? " active" : ""}}" title="Click to sort high/low">${{arrow}}</span>`;
      cell.title = "Click to sort (↓ high / ↑ low)";
      cell.onclick = (e) => {{
        e.stopPropagation();
        if (sortCol === c.id) sortDir *= -1;
        else {{
          sortCol = c.id;
          sortDir = (c.sort === "text") ? 1 : -1;
        }}
        render();
      }};
      th.appendChild(cell);
    }});
  }}
  function render() {{
    const tb = document.getElementById("govmap-body");
    const countEl = document.getElementById("govmap-count");
    const metaEl = document.getElementById("govmap-meta");
    const titleEl = document.querySelector("#govmap-wrap > summary > span:first-child");
    if (!tb) return;
    renderHead();
    const rows = filteredRows();
    const hub = viewMode === "company" ? resolveHub() : null;
    renderRoleChips();
    renderHubHero(rows);
    if (titleEl) {{
      titleEl.textContent =
        viewMode === "company" ? "Gov Hub" :
        viewMode === "role" ? "Gov Role" : "Governance Map";
    }}
    if (countEl) {{
      const filterBit = filterBits().length ? ` · ${{filterBits().join(" · ")}}` : "";
      if (viewMode === "company" && hub) {{
        countEl.textContent = `Hub · ${{hub.ticker}} · ${{rows.length}} directors${{filterBit}}`;
      }} else if (viewMode === "role") {{
        const multi = rows.filter(r => roleSeatCount(r) >= 2).length;
        countEl.textContent = roleNeedle()
          ? `Role · ${{rows.length}} people · ${{multi}} on 2+${{filterBit}}`
          : "Pick a role";
      }} else if (searchQuery || activeFilters()) {{
        countEl.textContent = `${{rows.length}} of ${{DATA.length}} match${{filterBit}}`;
      }} else {{
        countEl.textContent = `${{DATA.length}} directors`;
      }}
    }}
    if (metaEl) {{
      const sortHint = sortDir < 0 ? "high→low" : "low→high";
      const filterBit = filterBits().length ? ` · ${{filterBits().join(" · ")}} only` : "";
      if (viewMode === "company") {{
        metaEl.textContent = hub
          ? `${{rows.length}} on ${{hub.ticker}} · sorted ${{sortHint}}${{filterBit}} · click row for seats`
          : `Gov Hub · search a ticker · sorted ${{sortHint}}${{filterBit}}`;
      }} else if (viewMode === "role") {{
        metaEl.textContent = roleNeedle()
          ? `${{rows.length}} with role · sorted by role seats${{filterBit}} · click row`
          : `Gov Role · pick Compliance / CFO / …`;
      }} else {{
        metaEl.textContent = (searchQuery || activeFilters())
          ? `${{rows.length}} match · sorted ${{sortHint}}${{filterBit}} · click row for companies`
          : `${{DATA.length}} directors · sorted ${{sortHint}} · click headers / rows`;
      }}
    }}
    tb.innerHTML = "";
    if (!rows.length) {{
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = COLS.length;
      let emptyMsg = `No directors match “${{esc(searchQuery)}}”.`;
      if (viewMode === "company" && !searchQuery) {{
        emptyMsg = "Enter a ticker above to list multi-board directors on that stock.";
      }} else if (viewMode === "company" && hub) {{
        emptyMsg = `No map directors sit on ${{esc(hub.ticker)}}.`;
      }} else if (viewMode === "role" && !roleNeedle()) {{
        emptyMsg = "Choose a role chip (Compliance / CFO / …) or type a designation keyword.";
      }} else if (viewMode === "role") {{
        emptyMsg = `No map people hold a designation matching “${{esc(searchQuery)}}”.`;
      }} else if (activeFilters() && !searchQuery) {{
        emptyMsg = `No directors have a ${{esc(filterBits().join(" · "))}} company on the map.`;
      }} else if (activeFilters()) {{
        emptyMsg = `No matches with ${{esc(filterBits().join(" · "))}}.`;
      }}
      td.innerHTML = `<div class="gov-empty">${{emptyMsg}}</div>`;
      tr.appendChild(td);
      tb.appendChild(tr);
      return;
    }}
    // Auto-expand single stock hit so company cards are visible.
    if (searchQuery && rows.length === 1) {{
      expanded = rows[0].person_id;
    }} else if (expanded && !rows.some(r => r.person_id === expanded)) {{
      expanded = null;
    }}
    rows.forEach((r, idx) => {{
      const open = expanded === r.person_id;
      const tr = document.createElement("tr");
      tr.className = "strat-row" + (open ? " expanded" : "") + (idx < 3 ? " top3" : "");
      tr.onclick = (e) => {{
        if (e.target.closest("a,button,th")) return;
        expanded = expanded === r.person_id ? null : r.person_id;
        render();
      }};
      COLS.forEach(c => {{
        const td = document.createElement("td");
        td.innerHTML = fmtCell(c, r);
        tr.appendChild(td);
      }});
      tb.appendChild(tr);
      if (open) {{
        const tr2 = document.createElement("tr");
        tr2.className = "strat-expand";
        const td = document.createElement("td");
        td.colSpan = COLS.length;
        td.innerHTML = renderCompanies(r);
        tr2.appendChild(td);
        tb.appendChild(tr2);
      }}
    }});
    tb.querySelectorAll(".gov-about-more").forEach(btn => {{
      btn.onclick = (e) => {{
        e.stopPropagation();
        const el = document.getElementById(btn.getAttribute("data-target"));
        if (!el) return;
        const collapsed = el.classList.toggle("collapsed");
        btn.textContent = collapsed ? "Show more" : "Show less";
      }};
    }});
  }}
  function setViewMode(mode) {{
    if (mode === "company") viewMode = "company";
    else if (mode === "role") viewMode = "role";
    else viewMode = "director";
    const hubBtn = document.getElementById("govmap-mode-hub");
    const dirBtn = document.getElementById("govmap-mode-dir");
    const roleBtn = document.getElementById("govmap-mode-role");
    if (hubBtn) hubBtn.classList.toggle("active", viewMode === "company");
    if (dirBtn) dirBtn.classList.toggle("active", viewMode === "director");
    if (roleBtn) roleBtn.classList.toggle("active", viewMode === "role");
    const searchEl = document.getElementById("govmap-search");
    if (searchEl) {{
      searchEl.placeholder =
        viewMode === "role"
          ? "Search role e.g. compliance, cfo, company secretary…"
          : viewMode === "company"
            ? "Search ticker or company name…"
            : "Search ticker, company, or director…";
    }}
    expanded = null;
    render();
  }}
  const hubBtn = document.getElementById("govmap-mode-hub");
  const dirBtn = document.getElementById("govmap-mode-dir");
  const roleBtn = document.getElementById("govmap-mode-role");
  if (hubBtn) hubBtn.onclick = () => setViewMode("company");
  if (dirBtn) dirBtn.onclick = () => setViewMode("director");
  if (roleBtn) roleBtn.onclick = () => setViewMode("role");
  const capFilterEl = document.getElementById("govmap-cap-filter");
  if (capFilterEl) {{
    capFilterEl.querySelectorAll("button[data-cap]").forEach(btn => {{
      btn.onclick = (e) => {{
        e.stopPropagation();
        capFilter = String(btn.getAttribute("data-cap") || "").toUpperCase();
        capFilterEl.querySelectorAll("button[data-cap]").forEach(b => {{
          b.classList.toggle("active", String(b.getAttribute("data-cap") || "").toUpperCase() === capFilter);
        }});
        render();
      }};
    }});
  }}
  const holdFilterEl = document.getElementById("govmap-hold-filter");
  if (holdFilterEl) {{
    holdFilterEl.querySelectorAll("button[data-hold]").forEach(btn => {{
      btn.onclick = (e) => {{
        e.stopPropagation();
        holdFilter = String(btn.getAttribute("data-hold") || "").toUpperCase();
        holdFilterEl.querySelectorAll("button[data-hold]").forEach(b => {{
          b.classList.toggle(
            "active",
            String(b.getAttribute("data-hold") || "").toUpperCase() === holdFilter
          );
        }});
        render();
      }};
    }});
  }}
  const searchEl = document.getElementById("govmap-search");
  if (searchEl) {{
    searchEl.oninput = (e) => {{
      searchQuery = String(e.target.value || "").trim().toLowerCase();
      render();
    }};
    if (searchQuery) searchEl.focus();
  }}
  // Open Gov Hub when Streamlit search already has a ticker-like query.
  if (searchQuery && resolveHub()) setViewMode("company");
  else render();
}})();
</script>
"""
    # Prefer light shell without PEAD expand CSS noise.
    title_html = (
        f'<h1 class="fund-title">{html.escape(title)}</h1>' if title.strip() else ""
    )
    body = (
        f'<div class="fund-page">'
        f"{title_html}"
        f'<div class="fund-sections">{section}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title or "Governance Map")}</title>'
            f"{_REPORT_CSS}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{body}"


def governance_map_iframe_height(row_count: int) -> int:
    return min(2400, max(520, 360 + min(row_count, 40) * 28))
