"""Click-to-expand strategy tables with quarterly panel, snapshot, and research links."""

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
from stocks.core.json_utils import json_dumps, json_safe_obj, json_safe_scalar
from stocks.core.text_utils import safe_str
from stocks.strategies.pead2.quarters import sanitize_quarter_panel
from stocks.strategies.pead2.expand_data import apply_scan_price_to_payload


def _load_expand_metric_maps(
    df: pd.DataFrame,
) -> tuple[dict[str, float], dict[str, dict], dict[str, dict]]:
    """Mcap, cached metrics, and PEAD2 expand payload from SQLite."""
    from stocks.core.config import PEAD2_CACHE_HOURS
    from stocks.core.database import load_market_cap_from_db, load_metrics_from_db, load_pead2_cache
    from stocks.strategies.pead2.expand_data import expand_from_lag_row
    from stocks.strategies.pead2.service import _normalize_cache_blob

    mcap_map: dict[str, float] = {}
    metrics_map: dict[str, dict] = {}
    pead_map: dict[str, dict] = {}
    if df.empty or "ticker" not in df.columns:
        return mcap_map, metrics_map, pead_map

    tickers = df["ticker"].astype(str).str.strip().str.upper().unique().tolist()
    mcap_df = load_market_cap_from_db(tickers)
    if not mcap_df.empty:
        mcap_map = {
            safe_str(t).upper(): float(v)
            for t, v in zip(mcap_df["ticker"], mcap_df["market_cap_cr"], strict=False)
            if safe_str(t) and v is not None and not pd.isna(v)
        }
    metrics_df = load_metrics_from_db(tickers)
    if not metrics_df.empty:
        for _, mrow in metrics_df.iterrows():
            key = safe_str(mrow.get("ticker")).upper()
            if key:
                metrics_map[key] = mrow.to_dict()
    cache_map = load_pead2_cache(tickers, max_hours=PEAD2_CACHE_HOURS)
    for ticker, blob in cache_map.items():
        norm = _normalize_cache_blob(blob)
        lag0 = (norm.get("lags") or {}).get("0")
        payload = expand_from_lag_row(lag0 if isinstance(lag0, dict) else None)
        if payload:
            pead_map[safe_str(ticker).upper()] = payload
    return mcap_map, metrics_map, pead_map


def _resolve_row_mcap(
    row: pd.Series,
    *,
    mcap_map: dict[str, float],
    metrics_map: dict[str, dict],
    pead_map: dict[str, dict],
) -> float | None:
    ticker = safe_str(row.get("ticker")).upper()
    row_mcap = row.get("market_cap_cr")
    if row_mcap is not None and not pd.isna(row_mcap):
        return float(row_mcap)
    if ticker and ticker in mcap_map:
        return mcap_map[ticker]
    metrics = metrics_map.get(ticker) or {}
    cached = metrics.get("market_cap_cr")
    if cached is not None and not pd.isna(cached):
        return float(cached)
    pead_snap = (pead_map.get(ticker) or {}).get("snapshot")
    if isinstance(pead_snap, dict):
        snap_mcap = pead_snap.get("market_cap_cr")
        if snap_mcap is not None and not pd.isna(snap_mcap):
            return float(snap_mcap)
    snap = row.get("snapshot")
    if isinstance(snap, dict):
        snap_mcap = snap.get("market_cap_cr")
        if snap_mcap is not None and not pd.isna(snap_mcap):
            return float(snap_mcap)
    return None


def _resolve_row_pe(
    row: pd.Series,
    *,
    metrics_map: dict[str, dict],
    pead_map: dict[str, dict],
) -> float | None:
    ticker = safe_str(row.get("ticker")).upper()
    row_pe = row.get("pe_ratio")
    if row_pe is not None and not pd.isna(row_pe):
        return float(row_pe)
    pead_pe = (pead_map.get(ticker) or {}).get("pe_ratio")
    if pead_pe is not None and not pd.isna(pead_pe):
        return float(pead_pe)
    metrics = metrics_map.get(ticker) or {}
    cached = metrics.get("pe")
    if cached is not None and not pd.isna(cached):
        return float(cached)
    snap = row.get("snapshot")
    if isinstance(snap, dict):
        for key in ("pe_ratio", "pe"):
            val = snap.get(key)
            if val is not None and not pd.isna(val):
                return float(val)
    pead_snap = (pead_map.get(ticker) or {}).get("snapshot")
    if isinstance(pead_snap, dict):
        for key in ("pe_ratio", "pe"):
            val = pead_snap.get(key)
            if val is not None and not pd.isna(val):
                return float(val)
    return None


def _resolve_row_cagr(row: pd.Series, *, pead_map: dict[str, dict]) -> float | None:
    ticker = safe_str(row.get("ticker")).upper()
    snap = row.get("snapshot")
    if isinstance(snap, dict):
        val = snap.get("cagr")
        if val is not None and not pd.isna(val):
            return float(val)
    pead_snap = (pead_map.get(ticker) or {}).get("snapshot")
    if isinstance(pead_snap, dict):
        val = pead_snap.get("cagr")
        if val is not None and not pd.isna(val):
            return float(val)
    for col in ("sales_cagr", "profit_cagr", "ocf_cagr", "ebitda_cagr"):
        val = row.get(col)
        if val is not None and not pd.isna(val):
            return float(val)
    return None


def _attach_snapshot_to_item(
    item: dict,
    row: pd.Series,
    *,
    row_mcap: float | None,
    row_pe: float | None,
    row_cagr: float | None,
    metrics_map: dict[str, dict],
    pead_map: dict[str, dict],
) -> None:
    snapshot = row.get("snapshot")
    row_price = json_safe_scalar(row.get("price"))
    snap_price = json_safe_scalar(snapshot.get("price") if isinstance(snapshot, dict) else None)
    price = row_price if row_price is not None else snap_price
    metrics = metrics_map.get(safe_str(row.get("ticker")).upper()) or {}
    pead_payload = pead_map.get(safe_str(row.get("ticker")).upper()) or {}
    pead_snap = pead_payload.get("snapshot") if isinstance(pead_payload.get("snapshot"), dict) else {}

    if isinstance(snapshot, dict) and snap_price is not None:
        snap = dict(snapshot)
    elif isinstance(pead_snap, dict) and pead_snap.get("price") is not None:
        snap = dict(pead_snap)
        if price is not None:
            snap["price"] = price
    else:
        snap = None

    if snap is not None:
        if row_price is not None:
            synced = apply_scan_price_to_payload(
                {
                    "snapshot": snap,
                    "pe_ratio": row_pe if row_pe is not None else row.get("pe_ratio"),
                    "forward_pe": row.get("forward_pe"),
                },
                row_price,
            )
            if synced:
                snap = synced.get("snapshot") or snap
                if row_pe is None and synced.get("pe_ratio") is not None:
                    row_pe = float(synced["pe_ratio"])
        if row_mcap is not None and snap.get("market_cap_cr") is None:
            snap["market_cap_cr"] = round(row_mcap, 1)
        if row_pe is not None:
            if snap.get("pe_ratio") is None:
                snap["pe_ratio"] = round(row_pe, 1)
            if snap.get("pe") is None:
                snap["pe"] = snap["pe_ratio"]
        if row_cagr is not None and snap.get("cagr") is None:
            snap["cagr"] = round(row_cagr, 2)
        if snap.get("forward_pe") is None:
            fwd = row.get("forward_pe")
            if fwd is None or pd.isna(fwd):
                fwd = pead_payload.get("forward_pe")
            if fwd is not None and not pd.isna(fwd):
                snap["forward_pe"] = round(float(fwd), 1)
        if snap.get("w52_low") is None:
            lo = metrics.get("52w_low")
            if lo is None and pead_snap:
                lo = pead_snap.get("w52_low")
            if lo is not None and not pd.isna(lo):
                snap["w52_low"] = round(float(lo), 2)
        if snap.get("w52_high") is None:
            hi = metrics.get("52w_high")
            if hi is None and pead_snap:
                hi = pead_snap.get("w52_high")
            if hi is not None and not pd.isna(hi):
                snap["w52_high"] = round(float(hi), 2)
        if not snap.get("moving_averages") and pead_snap.get("moving_averages"):
            snap["moving_averages"] = pead_snap["moving_averages"]
        item["snapshot"] = json_safe_obj(snap)
        if snap.get("long_description"):
            item["long_description"] = snap["long_description"]
        return

    if price is None:
        return

    item["snapshot"] = json_safe_obj(
        {
            "price": price,
            "market_cap_cr": round(row_mcap, 1) if row_mcap is not None else None,
            "pe": round(row_pe, 1) if row_pe is not None else None,
            "pe_ratio": round(row_pe, 1) if row_pe is not None else None,
            "forward_pe": json_safe_scalar(row.get("forward_pe") or pead_payload.get("forward_pe")),
            "cagr": round(row_cagr, 2) if row_cagr is not None else None,
            "w52_low": round(float(metrics["52w_low"]), 2)
            if metrics.get("52w_low") is not None and not pd.isna(metrics.get("52w_low"))
            else round(float(pead_snap["w52_low"]), 2)
            if pead_snap.get("w52_low") is not None and not pd.isna(pead_snap.get("w52_low"))
            else None,
            "w52_high": round(float(metrics["52w_high"]), 2)
            if metrics.get("52w_high") is not None and not pd.isna(metrics.get("52w_high"))
            else round(float(pead_snap["w52_high"]), 2)
            if pead_snap.get("w52_high") is not None and not pd.isna(pead_snap.get("w52_high"))
            else None,
            "moving_averages": pead_snap.get("moving_averages") or [],
        }
    )


def _has_quarter_panel(val: object) -> bool:
    return (
        isinstance(val, dict)
        and bool(val.get("labels"))
        and bool(val.get("rows"))
    )


def rows_for_json(df: pd.DataFrame, *, extra_cols: tuple[str, ...] = ()) -> list[dict]:
    if df.empty:
        return []
    sync_stock_notes_from_file()
    work = attach_stock_notes(
        attach_research_links(df) if "tv_link" not in df.columns else df.copy(),
        sync_file=False,
    )
    mcap_map, metrics_map, pead_map = _load_expand_metric_maps(work)
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
        "rank", "website",
        "mv_score", "price_to_sales", "sales_growth", "debt_to_equity",
        "ie_gates", "institutional_pct_delta", "institutional_pct_now",
        "first_time_entry", "quarter_end", "avg_volume", "years_listed", "sales_cagr",
        "ah_ingredients", "ah_n_pass", "phase", "ev_ebitda", "drawdown_pct",
        "promoter_pct_delta", "demerger_flag",
        "fair_price", "upside_pct", "implied_growth", "verdict",
        "base_fcf", "equity_value", "pv_forecast", "pv_terminal",
        "discount_rate", "terminal_growth", "growth",
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
        snapshot = row.get("snapshot")
        web = safe_str(row.get("website"))
        if not web and isinstance(snapshot, dict):
            web = safe_str(snapshot.get("website"))
        if web:
            item["website"] = web
        row_mcap = _resolve_row_mcap(
            row, mcap_map=mcap_map, metrics_map=metrics_map, pead_map=pead_map
        )
        row_pe = _resolve_row_pe(row, metrics_map=metrics_map, pead_map=pead_map)
        row_cagr = _resolve_row_cagr(row, pead_map=pead_map)
        if row_mcap is not None:
            item["market_cap_cr"] = round(row_mcap, 1)
        if row_pe is not None:
            item["pe_ratio"] = round(row_pe, 1)
        if row_cagr is not None:
            item["sales_cagr"] = round(row_cagr, 2)
        for col in base_cols:
            if col in row.index and row.get(col) is not None:
                val = row.get(col)
                if isinstance(val, float) and pd.isna(val):
                    continue
                item[col] = json_safe_scalar(val)
        _attach_snapshot_to_item(
            item,
            row,
            row_mcap=row_mcap,
            row_pe=row_pe,
            row_cagr=row_cagr,
            metrics_map=metrics_map,
            pead_map=pead_map,
        )
        quarters = row.get("quarters")
        if not _has_quarter_panel(quarters):
            pead_q = (pead_map.get(safe_str(ticker).upper()) or {}).get("quarters")
            if _has_quarter_panel(pead_q):
                quarters = pead_q
        if _has_quarter_panel(quarters):
            item["quarters"] = sanitize_quarter_panel(json_safe_obj(quarters))
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
        rows.append(json_safe_obj(item))
    return attach_google_news_to_rows(rows)


def prepare_interactive_report_df(
    df: pd.DataFrame,
    *,
    max_workers: int | None = None,
) -> pd.DataFrame:
    """PEAD-style expand payload: PEAD2 cache + throttled Yahoo fetch."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    from stocks.strategies.pead2.expand_data import attach_pead_expand

    workers = min(int(max_workers or 8), 8)
    out = attach_pead_expand(df, max_workers=workers)
    out = attach_research_links(out)
    if "website" not in out.columns:
        out["website"] = None
    for idx in out.index:
        if safe_str(out.at[idx, "website"]):
            continue
        snap = out.at[idx, "snapshot"]
        if isinstance(snap, dict):
            web = safe_str(snap.get("website"))
            if web:
                out.at[idx, "website"] = web
    return out


def build_interactive_section(
    section_id: str,
    title: str,
    df: pd.DataFrame,
    cols_json: list[dict],
    *,
    kind: str,
    open_section: bool = False,
    expand_hint: str = "Click row — same detail as PEAD (quarterly, links, news)",
) -> str:
    del kind
    data_json = json_dumps(rows_for_json(df), separators=(",", ":"))
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
    let web = r.website || "";
    if (web && !/^https?:\\/\\//i.test(web)) web = "https://" + web;
    const webLink = web
      ? `<a href="${{esc(web)}}" target="_blank" rel="noopener noreferrer" title="Company website">Web</a>`
      : "";
    return (
      `<div class="company-cell">` +
      `<div class="company-top">` +
      `<span class="company-name" title="${{esc(name)}}">${{esc(name)}}</span>` +
      `<span class="company-actions">` +
      `<span class="expand-hint" title="{hint}"></span>` +
      `<span class="links-inline">` +
      `<a href="${{r.sc}}" target="_blank" rel="noopener noreferrer">SC</a>` +
      `<a href="${{r.tv}}" target="_blank" rel="noopener noreferrer">TV</a>` +
      webLink +
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
        td.innerHTML = renderPeadExpandPanel(r);
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
