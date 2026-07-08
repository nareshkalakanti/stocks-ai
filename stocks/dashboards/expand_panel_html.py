"""Shared snapshot + quarterly expand panel CSS/JS for strategy reports."""

EXPAND_PANEL_CSS = """
  tr.strat-row { cursor: pointer; }
  tr.strat-row.expanded td { background: #eff6ff !important; }
  tr.strat-expand td {
    padding: 10px 14px 14px;
    background: #f8fafc;
    border-bottom: 1px solid #e5e7eb;
    white-space: normal;
    vertical-align: top;
  }
  .expand-hint { color: #6b7280; font-size: 10px; margin-left: 6px; }
  tr.strat-row.expanded .expand-hint::after { content: "▴"; }
  tr.strat-row:not(.expanded) .expand-hint::after { content: "▾"; }
  .expand-body {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 20px;
    align-items: start;
    width: 100%;
  }
  @media (max-width: 960px) {
    .expand-body { grid-template-columns: 1fr; }
  }
  .q-panel { overflow-x: auto; padding: 10px 0 4px; }
  .q-table { width: 100%; border-collapse: collapse; min-width: 640px; font-size: 11px; }
  .q-table th, .q-table td {
    padding: 6px 10px;
    border: 1px solid #e5e7eb;
    text-align: right;
    white-space: nowrap;
  }
  .q-table th:first-child, .q-table td.q-label {
    text-align: left;
    font-weight: 600;
    min-width: 120px;
    position: sticky;
    left: 0;
    background: #fff;
    z-index: 1;
  }
  .q-table th { color: #6b7280; font-size: 10px; text-transform: uppercase; background: #f9fafb; }
  .q-table th.q-recent, .q-table td.q-recent { background: rgba(37, 99, 235, 0.08); }
  .q-table td.q-up { color: #059669; font-weight: 700; }
  .q-table td.q-down { color: #dc2626; font-weight: 700; }
  .q-table td.q-flat { color: #6b7280; }
  .q-empty { color: #6b7280; font-size: 12px; padding: 8px 4px; }
  .snap-panel { min-width: 300px; max-width: 340px; font-size: 12px; line-height: 1.35; }
  .snap-metrics {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 16px 20px;
    margin-bottom: 14px;
  }
  .snap-metric { display: inline-flex; align-items: baseline; gap: 6px; white-space: nowrap; }
  .snap-metric-label { font-size: 12px; color: #6b7280; font-weight: 500; }
  .snap-metric-val { font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .snap-metric-val.pos { color: #059669; }
  .snap-metric-val.neg { color: #dc2626; }
  .snap-class {
    font-size: 11px;
    color: #6b7280;
    line-height: 1.35;
    margin: -6px 0 12px;
    word-break: break-word;
  }
  .snap-class-sep { margin: 0 5px; opacity: 0.5; }
  .snap-section { margin-top: 14px; }
  .snap-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 8px;
  }
  .ma-pills { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .ma-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
    background: #f8fafc;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .ma-pill.above { border-color: rgba(5, 150, 105, 0.45); background: rgba(5, 150, 105, 0.12); }
  .ma-pill.below { border-color: rgba(220, 38, 38, 0.4); background: rgba(220, 38, 38, 0.1); }
  .ma-pill .ma-period { color: #6b7280; font-size: 12px; font-weight: 600; min-width: 22px; text-align: center; }
  .ma-pill .ma-val { font-weight: 700; font-size: 12px; margin-left: auto; }
  .ma-icon { width: 14px; font-size: 11px; font-weight: 800; flex-shrink: 0; }
  .ma-icon.up { color: #059669; }
  .ma-icon.down { color: #dc2626; }
  .range-wrap { margin-top: 2px; }
  .range-ends {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 8px;
    font-variant-numeric: tabular-nums;
  }
  .range-low { color: #dc2626; }
  .range-high { color: #059669; }
  .range-track {
    position: relative;
    height: 8px;
    border-radius: 999px;
    background: linear-gradient(90deg, #dc2626 0%, #fbbf24 50%, #059669 100%);
  }
  .range-thumb {
    position: absolute;
    top: 50%;
    width: 12px;
    height: 12px;
    margin-top: -6px;
    margin-left: -6px;
    border-radius: 50%;
    background: #4f46e5;
    border: 2px solid #fff;
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.3);
  }
  .company-cell { min-width: 0; }
  .company-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 0;
  }
  .company-name {
    font-weight: 600;
    font-size: 14px;
    line-height: 1.4;
    letter-spacing: -0.01em;
    white-space: normal;
    word-break: break-word;
    flex: 1;
    min-width: 0;
    color: #0f172a;
  }
  .company-tags-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px 6px;
    margin-top: 5px;
  }
  .company-actions { display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; }
  .links-inline { display: inline-flex; gap: 4px; flex-shrink: 0; }
  .links-inline a {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    background: #eff6ff;
    color: #1d4ed8;
    text-decoration: none;
    font-size: 10px;
    font-weight: 700;
  }
  .sub { color: #6b7280; font-size: 11px; }
  .corp-tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px 6px;
    margin: 0;
  }
  .corp-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    line-height: 1.25;
    padding: 3px 8px;
    border-radius: 5px;
    white-space: nowrap;
  }
  .corp-tag-bg { color: #5b21b6; background: #ede9fe; }
  .corp-tag-hold { color: #1d4ed8; background: #dbeafe; }
  .corp-tag-dem { color: #92400e; background: #fef3c7; }
  .corp-tag-spin { color: #0e7490; background: #cffafe; }
  .corp-tag-spec { color: #9d174d; background: #fce7f3; }
  .corp-tag-ss { color: #854d0e; background: #fef9c3; max-width: 240px; overflow: hidden; text-overflow: ellipsis; }
  .bg-tag {
    color: #7c3aed;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 2px;
  }
  .g-high { color: #059669; font-weight: 700; }
  .g-mid { color: #d97706; font-weight: 700; }
  .g-low { color: #dc2626; font-weight: 700; }
  .g-pos { color: #059669; font-weight: 600; }
  .g-neg { color: #dc2626; font-weight: 600; }
  td.company-td { white-space: normal; min-width: 240px; max-width: 400px; }
  .expand-wrap { display: flex; flex-direction: column; gap: 14px; width: 100%; }
  .note-stack {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 10px;
    width: 100%;
  }
  .note-card {
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    background: #fff;
    padding: 12px 14px;
    line-height: 1.45;
    font-size: 12px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  }
  .note-card.business { border-left: 4px solid #2563eb; }
  .note-card.market { border-left: 4px solid #059669; }
  .note-card.triggers { border-left: 4px solid #d97706; }
  .note-title {
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 6px;
  }
  .note-body { color: #374151; white-space: pre-wrap; }
  .note-list {
    margin: 0;
    padding-left: 18px;
    color: #374151;
  }
  .note-list li { margin-bottom: 4px; }
  .note-list li:last-child { margin-bottom: 0; }
  .note-source {
    margin-top: 8px;
    font-size: 10px;
    color: #9ca3af;
    font-style: italic;
  }
"""

CORP_TAGS_JS = """
function fmtCorpTags(r) {
  const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  const parts = [];
  if (r.business_group) parts.push(`<div class="corp-tag corp-tag-bg" title="${esc(r.business_group)}">${esc(r.business_group)}</div>`);
  if (r.is_holding) parts.push('<div class="corp-tag corp-tag-hold" title="In your Holdings portfolio">Holding</div>');
  if (r.demerger) parts.push('<div class="corp-tag corp-tag-dem">Demerger</div>');
  if (r.spin_off) parts.push('<div class="corp-tag corp-tag-spin">Spin off</div>');
  if (r.special_situation) parts.push('<div class="corp-tag corp-tag-spec">Special Situation</div>');
  if (r.ss_holders_label) {
    const ssLabel = String(r.ss_holders_label);
    const ssShow = (r.ss_best ? "★ " : "") + ssLabel;
    parts.push(`<div class="corp-tag corp-tag-ss" title="${esc(ssLabel)}">${esc(ssShow)}</div>`);
  }
  if (r.has_tq) {
    const tqTip = r.tq_crossover ? esc(r.tq_crossover) : "TQ signal (Strategy scan)";
    const tqLbl = r.tq_score != null && !isNaN(Number(r.tq_score))
      ? `TQ ${Number(r.tq_score).toFixed(0)}` : "TQ";
    parts.push(`<div class="corp-tag corp-tag-tq" title="${tqTip}">${tqLbl}</div>`);
  }
  if (r.has_bb) {
    const bbTip = esc((r.bb_signal || "BB") + (r.bb_timeframe ? " · " + r.bb_timeframe : ""));
    parts.push(`<div class="corp-tag corp-tag-bb" title="${bbTip}">BB</div>`);
  }
  if (!parts.length) return "";
  return `<div class="corp-tags">${parts.join("")}</div>`;
}
"""

EXPAND_PANEL_JS = """
function fmtQVal(v, decimals, pct) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  const suffix = pct ? "%" : "";
  if (decimals === 2) return n.toFixed(2) + suffix;
  return n.toLocaleString("en-IN", { maximumFractionDigits: 0 }) + suffix;
}
function fmtSnapNum(n) {
  if (n === null || isNaN(n)) return "—";
  return n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtMcapCr(n) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return Number(n).toLocaleString("en-IN", { maximumFractionDigits: 1 }) + " Cr";
}
function fmtSnapClass(s) {
  const parts = [];
  if (s.industry) parts.push(String(s.industry));
  if (s.sub_sector && String(s.sub_sector) !== String(s.industry || "")) {
    parts.push(String(s.sub_sector));
  }
  if (!parts.length) return "";
  const esc = (x) => String(x).replace(/&/g,"&amp;").replace(/</g,"&lt;");
  return `<div class="snap-class">${parts.map(esc).join('<span class="snap-class-sep">·</span>')}</div>`;
}
function renderSnapshotPanel(s) {
  if (!s || s.price == null) return "";
  const cagr = s.cagr == null || isNaN(s.cagr) ? null : Number(s.cagr);
  const cagrValCls = cagr === null ? "" : (cagr >= 0 ? "pos" : "neg");
  const cagrTxt = cagr === null ? "—" : `${cagr >= 0 ? "+" : ""}${cagr.toFixed(1)}%`;
  let maHtml = "";
  (s.moving_averages || []).forEach(ma => {
    const cls = ma.above ? "above" : "below";
    const icon = ma.above ? "✓" : "✕";
    const iconCls = ma.above ? "up" : "down";
    maHtml += `<span class="ma-pill ${cls}">` +
      `<span class="ma-icon ${iconCls}">${icon}</span>` +
      `<span class="ma-period">${ma.period}</span>` +
      `<span class="ma-val">${fmtSnapNum(ma.value)}</span></span>`;
  });
  let rangeHtml = "";
  const lo = s.w52_low, hi = s.w52_high, px = s.price;
  if (lo != null && hi != null && hi > lo && px != null) {
    const pct = Math.max(0, Math.min(100, ((px - lo) / (hi - lo)) * 100));
    rangeHtml = `<div class="range-wrap">` +
      `<div class="range-ends">` +
      `<span class="range-low">${fmtSnapNum(lo)}</span>` +
      `<span class="range-high">${fmtSnapNum(hi)}</span>` +
      `</div>` +
      `<div class="range-track"><span class="range-thumb" style="left:${pct.toFixed(1)}%"></span></div>` +
      `</div>`;
  } else {
    rangeHtml = `<div class="q-empty">No 52-week range</div>`;
  }
  return `<div class="snap-panel">` +
    `<div class="snap-metrics">` +
    `<div class="snap-metric"><span class="snap-metric-label">Price</span>` +
    `<span class="snap-metric-val">${fmtSnapNum(s.price)}</span></div>` +
    `<div class="snap-metric"><span class="snap-metric-label">Mkt cap</span>` +
    `<span class="snap-metric-val">${fmtMcapCr(s.market_cap_cr)}</span></div>` +
    `<div class="snap-metric"><span class="snap-metric-label">PE</span>` +
    `<span class="snap-metric-val">${s.pe_ratio != null ? Number(s.pe_ratio).toFixed(1) : (s.pe != null ? Number(s.pe).toFixed(1) : "—")}</span></div>` +
    `<div class="snap-metric"><span class="snap-metric-label">Fwd PE</span>` +
    `<span class="snap-metric-val">${s.forward_pe != null ? Number(s.forward_pe).toFixed(1) : "—"}</span></div>` +
    `<div class="snap-metric"><span class="snap-metric-label">CAGR</span>` +
    `<span class="snap-metric-val ${cagrValCls}">${cagrTxt}</span></div>` +
    `</div>` +
    fmtSnapClass(s) +
    `<div class="snap-section"><div class="snap-label">Moving averages</div>` +
    `<div class="ma-pills">${maHtml || "—"}</div></div>` +
    `<div class="snap-section"><div class="snap-label">52-week range</div>${rangeHtml}</div>` +
    `</div>`;
}
function renderQuarterPanel(q) {
  if (!q || !q.labels || !q.rows) {
    return '<div class="q-empty">No quarterly data.</div>';
  }
  const n = q.labels.length;
  let h = '<div class="q-panel"><table class="q-table"><thead><tr><th></th>';
  q.labels.forEach((lb, i) => {
    const recent = i >= n - 3 ? " q-recent" : "";
    h += `<th class="${recent}">${lb}</th>`;
  });
  h += "</tr></thead><tbody>";
  q.rows.forEach(row => {
    h += `<tr><td class="q-label">${row.label}</td>`;
    row.values.forEach((v, i) => {
      let cls = "";
      if (i > 0 && v != null && row.values[i - 1] != null) {
        const prev = row.values[i - 1];
        if (v > prev) cls = row.good_up ? " q-up" : " q-down";
        else if (v < prev) cls = row.good_up ? " q-down" : " q-up";
        else cls = " q-flat";
      }
      const recent = i >= n - 3 ? " q-recent" : "";
      h += `<td class="${cls}${recent}">${fmtQVal(v, row.decimals, row.pct)}</td>`;
    });
    h += "</tr>";
  });
  h += "</tbody></table></div>";
  return h;
}
function rowSnapshot(r) {
  let snap = r.snapshot ? { ...r.snapshot } : null;
  if (!snap && r.price != null) {
    snap = {
      price: r.price,
      market_cap_cr: r.market_cap_cr,
      pe: r.pe_ratio,
      pe_ratio: r.pe_ratio,
      forward_pe: r.forward_pe,
      cagr: null,
      w52_low: null,
      w52_high: null,
      moving_averages: [],
    };
  }
  if (snap) {
    if (snap.market_cap_cr == null && r.market_cap_cr != null) {
      snap.market_cap_cr = r.market_cap_cr;
    }
    if (snap.price == null && r.price != null) snap.price = r.price;
    if (snap.pe_ratio == null && r.pe_ratio != null) snap.pe_ratio = r.pe_ratio;
    if (snap.pe == null && r.pe_ratio != null) snap.pe = r.pe_ratio;
    if (snap.forward_pe == null && r.forward_pe != null) snap.forward_pe = r.forward_pe;
    if (r.industry) snap.industry = r.industry;
    if (r.sub_sector) snap.sub_sector = r.sub_sector;
    if (r.buy_headroom_pct != null) snap.buy_headroom_pct = r.buy_headroom_pct;
  }
  return snap;
}
function renderStockNotes(r) {
  const n = r.stock_note;
  if (!n) return "";
  const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  const parts = [];
  if (n.business) {
    parts.push(
      `<div class="note-card business">` +
      `<div class="note-title">Business</div>` +
      `<div class="note-body">${esc(n.business)}</div></div>`
    );
  }
  if (n.market_position) {
    parts.push(
      `<div class="note-card market">` +
      `<div class="note-title">Market position</div>` +
      `<div class="note-body">${esc(n.market_position)}</div></div>`
    );
  }
  if (n.triggers && n.triggers.length) {
    const items = n.triggers.map(t => `<li>${esc(t)}</li>`).join("");
    parts.push(
      `<div class="note-card triggers">` +
      `<div class="note-title">Trigger points</div>` +
      `<ul class="note-list">${items}</ul></div>`
    );
  }
  if (!parts.length) return "";
  const src = n.source ? `<div class="note-source">${esc(n.source)}</div>` : "";
  return `<div class="note-stack">${parts.join("")}${src}</div>`;
}
function renderStrategyBreakout(r) {
  if (!r.has_tq && !r.has_bb) return "";
  const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  let inner = "";
  if (r.has_tq) {
    const sc = r.tq_score != null && !isNaN(Number(r.tq_score))
      ? Number(r.tq_score).toFixed(1) : "—";
    inner += `<div class="snap-metric"><span class="snap-metric-label">TQ score</span>` +
      `<span class="snap-metric-val">${sc}</span></div>`;
    if (r.tq_crossover) {
      inner += `<div class="snap-class">${esc(r.tq_crossover)}</div>`;
    }
  }
  if (r.has_bb) {
    const bb = (r.bb_signal || "ABOVE_BAND") + (r.bb_timeframe ? " · " + r.bb_timeframe : "");
    inner += `<div class="snap-metric"><span class="snap-metric-label">BB</span>` +
      `<span class="snap-metric-val">${esc(bb)}</span></div>`;
  }
  return `<div class="snap-section"><div class="snap-label">Strategy (SQLite)</div>` +
    `<div class="snap-metrics">${inner}</div></div>`;
}
function renderExpandPanel(r) {
  const notesHtml = renderStockNotes(r);
  const snapHtml = renderSnapshotPanel(rowSnapshot(r));
  const stratHtml = renderStrategyBreakout(r);
  const q = renderQuarterPanel(r.quarters);
  const bodyParts = [];
  if (snapHtml) bodyParts.push(snapHtml);
  if (stratHtml) bodyParts.push(`<div>${stratHtml}</div>`);
  if (q) bodyParts.push(`<div>${q}</div>`);
  const body = bodyParts.length
    ? `<div class="expand-body">${bodyParts.join("")}</div>`
    : "";
  if (notesHtml && body) return `<div class="expand-wrap">${notesHtml}${body}</div>`;
  if (notesHtml) return `<div class="expand-wrap">${notesHtml}</div>`;
  if (body) return body;
  return '<div class="q-empty">No detail data.</div>';
}
"""

EXPAND_PANEL_JS = CORP_TAGS_JS + EXPAND_PANEL_JS
