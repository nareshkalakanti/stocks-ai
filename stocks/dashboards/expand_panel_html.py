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
    grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
    gap: 12px;
    align-items: start;
    width: 100%;
  }
  .expand-main {
    min-width: 0;
    width: 100%;
  }
  @media (max-width: 960px) {
    .expand-body { grid-template-columns: 1fr; }
  }
  .q-panel { overflow-x: auto; padding: 4px 0 2px; }
  .q-table { width: 100%; border-collapse: collapse; min-width: 480px; font-size: 11px; }
  .q-table th, .q-table td {
    padding: 4px 8px;
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
  .expand-pead {
    grid-template-columns: minmax(0, 1fr);
  }
  .expand-news-only {
    max-width: 640px;
  }
  .q-empty { color: #6b7280; font-size: 12px; padding: 8px 4px; }
  .snap-panel { min-width: 220px; max-width: 300px; font-size: 11px; line-height: 1.3; }
  .snap-metrics {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px 12px;
    margin-bottom: 8px;
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
  .co-profile {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .co-profile-website { line-height: 1.35; }
  .co-website {
    color: #2563eb;
    font-size: 12px;
    font-weight: 600;
    text-decoration: none;
    word-break: break-word;
  }
  .co-website::after {
    content: "↗";
    font-size: 10px;
    margin-left: 4px;
    opacity: 0.7;
  }
  .co-website:hover { text-decoration: underline; }
  .co-profile-meta {
    font-size: 12px;
    line-height: 1.5;
    color: #64748b;
    word-break: break-word;
    font-weight: 500;
  }
  .co-profile-meta-sep { margin: 0 5px; opacity: 0.4; }
  .co-profile-about {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
  .co-profile-desc {
    margin: 0;
    font-size: 13px;
    line-height: 1.6;
    color: #334155;
    white-space: pre-wrap;
    word-break: break-word;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 4;
    overflow: hidden;
  }
  .co-profile-desc.expanded {
    display: block;
    -webkit-line-clamp: unset;
  }
  .co-profile-more {
    border: none;
    background: none;
    padding: 0;
    font-size: 11px;
    font-weight: 600;
    color: #2563eb;
    cursor: pointer;
    line-height: 1.3;
  }
  .co-profile-more:hover { text-decoration: underline; }
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
  .expand-detail-stack {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 8px;
    align-items: start;
  }
  @media (max-width: 960px) {
    .expand-detail-stack { grid-template-columns: 1fr; }
  }
  .expand-info-card {
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    background: #fff;
    padding: 8px 10px 10px;
    min-width: 0;
  }
  .expand-info-card.profile { border-left: 3px solid #2563eb; }
  .expand-info-card.news { border-left: 3px solid #7c3aed; }
  .expand-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
  }
  .expand-card-title {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748b;
  }
  .expand-card-action {
    font-size: 10px;
    font-weight: 600;
    color: #2563eb;
    text-decoration: none;
    white-space: nowrap;
  }
  .expand-card-action:hover { text-decoration: underline; }
  .expand-info-card .co-profile { gap: 5px; }
  .expand-info-card .co-profile-meta { font-size: 10px; line-height: 1.35; }
  .expand-info-card .co-website { font-size: 10px; }
  .expand-info-card .co-profile-desc {
    font-size: 11px;
    line-height: 1.45;
    -webkit-line-clamp: 2;
  }
  .expand-info-card .co-profile-more { font-size: 10px; }
  .co-news-list { display: flex; flex-direction: column; }
  .co-news-item {
    padding: 5px 0;
    border-bottom: 1px solid #f1f5f9;
  }
  .co-news-item:last-child { border-bottom: none; }
  .co-news-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 2px;
    font-size: 9px;
    color: #94a3b8;
  }
  .co-news-tag {
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #1d4ed8;
    background: #dbeafe;
    padding: 1px 5px;
    border-radius: 999px;
  }
  .co-news-link {
    font-size: 11px;
    line-height: 1.35;
    color: #0f172a;
    text-decoration: none;
    font-weight: 600;
  }
  .co-news-link:hover { color: #2563eb; text-decoration: underline; }
  .expand-news-only { max-width: 720px; }
  .q-empty { color: #6b7280; font-size: 11px; padding: 4px 0; }
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
  if (!parts.length) return "";
  return `<div class="corp-tags">${parts.join("")}</div>`;
}
"""

EXPAND_PANEL_JS = """
function fmtPctNum(n) {
  const v = Number(n);
  if (!isFinite(v)) return "—";
  const t = Math.trunc(v * 10) / 10;
  return t.toLocaleString("en-IN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  });
}
function fmtQVal(v, decimals, pct) {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (isNaN(n)) return "—";
  const suffix = pct ? "%" : "";
  if (pct) return fmtPctNum(n) + suffix;
  if (decimals === 2) {
    return n.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }) + suffix;
  }
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
function fmtWebsite(url) {
  if (!url) return "";
  const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  let href = String(url).trim();
  if (!/^https?:\\/\\//i.test(href)) href = "https://" + href;
  let label = href;
  try {
    const host = new URL(href).hostname.replace(/^www\\./i, "");
    if (host) label = host;
  } catch (_) {}
  return `<a class="co-website" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
}
function toggleCoAbout(btn) {
  const block = btn.closest(".co-profile-about");
  if (!block) return;
  const desc = block.querySelector(".co-profile-desc");
  if (!desc) return;
  const open = desc.classList.toggle("expanded");
  btn.textContent = open ? "Show less" : "Show more";
  btn.setAttribute("aria-expanded", open ? "true" : "false");
}
function fmtCoMeta(s) {
  if (!s) return "";
  const esc = (x) => String(x).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  const parts = [];
  if (s.company_sector) parts.push(esc(s.company_sector));
  if (s.company_industry && s.company_industry !== s.company_sector) {
    parts.push(esc(s.company_industry));
  }
  if (s.headquarters) parts.push(esc(s.headquarters));
  if (s.employees != null && !isNaN(Number(s.employees))) {
    parts.push(esc(Number(s.employees).toLocaleString("en-IN")) + " employees");
  }
  if (!parts.length) return "";
  return `<div class="co-profile-meta">${parts.join('<span class="co-profile-meta-sep">·</span>')}</div>`;
}
function renderCompanyProfileBody(s) {
  const desc = s?.long_description;
  const web = s?.website;
  const meta = fmtCoMeta(s);
  if (!desc && !web && !meta) return "";
  const esc = (x) => String(x).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  let html = '<div class="co-profile">';
  if (meta) html += meta;
  if (web) html += `<div class="co-profile-website">${fmtWebsite(web)}</div>`;
  if (desc) {
    const long = desc.length > 120;
    html += `<div class="co-profile-about">` +
      `<p class="co-profile-desc${long ? "" : " expanded"}">${esc(desc)}</p>` +
      (long ? `<button type="button" class="co-profile-more" aria-expanded="false" onclick="toggleCoAbout(this)">Show more</button>` : "") +
      `</div>`;
  }
  html += "</div>";
  return html;
}
function renderProfileCard(s) {
  const body = renderCompanyProfileBody(s);
  if (!body) return "";
  return (
    `<div class="expand-info-card profile">` +
    `<div class="expand-card-head"><div class="expand-card-title">Company</div></div>` +
    body + `</div>`
  );
}
function renderNewsCard(r) {
  const items = r.news;
  if (!items || !items.length) return "";
  const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  let head = `<div class="expand-card-head"><div class="expand-card-title">Google News</div>`;
  if (r.news_search_url) {
    head += `<a class="expand-card-action" href="${esc(r.news_search_url)}" target="_blank" rel="noopener noreferrer">View all ↗</a>`;
  }
  head += `</div><div class="co-news-list">`;
  let list = "";
  items.slice(0, 3).forEach((item, idx) => {
    const title = esc(item.title || "");
    const url = esc(item.url || "");
    const when = esc(item.when || item.published || "—");
    const source = item.source ? esc(item.source) : "";
    const tag = idx === 0 ? '<span class="co-news-tag">Latest</span>' : "";
    const meta = source ? `${tag}<span>${when}</span><span>·</span><span>${source}</span>` : `${tag}<span>${when}</span>`;
    list += `<div class="co-news-item"><div class="co-news-meta">${meta}</div>` +
      `<a class="co-news-link" href="${url}" target="_blank" rel="noopener noreferrer">${title}</a></div>`;
  });
  return `<div class="expand-info-card news">${head}${list}</div></div>`;
}
function renderDetailCards(r, snap) {
  const profile = renderProfileCard(snap);
  const news = renderNewsCard(r);
  if (!profile && !news) return "";
  return `<div class="expand-detail-stack">${profile}${news}</div>`;
}
function renderSnapshotPanel(s) {
  if (!s || s.price == null) return "";
  const cagr = s.cagr == null || isNaN(s.cagr) ? null : Number(s.cagr);
  const cagrValCls = cagr === null ? "" : (cagr >= 0 ? "pos" : "neg");
  const cagrTxt = cagr === null ? "—" : `${cagr >= 0 ? "+" : ""}${fmtPctNum(cagr)}%`;
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
    `<div class="snap-metric"><span class="snap-metric-label">CAGR</span>` +
    `<span class="snap-metric-val ${cagrValCls}">${cagrTxt}</span></div>` +
    `</div>` +
    fmtSnapClass(s) +
    `<div class="snap-section"><div class="snap-label">Moving averages</div>` +
    `<div class="ma-pills">${maHtml || "—"}</div></div>` +
    `<div class="snap-section"><div class="snap-label">52-week range</div>${rangeHtml}</div>` +
    `</div>`;
}
function qNum(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}
function qCellClass(row, i) {
  if (i <= 0) return "";
  const cur = qNum(row.values[i]);
  const prev = qNum(row.values[i - 1]);
  if (cur === null || prev === null) return "";
  const goodUp = row.good_up !== false;
  if (cur > prev) return goodUp ? "q-up" : "q-down";
  if (cur < prev) return goodUp ? "q-down" : "q-up";
  return "q-flat";
}
function renderQuarterPanel(q) {
  if (!q || !q.labels || !q.rows) {
    return '<div class="q-empty">No quarterly data.</div>';
  }
  const skipRows = new Set(["Current PE", "Forward PE", "Forward EPS"]);
  const rows = q.rows.filter(row => !skipRows.has(String(row.label || "")));
  const n = q.labels.length;
  let h = '<div class="q-panel"><table class="q-table"><thead><tr><th></th>';
  q.labels.forEach((lb, i) => {
    const recent = i >= n - 3 ? "q-recent" : "";
    h += `<th class="${recent}">${lb}</th>`;
  });
  h += "</tr></thead><tbody>";
  rows.forEach(row => {
    h += `<tr><td class="q-label">${row.label}</td>`;
    row.values.forEach((v, i) => {
      const tone = qCellClass(row, i);
      const recent = i >= n - 3 ? "q-recent" : "";
      const cls = [tone, recent].filter(Boolean).join(" ");
      h += `<td${cls ? ` class="${cls}"` : ""}>${fmtQVal(v, row.decimals, row.pct)}</td>`;
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
    if (!snap.company_sector && r.sector) snap.company_sector = r.sector;
    if (!snap.company_industry && r.industry) snap.company_industry = r.industry;
    if (!snap.company_industry && r.sub_sector) snap.company_industry = r.sub_sector;
    if (!snap.long_description && r.long_description) snap.long_description = r.long_description;
    if (!snap.website && r.website) snap.website = r.website;
    if (!snap.company_sector && r.company_sector) snap.company_sector = r.company_sector;
    if (!snap.company_industry && r.company_industry) snap.company_industry = r.company_industry;
    if (!snap.headquarters && r.headquarters) snap.headquarters = r.headquarters;
    if (snap.employees == null && r.employees != null) snap.employees = r.employees;
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
function renderExpandPanel(r) {
  const snap = rowSnapshot(r);
  const snapHtml = renderSnapshotPanel(snap);
  const qHtml = renderQuarterPanel(r.quarters);
  const cardsHtml = renderDetailCards(r, snap);
  if (!snapHtml && !qHtml && !cardsHtml) {
    return renderExpandPanelNews(r);
  }
  const soloClass = snapHtml ? "" : " expand-pead-solo";
  let body = `<div class="expand-body expand-pead${soloClass}">`;
  if (snapHtml) body += snapHtml;
  body += `<div class="expand-main">${qHtml || ""}${cardsHtml || ""}</div>`;
  body += `</div>`;
  return body;
}
function renderExpandPanelNews(r) {
  const news = renderNewsCard(r);
  if (news) return `<div class="expand-news-only">${news}</div>`;
  return '<div class="q-empty">No Google News found.</div>';
}
"""

EXPAND_PANEL_JS = CORP_TAGS_JS + EXPAND_PANEL_JS
