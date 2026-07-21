"""Click-to-expand strategy tables with snapshot sidebar + quarterly panel."""

from __future__ import annotations

import html
import json

import pandas as pd

from stocks.dashboards.expand_panel_html import EXPAND_PANEL_CSS, EXPAND_PANEL_JS
from stocks.dashboards.report_html import _REPORT_CSS
from stocks.shared.corp_tags import corp_tags_dict_for_ticker
from stocks.shared.links import attach_research_links, screener_url, tradingview_url
from stocks.shared.stock_notes import attach_stock_notes, sync_stock_notes_from_file
from stocks.market.google_news import attach_google_news_to_rows
from stocks.core.text_utils import safe_str


def rows_for_json(df: pd.DataFrame, *, extra_cols: tuple[str, ...] = ()) -> list[dict]:
    if df.empty:
        return []
    sync_stock_notes_from_file()
    work = attach_stock_notes(
        attach_research_links(df) if "tv_link" not in df.columns else df.copy(),
        sync_file=False,
    )
    rows: list[dict] = []
    base_cols = (
        "price", "rsi", "supertrend", "adx", "di_plus", "di_minus",
        "long_term_rs", "short_term_rs", "crossover_type", "crossover_score",
        "score", "date", "upper_band", "signal", "timeframe",
        "tq_w52", "tq_w52_prev", "tq_change", "tq_zone", "recovery_score",
        "industry", "sub_sector", "market_cap_cr", "pe_ratio", "forward_pe",
        "growth_score", "growth_checks", "sales_cagr", "profit_cagr",
        "sales_growth", "operating_margin", "gross_margin", "net_margin",
        "roe", "roa", "debt_to_equity",
        "cq_score", "cq_checks", "cash_to_tax", "croic", "ccc_years", "ccc_days",
        "ocf_ebitda_growth", "ocf_to_ebitda", "ocf_cagr", "ebitda_cagr",
    ) + extra_cols
    for _, row in work.iterrows():
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        item = {
            "ticker": ticker,
            "name": safe_str(row.get("name")),
            "market": market,
            "sector": safe_str(row.get("sector")),
            **corp_tags_dict_for_ticker(ticker),
            "sc": row.get("screener_link") or screener_url(ticker, market),
            "tv": row.get("tv_link") or tradingview_url(ticker, market),
        }
        for col in base_cols:
            if col in row.index and row.get(col) is not None:
                val = row.get(col)
                if isinstance(val, float) and pd.isna(val):
                    continue
                item[col] = val
        snapshot = row.get("snapshot")
        if isinstance(snapshot, dict) and snapshot.get("price") is not None:
            item["snapshot"] = snapshot
        quarters = row.get("quarters")
        if isinstance(quarters, dict) and quarters.get("labels"):
            item["quarters"] = quarters
        note = row.get("stock_note")
        if isinstance(note, dict) and (
            note.get("business") or note.get("market_position") or note.get("triggers")
        ):
            item["stock_note"] = {
                "business": safe_str(note.get("business")) or None,
                "market_position": safe_str(note.get("market_position")) or None,
                "triggers": list(note.get("triggers") or []),
                "source": safe_str(note.get("source")) or None,
            }
        rows.append(item)
    return attach_google_news_to_rows(rows)


def build_interactive_section(
    section_id: str,
    title: str,
    df: pd.DataFrame,
    cols_json: list[dict],
    *,
    kind: str,
    open_section: bool = False,
    expand_hint: str = "Click row for Google News",
) -> str:
    del kind
    data_json = json.dumps(rows_for_json(df), separators=(",", ":"))
    cols_str = json.dumps(cols_json, separators=(",", ":"))
    open_attr = " open" if open_section else ""
    hint = html.escape(expand_hint)
    return f"""
<details class="fund-section"{open_attr} id="{section_id}-wrap">
  <summary>
    <span>{html.escape(title)}</span>
    <span class="fund-section-meta">{len(df)} signals</span>
  </summary>
  <div class="fund-section-body">
    <div class="table-wrap">
      <table class="report strat-table">
        <thead><tr id="{section_id}-head"></tr></thead>
        <tbody id="{section_id}-body"></tbody>
      </table>
    </div>
  </div>
</details>
<script>
(function() {{
  const SECTION = {json.dumps(section_id)};
  const DATA = {data_json};
  const COLS = {cols_str};
  let expanded = null;
  {EXPAND_PANEL_JS}
  function esc(s) {{
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  }}
  function fmtCompany(r) {{
    const name = r.name || r.ticker;
    const tags = fmtCorpTags(r);
    return (
      `<div class="company-cell">` +
      `<div class="company-top">` +
      `<span class="company-name" title="${{esc(name)}}">${{esc(name)}}</span>` +
      `<span class="company-actions">` +
      `<span class="expand-hint" title="{hint}"></span>` +
      `<span class="links-inline">` +
      `<a href="${{r.sc}}" target="_blank" rel="noopener noreferrer">SC</a>` +
      `<a href="${{r.tv}}" target="_blank" rel="noopener noreferrer">TV</a>` +
      `</span></span></div>` +
      `<div class="sub">${{esc(r.ticker)}}</div>` +
      (tags ? `<div class="company-tags-row">${{tags}}</div>` : "") +
      `</div>`
    );
  }}
  function fmtCell(c, r) {{
    const v = r[c.id];
    switch (c.fmt) {{
      case "company": return fmtCompany(r);
      case "text": return v != null ? esc(v) : "—";
      case "date": return v ? esc(String(v).slice(0, 10)) : "—";
      case "score":
        if (v == null || isNaN(v)) return "—";
        return `<span class="badge-score">${{Number(v).toFixed(1)}}</span>`;
      case "int":
        if (v == null || isNaN(v)) return "—";
        return `<span class="badge-score">${{Number(v).toFixed(0)}}</span>`;
      case "num1": return v != null && !isNaN(v) ? Number(v).toFixed(1) : "—";
      case "num2": return v != null && !isNaN(v) ? Number(v).toFixed(2) : "—";
      case "num4": return v != null && !isNaN(v) ? Number(v).toFixed(4) : "—";
      default: return v != null ? esc(v) : "—";
    }}
  }}
  function render() {{
    const tb = document.getElementById(SECTION + "-body");
    const th = document.getElementById(SECTION + "-head");
    if (!tb || !th) return;
    th.innerHTML = COLS.map(c => `<th>${{c.label}}</th>`).join("");
    tb.innerHTML = "";
    DATA.forEach((r, idx) => {{
      const open = expanded === r.ticker;
      const tr = document.createElement("tr");
      tr.className = "strat-row" + (open ? " expanded" : "") + (idx < 3 ? " top3" : "");
      tr.onclick = (e) => {{
        if (e.target.closest("a")) return;
        expanded = expanded === r.ticker ? null : r.ticker;
        render();
      }};
      COLS.forEach(c => {{
        const td = document.createElement("td");
        if (c.id === "company") td.className = "company-td";
        td.innerHTML = fmtCell(c, r);
        tr.appendChild(td);
      }});
      tb.appendChild(tr);
      if (open) {{
        const tr2 = document.createElement("tr");
        tr2.className = "strat-expand";
        const td = document.createElement("td");
        td.colSpan = COLS.length;
        td.innerHTML = renderExpandPanelNews(r);
        tr2.appendChild(td);
        tb.appendChild(tr2);
      }}
    }});
  }}
  render();
}})();
</script>
"""


def wrap_interactive_page(
    *,
    title: str = "",
    sections_html: str,
    standalone: bool = True,
    **_: object,
) -> str:
    """Minimal report shell — tables only, no subtitle/footer/hint lines."""
    title_html = (
        f'<h1 class="fund-title">{html.escape(title)}</h1>' if title.strip() else ""
    )
    extra_css = f"<style>{EXPAND_PANEL_CSS}</style>"
    body = (
        f'<div class="fund-page">'
        f"{title_html}"
        f'<div class="fund-sections">{sections_html}</div>'
        f"</div>"
    )
    if standalone:
        return (
            "<!DOCTYPE html><html><head>"
            f'<meta charset="utf-8"><title>{html.escape(title or "Report")}</title>'
            f"{_REPORT_CSS}{extra_css}</head><body>{body}</body></html>"
        )
    return f"{_REPORT_CSS}{extra_css}{body}"
