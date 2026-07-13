"""100X Formula dashboard — PEAD-style interactive table."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

import pandas as pd

from stocks.dashboards.expand_panel_html import EXPAND_PANEL_JS
from stocks.core.config import (
    FORMULA_100X_CFO_EBIT_MIN,
    FORMULA_100X_CFO_MCAP_MIN,
    FORMULA_100X_EBT_CAPITAL_MIN,
)
from stocks.core.json_utils import json_dumps, json_safe_obj, json_safe_scalar
from stocks.core.text_utils import safe_str
from stocks.shared.corp_tags import corp_tags_dict_for_ticker
from stocks.shared.links import screener_url, tradingview_url
from stocks.strategies.pead2.html import (
    _PEAD2_DASHBOARD_CSS,
    _PEAD2_FONT_LINKS,
    format_generated_ist,
)

_100X_UI_BUILD = "2026-07-12c"


def _rows_for_json(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for _, row in df.iterrows():
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        rows.append(
            json_safe_obj(
                {
                    "ticker": ticker,
                    "name": safe_str(row.get("name")),
                    "market": market,
                    "market_cap_cr": json_safe_scalar(row.get("market_cap_cr")),
                    "price": json_safe_scalar(row.get("price")),
                    "sector": safe_str(row.get("sector")) or None,
                    "industry": safe_str(row.get("industry")) or None,
                    "criteria_score": json_safe_scalar(row.get("criteria_score")),
                    "cfo_ebit_pct": json_safe_scalar(row.get("cfo_ebit_pct")),
                    "ebt_capital_pct": json_safe_scalar(row.get("ebt_capital_pct")),
                    "cfo_mcap_pct": json_safe_scalar(row.get("cfo_mcap_pct")),
                    "cfo_latest_cr": json_safe_scalar(row.get("cfo_latest_cr")),
                    "pass_rising_cfo": bool(row.get("pass_rising_cfo")),
                    "pass_cfo_ebit": bool(row.get("pass_cfo_ebit")),
                    "pass_ebt_capital": bool(row.get("pass_ebt_capital")),
                    "pass_cfo_mcap": bool(row.get("pass_cfo_mcap")),
                    "formula_pass": bool(row.get("formula_pass")),
                    "sc": row.get("screener_link") or screener_url(ticker, market),
                    "tv": row.get("tv_link") or tradingview_url(ticker, market),
                    **corp_tags_dict_for_ticker(ticker),
                }
            )
        )
        snapshot = row.get("snapshot")
        snap_price = json_safe_scalar(snapshot.get("price") if isinstance(snapshot, dict) else None)
        if isinstance(snapshot, dict) and snap_price is not None:
            snap = dict(snapshot)
            mcap = row.get("market_cap_cr")
            if mcap is not None and pd.notna(mcap) and snap.get("market_cap_cr") is None:
                snap["market_cap_cr"] = round(float(mcap), 1)
            rows[-1]["snapshot"] = snap
            if snap.get("long_description"):
                rows[-1]["long_description"] = snap["long_description"]
            if snap.get("website"):
                rows[-1]["website"] = snap["website"]
            for key in (
                "company_sector",
                "company_industry",
                "headquarters",
                "employees",
            ):
                if snap.get(key) is not None:
                    rows[-1][key] = json_safe_scalar(snap.get(key))
        elif json_safe_scalar(row.get("price")) is not None:
            rows[-1]["snapshot"] = {
                "price": rows[-1]["price"],
                "market_cap_cr": rows[-1].get("market_cap_cr"),
                "cagr": None,
                "w52_low": None,
                "w52_high": None,
                "moving_averages": [],
            }
            if row.get("website"):
                rows[-1]["website"] = safe_str(row.get("website"))
            if row.get("long_description"):
                rows[-1]["long_description"] = safe_str(row.get("long_description"))
    return rows


def build_100x_dashboard_html(
    df: pd.DataFrame,
    *,
    title: str = "100X Formula",
    standalone: bool = True,
) -> str:
    updated = format_generated_ist()
    data_json = json_dumps(_rows_for_json(df), separators=(",", ":"))
    cfo_ebit_min = FORMULA_100X_CFO_EBIT_MIN
    ebt_ce_min = FORMULA_100X_EBT_CAPITAL_MIN
    cfo_mcap_min = FORMULA_100X_CFO_MCAP_MIN

    body = f"""
<div class="dash" id="dash">
  <main class="main">
    <div class="topbar">
      <div>
        <h1 class="title">📈 {html.escape(title)}</h1>
        <div class="meta">
          {html.escape(updated)} · panel {_100X_UI_BUILD} · click row for criteria detail
        </div>
      </div>
      <div class="top-actions">
        <button class="icon-btn" id="btn-theme" type="button" title="Toggle theme">Light</button>
        <button class="icon-btn" id="btn-fs" type="button" title="Fullscreen">Fullscreen</button>
      </div>
    </div>
    <div class="toolbar">
      <div class="count" id="count-label">0 companies</div>
      <div class="col-toggle">
        <div class="recent-days quarter-toggle" id="filter-pills">
          <span class="recent-days-label">Show</span>
          <button type="button" class="quarter-btn filter-btn on" data-filter="all">All</button>
          <button type="button" class="quarter-btn filter-btn" data-filter="pass">Pass 4/4</button>
          <button type="button" class="quarter-btn filter-btn" data-filter="partial">Partial</button>
        </div>
      </div>
    </div>
    <div class="table-wrap" id="table-wrap">
      <table id="pead-table">
        <thead><tr id="thead"></tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </main>
</div>
<style>
  .x100-criteria {{
    display: grid;
    gap: 8px;
    max-width: 520px;
  }}
  .x100-rule {{
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 10px;
    align-items: center;
    padding: 8px 10px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--panel-2);
    font-size: 12px;
  }}
  .x100-rule.pass {{ border-color: rgba(34, 197, 94, 0.35); background: rgba(34, 197, 94, 0.08); }}
  .x100-rule.fail {{ border-color: rgba(239, 68, 68, 0.25); }}
  .x100-badge {{
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 999px;
    white-space: nowrap;
  }}
  .x100-badge.pass {{ color: #166534; background: rgba(34, 197, 94, 0.18); }}
  .x100-badge.fail {{ color: #991b1b; background: rgba(239, 68, 68, 0.12); }}
  .x100-val {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
</style>
<script>
{EXPAND_PANEL_JS}
const DATA = {data_json};
const THRESH = {{
  cfo_ebit: {cfo_ebit_min},
  ebt_ce: {ebt_ce_min},
  cfo_mcap: {cfo_mcap_min},
}};
let filterMode = "all";
let sortCol = "criteria_score";
let sortDir = -1;
let expandedTicker = null;

const COLS = [
  {{id:"company", label:"Company", fmt:"company"}},
  {{id:"criteria_score", label:"Score", fmt:"score"}},
  {{id:"cfo_ebit_pct", label:"CFO/EBIT%", fmt:"pct"}},
  {{id:"ebt_capital_pct", label:"EBT/CE%", fmt:"pct"}},
  {{id:"cfo_mcap_pct", label:"CFO/MCap%", fmt:"pct"}},
  {{id:"cfo_latest_cr", label:"CFO Cr", fmt:"num"}},
  {{id:"market_cap_cr", label:"Mkt cap Cr", fmt:"num"}},
  {{id:"price", label:"Price", fmt:"num2"}},
];

function num(v) {{
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}}
function fmtNum(v, d=1) {{
  const n = num(v);
  if (n === null) return "—";
  return n.toLocaleString("en-IN", {{maximumFractionDigits: d, minimumFractionDigits: d}});
}}
function fmtPct(v) {{
  const n = num(v);
  if (n === null) return "—";
  return n.toFixed(1) + "%";
}}
function fmtScore(v) {{
  const n = num(v);
  if (n === null) return "—";
  const cls = n >= 4 ? "pos" : n >= 2 ? "" : "neg";
  return `<span class="pead-chip ${{cls}}">${{n}}/4</span>`;
}}
function fmtCompany(r) {{
  const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  const name = esc(r.name || r.ticker);
  const tk = esc(r.ticker || "");
  const sub = [r.sector, r.industry].filter(Boolean).map(esc).join(" · ");
  const tags = fmtCorpTags(r);
  const snap = rowSnapshot(r);
  const web = snap?.website || r.website;
  let links =
    `<div class="links-inline">` +
    `<a href="${{esc(r.sc||"#")}}" target="_blank" rel="noopener noreferrer">SC</a>` +
    `<a href="${{esc(r.tv||"#")}}" target="_blank" rel="noopener noreferrer">TV</a>`;
  if (web) links += fmtWebsite(web);
  links += `</div>`;
  return (
    `<div class="company-cell">` +
    `<div class="company-name">${{name}} <span class="expand-hint"></span></div>` +
    `<div class="company-sub">${{tk}}${{sub ? " · " + sub : ""}}</div>` +
    links +
    (tags ? `<div class="company-tags-row">${{tags}}</div>` : "") +
    `</div>`
  );
}}
function cell(c, r) {{
  switch (c.fmt) {{
    case "company": return fmtCompany(r);
    case "score": return fmtScore(r.criteria_score);
    case "pct": return fmtPct(r[c.id]);
    case "num2": return fmtNum(r[c.id], 2);
    default: return fmtNum(r[c.id], 1);
  }}
}}
function passesFilter(r) {{
  const s = num(r.criteria_score) || 0;
  if (filterMode === "pass") return s >= 4;
  if (filterMode === "partial") return s >= 1 && s < 4;
  return true;
}}
function render100xScoreRing(score) {{
  const n = Number(score);
  if (isNaN(n)) return "";
  const pct = Math.max(0, Math.min(100, (n / 4) * 100));
  const r = 22;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - pct / 100);
  const color = n >= 4 ? "#22c55e" : n >= 2 ? "#d97706" : "#ef4444";
  return (
    `<div class="pead-score-ring" title="100X score">` +
    `<svg viewBox="0 0 52 52" width="54" height="54" aria-hidden="true">` +
    `<circle cx="26" cy="26" r="${{r}}" fill="none" stroke="currentColor" stroke-width="4" opacity="0.15"/>` +
    `<circle cx="26" cy="26" r="${{r}}" fill="none" stroke="${{color}}" stroke-width="4" ` +
    `stroke-dasharray="${{c.toFixed(2)}}" stroke-dashoffset="${{offset.toFixed(2)}}" ` +
    `stroke-linecap="round" transform="rotate(-90 26 26)"/>` +
    `<text x="26" y="28.5" text-anchor="middle" class="pead-score-ring-txt">${{n}}/4</text>` +
    `</svg></div>`
  );
}}
function render100xHero(r, snap) {{
  const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  const name = r.name || r.ticker;
  const mkt = safeStrMarket(r.market);
  const subParts = [];
  if (mkt && r.ticker) subParts.push(`${{mkt}}: ${{r.ticker}}`);
  else if (r.ticker) subParts.push(String(r.ticker));
  const ind = r.industry || r.sub_sector || r.sector;
  if (ind) subParts.push(String(ind));
  const hq = snap?.headquarters || r.headquarters;
  if (hq) {{
    const city = String(hq).split(",")[0].trim();
    if (city) subParts.push(city);
  }}
  const px = snap?.price ?? r.price;
  const cagr = snap?.cagr;
  const mcap = snap?.market_cap_cr ?? r.market_cap_cr;
  const cagrTxt = cagr == null || isNaN(Number(cagr)) ? "—" : `${{Number(cagr) >= 0 ? "+" : ""}}${{fmtPctNum(Number(cagr))}}%`;
  const mcapTxt = mcap != null && !isNaN(Number(mcap)) ? `${{fmtPctNum(Number(mcap))}} Cr` : "—";
  let about = "";
  const desc = snap?.long_description || r.long_description;
  if (desc) {{
    const long = desc.length > 140;
    about = `<div class="pead-about co-profile-about">` +
      `<p class="co-profile-desc${{long ? "" : " expanded"}}">${{esc(desc)}}</p>` +
      (long ? `<button type="button" class="co-profile-more" aria-expanded="false" onclick="toggleCoAbout(this)">Show more</button>` : "") +
      `</div>`;
  }}
  const tags = fmtCorpTags(r);
  const web = snap?.website || r.website;
  let links =
    `<div class="pead-detail-links">` +
    `<span class="links-inline">` +
    `<a href="${{esc(r.sc || "#")}}" target="_blank" rel="noopener noreferrer">SC</a>` +
    `<a href="${{esc(r.tv || "#")}}" target="_blank" rel="noopener noreferrer">TV</a>` +
    `</span>`;
  if (web) links += `<span class="pead-detail-web">${{fmtWebsite(web)}}</span>`;
  links += `</div>`;
  return (
    `<div class="pead-hero">` +
    `<div class="pead-top">` +
    `<div class="pead-top-left">` +
    `<div class="pead-detail-name">${{esc(name)}}</div>` +
    `<div class="pead-detail-sub">${{esc(subParts.join(" · "))}}</div>` +
    (tags ? `<div class="company-tags-row">${{tags}}</div>` : "") +
    links +
    `</div>` +
    `<div class="pead-top-right">` +
    `<div class="pead-capline">Mkt cap ${{mcapTxt}} · CAGR ${{cagrTxt}}</div>` +
    render100xScoreRing(r.criteria_score) +
    `</div></div>` +
    `<div class="pead-detail-price-row">` +
    `<span class="pead-detail-price">${{px != null ? fmtSnapNum(px) : "—"}}</span>` +
    `</div>` +
    about +
    `</div>`
  );
}}
function render100xCriteria(r) {{
  const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");
  const rules = [
    ["Rising CFO", r.pass_rising_cfo, "Annual operating cash flow trending up"],
    ["CFO / EBIT", r.pass_cfo_ebit, `>${{THRESH.cfo_ebit}}% · got ${{fmtPct(r.cfo_ebit_pct)}}`],
    ["EBT / Capital", r.pass_ebt_capital, `>${{THRESH.ebt_ce}}% · got ${{fmtPct(r.ebt_capital_pct)}}`],
    ["CFO / Mkt cap", r.pass_cfo_mcap, `>${{THRESH.cfo_mcap}}% · got ${{fmtPct(r.cfo_mcap_pct)}}`],
  ];
  let list = "";
  rules.forEach(([label, ok, detail]) => {{
    list += `<div class="x100-rule ${{ok ? "pass" : "fail"}}">` +
      `<span class="x100-badge ${{ok ? "pass" : "fail"}}">${{ok ? "Pass" : "Miss"}}</span>` +
      `<span>${{esc(label)}}</span>` +
      `<span class="x100-val">${{esc(detail)}}</span></div>`;
  }});
  return `<div class="pead-section"><div class="pead-section-title">100X criteria</div>` +
    `<div class="x100-criteria">${{list}}</div></div>`;
}}
function renderExpand(r) {{
  const snap = rowSnapshot(r);
  return `<div class="pead-card">${{render100xHero(r, snap)}}${{render100xCriteria(r)}}</div>`;
}}
function syncExpandPanelWidth() {{
  const wrap = document.getElementById("table-wrap");
  if (!wrap) return;
  const w = wrap.clientWidth;
  document.querySelectorAll("tr.pead-expand td.pead-expand-td").forEach(td => {{
    td.style.width = w + "px";
    td.style.maxWidth = w + "px";
  }});
}}
function renderHead() {{
  const tr = document.getElementById("thead");
  tr.innerHTML = "";
  COLS.forEach(c => {{
    const th = document.createElement("th");
    th.className = c.id === "company" ? "col-company" : "col-num";
    const active = sortCol === c.id;
    const arrow = active ? (sortDir < 0 ? "↓" : "↑") : "↕";
    th.innerHTML = `<span class="th-inner"><span class="th-label">${{c.label}}</span>` +
      `<span class="sort-ind${{active ? " active" : ""}}">${{arrow}}</span></span>`;
    th.onclick = () => {{
      if (sortCol === c.id) sortDir *= -1;
      else {{ sortCol = c.id; sortDir = c.id === "company" ? 1 : -1; }}
      render();
    }};
    tr.appendChild(th);
  }});
}}
function compareRows(a, b, col) {{
  if (col.fmt === "company") {{
    return String(a.name || a.ticker).localeCompare(String(b.name || b.ticker)) * sortDir;
  }}
  const av = num(a[col.id]), bv = num(b[col.id]);
  if (av === null && bv === null) return 0;
  if (av === null) return 1;
  if (bv === null) return -1;
  return (av - bv) * sortDir;
}}
function render() {{
  let rows = DATA.filter(passesFilter);
  const sortColumn = COLS.find(c => c.id === sortCol) || COLS[0];
  rows.sort((a, b) => compareRows(a, b, sortColumn));
  const passN = DATA.filter(r => (num(r.criteria_score) || 0) >= 4).length;
  document.getElementById("count-label").textContent =
    `100X (${{rows.length}} shown · ${{passN}} pass 4/4)`;
  renderHead();
  const tb = document.getElementById("tbody");
  tb.innerHTML = "";
  rows.forEach(r => {{
    const isOpen = expandedTicker === r.ticker;
    const tr = document.createElement("tr");
    tr.className = "pead-row" + (isOpen ? " expanded" : "");
    tr.onclick = e => {{
      if (e.target.closest("a")) return;
      expandedTicker = expandedTicker === r.ticker ? null : r.ticker;
      render();
    }};
    COLS.forEach(c => {{
      const td = document.createElement("td");
      td.className = c.id === "company" ? "company-td" : "col-num";
      td.innerHTML = cell(c, r);
      tr.appendChild(td);
    }});
    tb.appendChild(tr);
    if (isOpen) {{
      const tr2 = document.createElement("tr");
      tr2.className = "pead-expand";
      const td = document.createElement("td");
      td.colSpan = COLS.length;
      td.className = "pead-expand-td";
      td.innerHTML = renderExpand(r);
      tr2.appendChild(td);
      tb.appendChild(tr2);
    }}
  }});
  syncExpandPanelWidth();
}}
document.querySelectorAll(".filter-btn").forEach(btn => {{
  btn.onclick = () => {{
    filterMode = btn.dataset.filter || "all";
    document.querySelectorAll(".filter-btn").forEach(b =>
      b.classList.toggle("on", b.dataset.filter === filterMode));
    render();
  }};
}});
const root = document.documentElement;
const dash = document.getElementById("dash");
const themeKey = "x100-theme";
function loadTheme() {{
  const t = localStorage.getItem(themeKey) || "dark";
  root.setAttribute("data-theme", t);
  document.getElementById("btn-theme").textContent = t === "light" ? "Dark" : "Light";
}}
function toggleTheme() {{
  const next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
  root.setAttribute("data-theme", next);
  localStorage.setItem(themeKey, next);
  document.getElementById("btn-theme").textContent = next === "light" ? "Dark" : "Light";
}}
function toggleFs() {{
  const on = dash.classList.toggle("fs");
  document.body.classList.toggle("fs-active", on);
  document.getElementById("btn-fs").textContent = on ? "Exit fullscreen" : "Fullscreen";
}}
document.getElementById("btn-theme").onclick = toggleTheme;
document.getElementById("btn-fs").onclick = toggleFs;
loadTheme();
render();
window.addEventListener("resize", () => syncExpandPanelWidth());
</script>
"""

    html_open = (
        '<!DOCTYPE html><html lang="en" data-theme="dark"><head>'
        f'<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title>"
        f"{_PEAD2_FONT_LINKS}"
        f"{_PEAD2_DASHBOARD_CSS}</head><body>"
    )
    if standalone:
        return f"{html_open}{body}</body></html>"
    return f"{_PEAD2_FONT_LINKS}{_PEAD2_DASHBOARD_CSS}{body}"


def formula_100x_iframe_height(row_count: int, *, expanded: bool = False) -> int:
    base = min(1500, max(960, 920 + min(row_count, 40) * 2))
    return base + (220 if expanded else 0)
