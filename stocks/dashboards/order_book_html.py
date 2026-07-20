"""Order inflow dashboard — All Orders flat table + By Company summary."""

from __future__ import annotations

import html
import json

import pandas as pd

from stocks.core.json_utils import json_dumps, json_safe_obj, json_safe_scalar
from stocks.core.text_utils import safe_str
from stocks.market.order_inflow import inr_to_cr


_ORDER_BOOK_CSS = """
<style>
  :root {
    --bg: #0f1114;
    --panel: #161a1f;
    --border: #2a3038;
    --text: #f3f4f6;
    --muted: #9ca3af;
    --teal: #2dd4bf;
    --teal-dim: rgba(45, 212, 191, 0.15);
    --green: #4ade80;
    --green-bg: rgba(74, 222, 128, 0.12);
    --link: #5eead4;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
  }
  .ob-wrap { padding: 4px 2px 20px; }
  .ob-title { font-size: 20px; font-weight: 700; margin: 0 0 14px; letter-spacing: -0.02em; }
  .ob-tabs { display: flex; gap: 0; margin-bottom: 14px; border-bottom: 1px solid var(--border); }
  .ob-tab {
    background: none;
    border: none;
    color: var(--muted);
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .ob-tab.on { color: var(--text); border-bottom-color: var(--teal); }
  .ob-filters {
    display: grid;
    grid-template-columns: 1fr 1fr 1.2fr 1.2fr auto;
    gap: 12px;
    align-items: end;
    padding: 12px 14px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    margin-bottom: 0;
  }
  .ob-field label {
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .ob-field select {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    padding: 8px 10px;
    font-size: 12px;
  }
  .ob-slider-wrap label { font-size: 11px; color: var(--muted); font-weight: 600; }
  .ob-slider-val { color: var(--teal); font-weight: 700; }
  input[type=range].ob-range {
    width: 100%;
    accent-color: var(--teal);
    margin-top: 6px;
  }
  .ob-refresh {
    background: transparent;
    border: 1px solid var(--teal);
    color: var(--teal);
    border-radius: 8px;
    padding: 9px 16px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.06em;
    cursor: pointer;
    white-space: nowrap;
    align-self: end;
  }
  .ob-refresh:hover { background: var(--teal-dim); }
  .ob-table-wrap {
    border: 1px solid var(--border);
    border-top: none;
    border-radius: 0 0 10px 10px;
    overflow: auto;
    max-height: 72vh;
    background: var(--panel);
  }
  table.ob-main {
    width: 100%;
    border-collapse: collapse;
    min-width: 980px;
  }
  table.ob-main thead th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: #12151a;
    text-align: left;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
  }
  table.ob-main thead th.sortable:hover { color: var(--text); }
  table.ob-main thead th .sort-icon { opacity: 0.5; margin-left: 4px; font-size: 10px; }
  table.ob-main thead th.sorted { color: var(--teal); }
  table.ob-main tbody td {
    padding: 9px 12px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    vertical-align: middle;
    font-size: 12px;
  }
  table.ob-main tbody tr:hover td { background: rgba(255,255,255,0.02); }
  .ob-co { color: var(--link); font-weight: 600; }
  .ob-cr { color: var(--green); font-weight: 600; white-space: nowrap; }
  .ob-pct {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
  }
  .ob-pct.hi { background: var(--green-bg); color: var(--green); }
  .ob-pct.lo { background: rgba(156,163,175,0.12); color: var(--muted); }
  .ob-pdf a { color: var(--teal); text-decoration: none; font-weight: 600; }
  .ob-pdf a:hover { text-decoration: underline; }
  .ob-empty { padding: 48px; text-align: center; color: var(--muted); }
  .ob-foot {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 16px;
    padding: 10px 12px;
    color: var(--muted);
    font-size: 11px;
    border: 1px solid var(--border);
    border-top: none;
    border-radius: 0 0 10px 10px;
    background: var(--panel);
  }
  .ob-foot button {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: 4px 10px;
    cursor: pointer;
    font-size: 11px;
  }
  .ob-foot button:disabled { opacity: 0.35; cursor: default; }
  /* By-company summary */
  .ob-list { display: flex; flex-direction: column; gap: 2px; margin-top: 14px; }
  .ob-row {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }
  .ob-summary {
    display: grid;
    grid-template-columns: 24px 1fr auto auto auto auto;
    gap: 12px;
    align-items: center;
    padding: 10px 12px;
    cursor: pointer;
  }
  .ob-summary:hover { background: rgba(255,255,255,0.02); }
  .ob-chev { color: var(--muted); font-size: 10px; }
  .ob-row.open .ob-chev::before { content: "▾"; }
  .ob-row:not(.open) .ob-chev::before { content: "▸"; }
  .ob-detail { display: none; padding: 0 12px 12px 36px; border-top: 1px solid var(--border); }
  .ob-row.open .ob-detail { display: block; }
  .ob-pill.up { background: var(--green-bg); color: var(--green); padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; }
  .ob-muted { color: var(--muted); font-size: 12px; }
  .view-by-co { display: none; }
  .view-all.on, .view-by-co.on { display: block; }
  .view-all:not(.on) { display: none; }
</style>
"""


def _companies_for_json(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    if df is None or df.empty:
        return rows
    for _, row in df.iterrows():
        orders_raw = row.get("orders")
        orders: list[dict] = []
        if isinstance(orders_raw, list):
            for o in orders_raw:
                if isinstance(o, dict):
                    orders.append(json_safe_obj(o))
        ttm_inr = row.get("ttm_revenue_inr")
        ttm_cr = inr_to_cr(ttm_inr) if ttm_inr is not None else None
        item = {
            "ticker": safe_str(row.get("ticker")),
            "name": safe_str(row.get("name")),
            "order_count": json_safe_scalar(row.get("order_count")),
            "total_cr": json_safe_scalar(row.get("total_cr")),
            "current_fy": safe_str(row.get("current_fy")) or None,
            "current_fy_cr": json_safe_scalar(row.get("current_fy_cr")),
            "growth_pct": json_safe_scalar(row.get("growth_pct")),
            "company_revenue_cr": ttm_cr,
            "orders": orders,
        }
        rows.append(json_safe_obj(item))
    return rows


def flatten_orders(companies: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for co in companies:
        name = co.get("name") or co.get("ticker")
        ticker = co.get("ticker")
        rev_cr = co.get("company_revenue_cr")
        for o in co.get("orders") or []:
            annual_cr = o.get("annual_value_cr") or o.get("value_cr")
            order_size_pct = o.get("revenue_pct")
            if order_size_pct is None and rev_cr and annual_cr:
                try:
                    order_size_pct = round(float(annual_cr) / float(rev_cr) * 100, 1)
                except (TypeError, ValueError, ZeroDivisionError):
                    order_size_pct = None
            flat.append(
                json_safe_obj(
                    {
                        "ticker": ticker,
                        "company": name,
                        "customer": o.get("customer") or "Not mentioned",
                        "order_type": o.get("order_type") or "—",
                        "announced_at": o.get("announced_at"),
                        "value_cr": o.get("value_cr"),
                        "duration_months": o.get("duration_months"),
                        "annual_value_cr": annual_cr,
                        "order_size_pct": order_size_pct,
                        "company_revenue_cr": rev_cr,
                        "pdf_url": o.get("pdf_url"),
                    }
                )
            )
    flat.sort(key=lambda r: str(r.get("announced_at") or ""), reverse=True)
    return flat


def build_order_book_html(
    df: pd.DataFrame,
    *,
    title: str = "All Orders",
    standalone: bool = True,
    page_size: int = 50,
) -> str:
    companies = _companies_for_json(df)
    flat = flatten_orders(companies)
    companies_js = json_dumps(companies, separators=(",", ":"))
    flat_js = json_dumps(flat, separators=(",", ":"))
    title_esc = html.escape(title)
    body = f"""
<div class="ob-wrap">
  <h1 class="ob-title">{title_esc}</h1>
  <div class="ob-tabs">
    <button type="button" class="ob-tab on" id="tab-all">All Orders</button>
    <button type="button" class="ob-tab" id="tab-co">By Company</button>
  </div>

  <div id="view-all" class="view-all on">
    <div class="ob-filters">
      <div class="ob-field">
        <label for="f-company">Company</label>
        <select id="f-company"><option value="">All companies</option></select>
      </div>
      <div class="ob-field">
        <label for="f-customer">Customer</label>
        <select id="f-customer"><option value="">All customers</option></select>
      </div>
      <div class="ob-slider-wrap">
        <label>Min Order Size: <span class="ob-slider-val" id="lbl-size">0%</span></label>
        <input type="range" class="ob-range" id="f-size" min="0" max="100" step="1" value="0" />
      </div>
      <div class="ob-slider-wrap">
        <label>Min Revenue: <span class="ob-slider-val" id="lbl-rev">0 Cr</span></label>
        <input type="range" class="ob-range" id="f-rev" min="0" max="500" step="1" value="0" />
      </div>
      <button type="button" class="ob-refresh" id="btn-refresh">↻ REFRESH</button>
    </div>
    <div class="ob-table-wrap">
      <table class="ob-main">
        <thead><tr id="ob-head"></tr></thead>
        <tbody id="ob-body"></tbody>
      </table>
    </div>
    <div class="ob-foot">
      <span>Rows per page: {page_size}</span>
      <span id="ob-page-label">1–0 of 0</span>
      <button type="button" id="ob-prev">Prev</button>
      <button type="button" id="ob-next">Next</button>
    </div>
  </div>

  <div id="view-co" class="view-by-co">
    <div class="ob-list" id="ob-co-list"></div>
    <div class="ob-foot" style="margin-top:8px;border-radius:10px;border-top:1px solid var(--border)">
      <span id="ob-co-count">0 companies</span>
    </div>
  </div>
</div>
<script>
const COMPANIES = {companies_js};
const ALL_ORDERS = {flat_js};
const PAGE_SIZE = {int(page_size)};

const COLS = [
  {{ id: "company", label: "Company" }},
  {{ id: "customer", label: "Customer" }},
  {{ id: "order_type", label: "Order Type" }},
  {{ id: "announced_at", label: "Date", sort: true }},
  {{ id: "value_cr", label: "Contract Value", num: true }},
  {{ id: "duration_months", label: "Duration" }},
  {{ id: "annual_value_cr", label: "Annual Value", num: true }},
  {{ id: "order_size_pct", label: "Order Size %", num: true }},
  {{ id: "company_revenue_cr", label: "Company Revenue", num: true }},
  {{ id: "pdf_url", label: "PDF" }},
];

let filtered = ALL_ORDERS.slice();
let page = 0;
let sortCol = "announced_at";
let sortDir = -1;
let openTicker = null;
let maxRevCr = 500;

function esc(s) {{
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
}}

function num(v) {{
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}}

function fmtCr(v) {{
  const n = num(v);
  if (n === null) return "—";
  return `<span class="ob-cr">₹${{n.toLocaleString("en-IN", {{ minimumFractionDigits: 1, maximumFractionDigits: 1 }})}} Cr</span>`;
}}

function fmtDate(v) {{
  if (!v) return "—";
  const p = String(v).split("-");
  if (p.length === 3) {{
    const d = new Date(parseInt(p[0],10), parseInt(p[1],10)-1, parseInt(p[2],10));
    return d.toLocaleDateString("en-GB", {{ day:"2-digit", month:"short", year:"numeric" }});
  }}
  return String(v);
}}

function fmtPct(v) {{
  const n = num(v);
  if (n === null) return "—";
  const cls = n >= 10 ? "hi" : "lo";
  return `<span class="ob-pct ${{cls}}">${{n.toFixed(1)}}%</span>`;
}}

function initFilters() {{
  const cos = [...new Set(ALL_ORDERS.map(r => r.company).filter(Boolean))].sort();
  const custs = [...new Set(ALL_ORDERS.map(r => r.customer).filter(Boolean))].sort();
  const coSel = document.getElementById("f-company");
  const cuSel = document.getElementById("f-customer");
  cos.forEach(c => {{
    const o = document.createElement("option");
    o.value = c; o.textContent = c;
    coSel.appendChild(o);
  }});
  custs.forEach(c => {{
    const o = document.createElement("option");
    o.value = c; o.textContent = c;
    cuSel.appendChild(o);
  }});
  const maxVal = Math.max(0, ...ALL_ORDERS.map(r => num(r.value_cr) || 0));
  maxRevCr = Math.max(50, Math.ceil(maxVal / 10) * 10);
  const revSlider = document.getElementById("f-rev");
  revSlider.max = String(maxRevCr);
}}

function applyFilters() {{
  const co = document.getElementById("f-company").value;
  const cu = document.getElementById("f-customer").value;
  const minSize = num(document.getElementById("f-size").value) || 0;
  const minRev = num(document.getElementById("f-rev").value) || 0;
  filtered = ALL_ORDERS.filter(r => {{
    if (co && r.company !== co) return false;
    if (cu && r.customer !== cu) return false;
    const vCr = num(r.value_cr) || 0;
    if (vCr < minRev) return false;
    const pct = num(r.order_size_pct);
    if (minSize > 0 && (pct === null || pct < minSize)) return false;
    return true;
  }});
  page = 0;
  sortRows();
  renderTable();
}}

function sortRows() {{
  const col = COLS.find(c => c.id === sortCol) || COLS[0];
  filtered.sort((a, b) => {{
    if (col.id === "announced_at") {{
      return String(a.announced_at || "").localeCompare(String(b.announced_at || "")) * sortDir;
    }}
    if (col.num) {{
      const av = num(a[col.id]); const bv = num(b[col.id]);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      return (av - bv) * sortDir;
    }}
    return String(a[col.id] || "").localeCompare(String(b[col.id] || "")) * sortDir;
  }});
}}

function renderHead() {{
  const tr = document.getElementById("ob-head");
  tr.innerHTML = "";
  COLS.forEach(c => {{
    const th = document.createElement("th");
    th.textContent = c.label;
    if (c.sort) {{
      th.className = "sortable" + (sortCol === c.id ? " sorted" : "");
      const icon = sortCol === c.id ? (sortDir < 0 ? "↓" : "↑") : "↕";
      th.innerHTML = esc(c.label) + `<span class="sort-icon">${{icon}}</span>`;
      th.onclick = () => {{
        if (sortCol === c.id) sortDir *= -1;
        else {{ sortCol = c.id; sortDir = -1; }}
        sortRows();
        renderHead();
        renderTable();
      }};
    }}
    tr.appendChild(th);
  }});
}}

function cell(col, r) {{
  switch (col.id) {{
    case "company": return `<span class="ob-co">${{esc(r.company)}}</span>`;
    case "customer": return esc(r.customer);
    case "order_type": return esc(r.order_type);
    case "announced_at": return fmtDate(r.announced_at);
    case "value_cr": return fmtCr(r.value_cr);
    case "duration_months":
      return r.duration_months != null ? r.duration_months + " months" : "—";
    case "annual_value_cr": return fmtCr(r.annual_value_cr);
    case "order_size_pct": return fmtPct(r.order_size_pct);
    case "company_revenue_cr": return fmtCr(r.company_revenue_cr);
    case "pdf_url":
      return r.pdf_url
        ? `<span class="ob-pdf"><a href="${{esc(r.pdf_url)}}" target="_blank" rel="noopener noreferrer">PDF</a></span>`
        : "—";
    default: return esc(r[col.id]);
  }}
}}

function renderTable() {{
  const tb = document.getElementById("ob-body");
  tb.innerHTML = "";
  const start = page * PAGE_SIZE;
  const slice = filtered.slice(start, start + PAGE_SIZE);
  if (!slice.length) {{
    tb.innerHTML = `<tr><td colspan="${{COLS.length}}" class="ob-empty">No orders match filters.</td></tr>`;
  }} else {{
    slice.forEach(r => {{
      const tr = document.createElement("tr");
      COLS.forEach(c => {{
        const td = document.createElement("td");
        td.innerHTML = cell(c, r);
        tr.appendChild(td);
      }});
      tb.appendChild(tr);
    }});
  }}
  const total = filtered.length;
  const end = Math.min(start + PAGE_SIZE, total);
  document.getElementById("ob-page-label").textContent =
    total ? `${{start + 1}}–${{end}} of ${{total}}` : "0 of 0";
  document.getElementById("ob-prev").disabled = page <= 0;
  document.getElementById("ob-next").disabled = start + PAGE_SIZE >= total;
}}

function renderByCompany() {{
  const list = document.getElementById("ob-co-list");
  list.innerHTML = "";
  COMPANIES.forEach(r => {{
    const growth = r.growth_pct != null ? Number(r.growth_pct).toFixed(2) + "%" : "—";
    const isOpen = openTicker === r.ticker;
    const div = document.createElement("div");
    div.className = "ob-row" + (isOpen ? " open" : "");
    div.innerHTML =
      `<div class="ob-summary">` +
      `<span class="ob-chev"></span>` +
      `<span class="ob-co">${{esc(r.name || r.ticker)}}</span>` +
      `<span class="ob-pill up">${{growth}}</span>` +
      `<span class="ob-muted">${{r.order_count || 0}} orders</span>` +
      `<span class="ob-cr">${{fmtCr(r.total_cr).replace(/<[^>]+>/g,"")}}</span>` +
      `<span class="ob-muted">${{fmtCr(r.current_fy_cr).replace(/<[^>]+>/g,"")}} (${{esc(r.current_fy || "")}})</span>` +
      `</div>` +
      `<div class="ob-detail"><table class="ob-main"><thead><tr>` +
      COLS.map(c => `<th>${{esc(c.label)}}</th>`).join("") +
      `</tr></thead><tbody>` +
      (r.orders || []).map(o => {{
        const row = {{
          company: r.name, customer: o.customer || "Not mentioned", order_type: o.order_type,
          announced_at: o.announced_at, value_cr: o.value_cr, duration_months: o.duration_months,
          annual_value_cr: o.annual_value_cr || o.value_cr, order_size_pct: o.revenue_pct,
          company_revenue_cr: r.company_revenue_cr, pdf_url: o.pdf_url
        }};
        return "<tr>" + COLS.map(c => `<td>${{cell(c, row)}}</td>`).join("") + "</tr>";
      }}).join("") +
      `</tbody></table></div>`;
    div.querySelector(".ob-summary").onclick = () => {{
      openTicker = openTicker === r.ticker ? null : r.ticker;
      renderByCompany();
    }};
    list.appendChild(div);
  }});
  document.getElementById("ob-co-count").textContent = COMPANIES.length + " companies";
}}

document.getElementById("tab-all").onclick = () => {{
  document.getElementById("tab-all").classList.add("on");
  document.getElementById("tab-co").classList.remove("on");
  document.getElementById("view-all").classList.add("on");
  document.getElementById("view-co").classList.remove("on");
}};
document.getElementById("tab-co").onclick = () => {{
  document.getElementById("tab-co").classList.add("on");
  document.getElementById("tab-all").classList.remove("on");
  document.getElementById("view-co").classList.add("on");
  document.getElementById("view-all").classList.remove("on");
  renderByCompany();
}};

document.getElementById("f-size").oninput = (e) => {{
  document.getElementById("lbl-size").textContent = e.target.value + "%";
  applyFilters();
}};
document.getElementById("f-rev").oninput = (e) => {{
  document.getElementById("lbl-rev").textContent = e.target.value + " Cr";
  applyFilters();
}};
document.getElementById("f-company").onchange = applyFilters;
document.getElementById("f-customer").onchange = applyFilters;
document.getElementById("btn-refresh").onclick = () => {{
  document.getElementById("f-company").value = "";
  document.getElementById("f-customer").value = "";
  document.getElementById("f-size").value = "0";
  document.getElementById("f-rev").value = "0";
  document.getElementById("lbl-size").textContent = "0%";
  document.getElementById("lbl-rev").textContent = "0 Cr";
  applyFilters();
}};
document.getElementById("ob-prev").onclick = () => {{ if (page > 0) {{ page--; renderTable(); }} }};
document.getElementById("ob-next").onclick = () => {{
  if ((page + 1) * PAGE_SIZE < filtered.length) {{ page++; renderTable(); }}
}};

initFilters();
renderHead();
applyFilters();
</script>
"""
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{title_esc}</title>'
            f"{_ORDER_BOOK_CSS}</head><body>{body}</body></html>"
        )
    return f"{_ORDER_BOOK_CSS}{body}"


def order_book_iframe_height(row_count: int, *, expanded: bool = False) -> int:
    del expanded
    # Flat all-orders view needs more vertical space for filter bar + table.
    return min(2600, max(560, 200 + min(row_count, 50) * 36))

def flat_order_count(df: pd.DataFrame) -> int:
    companies = _companies_for_json(df)
    return len(flatten_orders(companies))
