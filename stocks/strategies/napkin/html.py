"""Napkin report HTML — Watching / PEAD-style board with SC · TV · Web."""

from __future__ import annotations

import html
from typing import Optional

import pandas as pd

from stocks.core.text_utils import safe_str, sanitize_website
from stocks.dashboards.iframe_helpers import embed_html_iframe
from stocks.shared.links import research_links


_NAPKIN_CSS = """
<style>
  .nk-wrap {
    font-family: "IBM Plex Sans", "Segoe UI", ui-sans-serif, system-ui, sans-serif;
    color: #1f2937;
    padding: 0 2px 8px;
  }
  .nk-meta {
    display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center;
    margin: 0 0 10px; font-size: 12px; color: #64748b;
  }
  .nk-chip {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700;
    border: 1px solid #e2e8f0; background: #f8fafc; color: #475569;
    cursor: pointer; user-select: none;
  }
  .nk-chip.active { background: #0f172a; color: #fff; border-color: #0f172a; }
  .nk-chip.buy { background: #ecfdf5; border-color: #bbf7d0; color: #15803d; }
  .nk-chip.buy.active { background: #15803d; color: #fff; border-color: #15803d; }
  .nk-chip.fair { background: #f1f5f9; color: #475569; }
  .nk-chip.over { background: #fef2f2; border-color: #fecaca; color: #b91c1c; }
  .nk-chip.miss { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
  .nk-search {
    flex: 1 1 160px; min-width: 140px; max-width: 280px;
    border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px 10px;
    font-size: 12px; outline: none;
  }
  .nk-search:focus { border-color: #94a3b8; }
  table.nk {
    width: 100%; border-collapse: collapse; background: #fff; table-layout: fixed;
  }
  table.nk th {
    text-align: left; font-size: 10px; font-weight: 700; letter-spacing: .04em;
    text-transform: uppercase; color: #64748b; background: #f8fafc;
    padding: 7px 8px; border-bottom: 1px solid #e2e8f0; white-space: nowrap;
  }
  table.nk th.num, table.nk td.num { text-align: right; font-variant-numeric: tabular-nums; }
  table.nk td {
    padding: 8px; border-bottom: 1px solid #f1f5f9; vertical-align: middle;
    font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  table.nk tbody tr:hover td { background: #f8fafc; }
  table.nk tr.buy td { background: #f0fdf4; }
  table.nk tr.buy:hover td { background: #dcfce7; }
  .nk-ticker { font-weight: 800; color: #0f172a; letter-spacing: -0.02em; }
  .nk-name { color: #64748b; font-size: 11px; }
  .nk-verdict {
    display: inline-block; padding: 2px 7px; border-radius: 999px;
    font-size: 10px; font-weight: 700; border: 1px solid transparent;
  }
  .nk-verdict.buy { background: #dcfce7; color: #166534; border-color: #bbf7d0; }
  .nk-verdict.fair { background: #f1f5f9; color: #475569; border-color: #e2e8f0; }
  .nk-verdict.over { background: #fee2e2; color: #991b1b; border-color: #fecaca; }
  .nk-verdict.miss { background: #ffedd5; color: #9a3412; border-color: #fed7aa; }
  .nk-verdict.unprof { background: #f1f5f9; color: #94a3b8; border-color: #e2e8f0; }
  .nk-score.pos { color: #15803d; font-weight: 800; }
  .nk-score.neg { color: #b91c1c; font-weight: 700; }
  .nk-links { display: flex; gap: 4px; flex-wrap: wrap; }
  .nk-links a {
    display: inline-block; padding: 1px 6px; border-radius: 5px;
    font-size: 10px; font-weight: 700; text-decoration: none; border: 1px solid #e2e8f0;
    background: #f1f5f9; color: #334155;
  }
  .nk-links a.sc { background: #f0fdf4; border-color: #bbf7d0; color: #15803d; }
  .nk-links a.tv { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
  .nk-links a.web { background: #ecfeff; border-color: #a5f3fc; color: #0e7490; }
  .nk-empty { padding: 18px; color: #94a3b8; font-size: 13px; }
</style>
"""


def _esc(val) -> str:
    return html.escape(safe_str(val))


def _pct(val) -> str:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "—"
        return f"{float(val):.1%}"
    except (TypeError, ValueError):
        return "—"


def _pe(val) -> str:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "—"
        return f"{float(val):.1f}"
    except (TypeError, ValueError):
        return "—"


def _score(val) -> str:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return "—"
        v = float(val)
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.1%}"
    except (TypeError, ValueError):
        return "—"


def _verdict_class(verdict: str) -> str:
    v = safe_str(verdict)
    if v == "Napkin Buy":
        return "buy"
    if v == "Fair Value":
        return "fair"
    if v == "Overvalued":
        return "over"
    if v == "Insufficient Data":
        return "miss"
    return "unprof"


def enrich_napkin_display(df: pd.DataFrame, universe: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Attach market, website, SC/TV links for the HTML board."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    out = df.copy()
    out["ticker"] = out["ticker"].astype(str).str.strip().str.upper()

    uni_map: dict[str, dict] = {}
    if universe is not None and not universe.empty and "ticker" in universe.columns:
        for _, r in universe.iterrows():
            t = safe_str(r.get("ticker")).upper()
            if t:
                uni_map[t] = r.to_dict()

    tickers = out["ticker"].tolist()
    websites: dict[str, str] = {}
    try:
        from stocks.core.database import load_company_profiles_from_db

        profiles = load_company_profiles_from_db(tickers)
        for t, p in profiles.items():
            w = sanitize_website(p.get("website"))
            if w:
                websites[t] = w
    except Exception:
        pass

    sc_list: list[str] = []
    tv_list: list[str] = []
    web_list: list[str] = []
    market_list: list[str] = []
    name_list: list[str] = []
    sector_list: list[str] = []
    note_list: list[str] = []

    for _, row in out.iterrows():
        t = safe_str(row.get("ticker")).upper()
        meta = uni_map.get(t, {})
        market = safe_str(row.get("market") or meta.get("market")) or None
        name = safe_str(row.get("name") or meta.get("name") or t)
        sector = safe_str(row.get("sector") or meta.get("sector") or meta.get("industry"))
        website = websites.get(t) or sanitize_website(meta.get("website"))
        sc, tv = research_links(t, market)
        sc_list.append(sc)
        tv_list.append(tv)
        web_list.append(website or "")
        market_list.append(market or "")
        name_list.append(name)
        sector_list.append(sector)
        # Missing-data note
        bits = []
        if safe_str(row.get("verdict")) in {"Unprofitable", "Insufficient Data"}:
            if row.get("pe") is None or (isinstance(row.get("pe"), float) and pd.isna(row.get("pe"))):
                bits.append("no PE")
            if row.get("expected_cagr") is None or (
                isinstance(row.get("expected_cagr"), float) and pd.isna(row.get("expected_cagr"))
            ):
                bits.append("no growth")
            src = safe_str(row.get("pe_source"))
            if src:
                bits.append(src)
        note_list.append(", ".join(bits))

    out["name"] = name_list
    out["sector"] = sector_list
    out["market"] = market_list
    out["sc"] = sc_list
    out["tv"] = tv_list
    out["website"] = web_list
    out["data_note"] = note_list
    return out


def build_napkin_html(
    scored: pd.DataFrame,
    *,
    list_label: str = "",
    adj_tv: float | None = None,
    near_w: float | None = None,
    health: str = "",
) -> str:
    """Interactive filterable Napkin board."""
    if scored is None or scored.empty:
        return f"{_NAPKIN_CSS}<div class='nk-wrap'><div class='nk-empty'>No scored rows.</div></div>"

    counts = scored["verdict"].value_counts().to_dict() if "verdict" in scored.columns else {}
    n_buy = int(counts.get("Napkin Buy", 0))
    n_fair = int(counts.get("Fair Value", 0))
    n_over = int(counts.get("Overvalued", 0))
    n_miss = int(counts.get("Insufficient Data", 0) + counts.get("Unprofitable", 0))

    macro = ""
    if adj_tv is not None and near_w is not None:
        macro = (
            f"<span class='nk-chip'>Terminal {adj_tv:.0%}</span>"
            f"<span class='nk-chip'>Near {near_w:.0%}</span>"
        )

    rows_html: list[str] = []
    for _, r in scored.iterrows():
        verd = safe_str(r.get("verdict"))
        vc = _verdict_class(verd)
        tr_cls = "buy" if vc == "buy" else ""
        score_v = pd.to_numeric(r.get("napkin_score"), errors="coerce")
        score_cls = "pos" if pd.notna(score_v) and float(score_v) > 0 else (
            "neg" if pd.notna(score_v) and float(score_v) < 0 else ""
        )
        web = sanitize_website(r.get("website"))
        links = (
            f"<div class='nk-links'>"
            f"<a class='sc' href='{_esc(r.get('sc'))}' target='_blank' rel='noopener'>SC</a>"
            f"<a class='tv' href='{_esc(r.get('tv'))}' target='_blank' rel='noopener'>TV</a>"
        )
        if web:
            links += f"<a class='web' href='{_esc(web)}' target='_blank' rel='noopener'>Web</a>"
        links += "</div>"
        note = safe_str(r.get("data_note"))
        note_html = f"<div class='nk-name'>{_esc(note)}</div>" if note else ""
        rows_html.append(
            f"<tr class='{tr_cls}' data-verdict='{_esc(verd)}' data-ticker='{_esc(r.get('ticker'))}' "
            f"data-name='{_esc(r.get('name'))}'>"
            f"<td><div class='nk-ticker'>{_esc(r.get('ticker'))}</div>"
            f"<div class='nk-name'>{_esc(r.get('name'))}</div>{note_html}</td>"
            f"<td class='num'>{_pe(r.get('pe'))}</td>"
            f"<td class='num'>{_pct(r.get('required_cagr'))}</td>"
            f"<td class='num'>{_pct(r.get('expected_cagr'))}</td>"
            f"<td class='num nk-score {score_cls}'>{_score(r.get('napkin_score'))}</td>"
            f"<td><span class='nk-verdict {vc}'>{_esc(verd)}</span></td>"
            f"<td>{links}</td>"
            f"</tr>"
        )

    label = _esc(list_label) if list_label else "Napkin"
    return f"""
{_NAPKIN_CSS}
<div class="nk-wrap" id="nk-root">
  <div class="nk-meta">
    <strong style="color:#0f172a">{label}</strong>
    {macro}
    <span>{_esc(health)}</span>
    <span class="nk-chip buy active" data-filter="Napkin Buy">Buy {n_buy}</span>
    <span class="nk-chip fair" data-filter="Fair Value">Fair {n_fair}</span>
    <span class="nk-chip over" data-filter="Overvalued">Over {n_over}</span>
    <span class="nk-chip miss" data-filter="miss">Gaps {n_miss}</span>
    <span class="nk-chip" data-filter="all">All {len(scored)}</span>
    <input class="nk-search" id="nk-search" type="search" placeholder="Search ticker / name" />
  </div>
  <table class="nk">
    <thead>
      <tr>
        <th style="width:22%">Ticker</th>
        <th class="num" style="width:8%">PE</th>
        <th class="num" style="width:10%">Req</th>
        <th class="num" style="width:10%">Exp</th>
        <th class="num" style="width:10%">Score</th>
        <th style="width:14%">Verdict</th>
        <th style="width:16%">Links</th>
      </tr>
    </thead>
    <tbody id="nk-body">
      {''.join(rows_html)}
    </tbody>
  </table>
</div>
<script>
(function() {{
  const root = document.getElementById('nk-root');
  if (!root) return;
  let filter = 'Napkin Buy';
  const body = document.getElementById('nk-body');
  const search = document.getElementById('nk-search');
  function apply() {{
    const q = (search && search.value || '').trim().toLowerCase();
    body.querySelectorAll('tr').forEach(tr => {{
      const v = tr.getAttribute('data-verdict') || '';
      const hay = ((tr.getAttribute('data-ticker')||'') + ' ' + (tr.getAttribute('data-name')||'')).toLowerCase();
      let ok = true;
      if (filter === 'miss') ok = (v === 'Insufficient Data' || v === 'Unprofitable');
      else if (filter !== 'all') ok = (v === filter);
      if (q && !hay.includes(q)) ok = false;
      tr.style.display = ok ? '' : 'none';
    }});
  }}
  root.querySelectorAll('.nk-chip[data-filter]').forEach(chip => {{
    chip.addEventListener('click', () => {{
      filter = chip.getAttribute('data-filter') || 'all';
      root.querySelectorAll('.nk-chip[data-filter]').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      apply();
    }});
  }});
  if (search) search.addEventListener('input', apply);
  apply();
}})();
</script>
"""


def napkin_iframe_height(n_rows: int) -> int:
    return int(min(900, max(320, 140 + n_rows * 42)))


def embed_napkin_report(html_doc: str, *, height: int) -> None:
    embed_html_iframe(html_doc, height=height)


__all__ = [
    "build_napkin_html",
    "enrich_napkin_display",
    "embed_napkin_report",
    "napkin_iframe_height",
]
