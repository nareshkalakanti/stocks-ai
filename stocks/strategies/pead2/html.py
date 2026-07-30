"""PEAD 2 dashboard HTML — light/dark theme, SC/TV links, fullscreen."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from stocks.shared.corp_tags import corp_tags_dict_for_ticker
from stocks.shared.superstars.holdings import superstar_pead_map
from stocks.shared.stock_notes import attach_stock_notes, sync_stock_notes_from_file
from stocks.dashboards.expand_panel_html import EXPAND_PANEL_JS
from stocks.strategies.pead2.strategy import enrich_pead_candidates, attach_strategy_breakout_signals
from stocks.strategies.pead2.quarters import sanitize_quarter_panel
from stocks.shared.links import research_links, resolve_listing_market
from stocks.core.text_utils import sanitize_website
from stocks.core.database import load_market_cap_from_db
from stocks.core.text_utils import safe_str
from stocks.core.json_utils import json_safe_bool


_PEAD2_UI_BUILD = "2026-07-30i"

_EXPAND_PAYLOAD_KEYS = frozenset(
    {
        "quarters",
        "snapshot",
        "long_description",
        "google_news",
        "news",
        "stock_note",
    }
)
# Large boards: keep quarters+slim snapshot; news/bios stay stripped.
# Served via /app/static so this payload no longer blanks the iframe.
_LARGE_REPORT_ROWS = 120
_EXPAND_KEYS_LARGE = frozenset({"quarters", "snapshot"})
_SNAPSHOT_SLIM_KEYS = frozenset(
    {
        "price",
        "market_cap_cr",
        "pe",
        "pe_ratio",
        "forward_pe",
        "cagr",
        "w52_low",
        "w52_high",
        "moving_averages",
        "website",
        "company_sector",
        "company_industry",
        "headquarters",
        "employees",
        "daily_change_pct",
    }
)

_PEAD2_FONT_LINKS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
"""

_PEAD2_DASHBOARD_CSS = """
<style>
  :root, [data-theme="light"] {
    --bg: #f4f6f9;
    --panel: #ffffff;
    --panel-2: #f8fafc;
    --border: #e2e8f0;
    --text: #0f172a;
    --muted: #64748b;
    --accent: #2563eb;
    --accent-soft: #eff6ff;
    --input-bg: #ffffff;
    --row-even: #f8fafc;
    --row-hover: #f1f5f9;
    --thead: #f1f5f9;
    --btn-bg: #ffffff;
    --btn-hover: #f1f5f9;
    --link: #2563eb;
    --link-bg: #eff6ff;
    --green: #059669;
    --green-dk: #047857;
    --green-bg: #ecfdf5;
    --amber: #d97706;
    --amber-bg: #fffbeb;
    --red: #dc2626;
    --red-bg: #fef2f2;
    --shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  }
  [data-theme="dark"] {
    --bg: #0a0c10;
    --panel: #12151c;
    --panel-2: #0d1017;
    --border: #2a3140;
    --text: #e8eaed;
    --muted: #9aa3b2;
    --accent: #6ea8fe;
    --accent-soft: #1a2744;
    --input-bg: #0d1017;
    --row-even: #0f1219;
    --row-hover: #1a2030;
    --thead: #141820;
    --btn-bg: #1a2030;
    --btn-hover: #252d3d;
    --link: #6ea8fe;
    --link-bg: #1a2744;
    --green: #4ade80;
    --green-dk: #166534;
    --green-bg: #14281f;
    --amber: #fbbf24;
    --amber-bg: #2d2618;
    --red: #f87171;
    --red-bg: #2d1818;
    --shadow: 0 2px 12px rgba(0, 0, 0, 0.45);
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    height: 100%;
    font-family: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 13.5px;
    line-height: 1.45;
    letter-spacing: -0.01em;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
  }
  body.fs-active { overflow: hidden; }
  .dash {
    display: grid;
    grid-template-columns: 1fr;
    height: 100%;
    min-height: 680px;
  }
  .dash.fs {
    position: fixed;
    inset: 0;
    z-index: 99999;
    min-height: 100vh;
    height: 100vh;
    background: var(--bg);
    box-shadow: var(--shadow);
  }
  .sidebar {
    background: var(--panel);
    border-right: 1px solid var(--border);
    padding: 16px 14px;
    overflow-y: auto;
    min-width: 0;
  }
  .sidebar-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin: 0 0 14px;
  }
  .dash.sidebar-hidden .sidebar {
    padding: 0;
    border: none;
    overflow: hidden;
  }
  .main {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    padding: 8px 10px;
    overflow: hidden;
  }
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }
  .title { font-size: 17px; font-weight: 700; margin: 0; letter-spacing: -0.02em; }
  .meta { color: var(--muted); font-size: 11px; margin-top: 2px; font-weight: 500; }
  .top-actions { display: flex; gap: 6px; flex-wrap: wrap; }
  .icon-btn {
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--btn-bg);
    color: var(--text);
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }
  .icon-btn:hover { background: var(--btn-hover); }
  .icon-btn.on { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
  .quarter-toggle { display: inline-flex; gap: 4px; margin-left: 10px; vertical-align: middle; }
  .quarter-btn {
    padding: 5px 10px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--btn-bg);
    color: var(--muted);
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
  }
  .quarter-btn.on {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }
  .quarter-btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .recent-days { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  .recent-days-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-right: 2px;
  }
  .filter-block { margin-bottom: 14px; }
  .filter-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .filter-row { margin-bottom: 9px; }
  .filter-row label { display: block; font-size: 12px; color: var(--text); margin-bottom: 4px; }
  input[type="range"] { width: 100%; accent-color: var(--accent); }
  input[type="text"] {
    width: 100%;
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    padding: 6px 8px;
    font-size: 12px;
  }
  .range-val { float: right; color: var(--accent); font-weight: 600; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .btn {
    width: 100%;
    margin-top: 6px;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--btn-bg);
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
  }
  .btn:hover { background: var(--btn-hover); }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }
  .pead-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 16px;
    align-items: center;
    margin: 0 0 12px;
    padding: 10px 12px;
    border-radius: 10px;
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 12px;
  }
  .pead-legend strong { color: var(--text); }
  .pead-section-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    margin: 0 0 10px;
  }
  .pead-picks {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
    margin: 0 0 14px;
  }
  .pead-pick {
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--panel);
    padding: 12px 12px 10px;
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .pead-pick:hover {
    border-color: var(--accent);
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.08);
  }
  .pead-pick.high {
    border-color: rgba(34, 197, 94, 0.45);
    background: linear-gradient(180deg, rgba(34, 197, 94, 0.08), var(--panel));
  }
  .pead-pick.strong {
    border-color: rgba(34, 197, 94, 0.55);
    background: linear-gradient(180deg, rgba(34, 197, 94, 0.1), var(--panel));
  }
  .pead-pick.caution {
    border-color: rgba(245, 158, 11, 0.55);
    background: linear-gradient(180deg, rgba(245, 158, 11, 0.08), var(--panel));
  }
  [data-theme="dark"] .pead-pick.high,
  [data-theme="dark"] .pead-pick.strong {
    background: linear-gradient(180deg, rgba(34, 197, 94, 0.12), var(--panel));
  }
  [data-theme="dark"] .pead-pick.caution {
    background: linear-gradient(180deg, rgba(245, 158, 11, 0.12), var(--panel));
  }
  .pead-pick-top {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: flex-start;
  }
  .pead-pick-ticker {
    font-size: 15px;
    font-weight: 800;
    color: var(--accent);
    text-decoration: none;
    letter-spacing: -0.02em;
  }
  .pead-pick-ticker:hover { text-decoration: underline; }
  .pead-pick-name {
    color: var(--muted);
    font-size: 12px;
    margin-top: 3px;
    line-height: 1.35;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .pead-pick-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 6px;
  }
  .pead-pick-chip {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    letter-spacing: 0.02em;
  }
  .pead-pick-chip.tq { background: rgba(29, 78, 216, 0.12); color: #1d4ed8; }
  .pead-pick-chip.bb { background: rgba(180, 83, 9, 0.12); color: #b45309; }
  .pead-pick-chip.pe-good { background: rgba(22, 163, 74, 0.12); color: #15803d; }
  .pead-pick-chip.pe-bad { background: rgba(220, 38, 38, 0.12); color: #b91c1c; }
  .pead-pick-scoreblk { text-align: right; min-width: 64px; }
  .pead-pick-badge {
    display: inline-block;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding: 2px 7px;
    border-radius: 999px;
    margin-bottom: 4px;
  }
  .pead-pick-badge.strong { background: #dcfce7; color: #166534; }
  .pead-pick-badge.soft { background: #e0e7ff; color: #3730a3; }
  .pead-pick-badge.caution { background: #fef3c7; color: #92400e; }
  .pead-pick-badge.watch { background: #f1f5f9; color: #475569; }
  [data-theme="dark"] .pead-pick-badge.strong { background: rgba(22,163,74,0.25); color: #86efac; }
  [data-theme="dark"] .pead-pick-badge.soft { background: rgba(99,102,241,0.25); color: #c7d2fe; }
  [data-theme="dark"] .pead-pick-badge.caution { background: rgba(245,158,11,0.25); color: #fcd34d; }
  [data-theme="dark"] .pead-pick-badge.watch { background: rgba(148,163,184,0.2); color: #cbd5e1; }
  .pead-pick-score {
    font-size: 22px;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .pead-pick-score.high { color: var(--green); }
  .pead-pick-score.mid { color: var(--text); }
  .pead-pick-score.low { color: var(--muted); }
  .pead-pick-score-lbl {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-top: 2px;
  }
  .pead-pick-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 12px;
    font-size: 12px;
  }
  .pead-pick-stat span {
    display: block;
    color: var(--muted);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .pead-pick-stat b {
    display: block;
    color: var(--text);
    font-size: 15px;
    margin-top: 2px;
    font-variant-numeric: tabular-nums;
  }
  .pead-fpe.good { color: var(--green); }
  .pead-fpe.mid { color: #ca8a04; }
  .pead-fpe.bad { color: var(--red); }
  .pead-fpe.missing { color: var(--muted); }
  .pead-pick-links {
    display: flex;
    gap: 8px;
    margin-top: 10px;
    font-size: 11px;
    font-weight: 600;
  }
  .pead-pick-links a {
    color: var(--accent);
    text-decoration: none;
  }
  .pead-pick-links a:hover { text-decoration: underline; }
  .pead-pick-date {
    margin-left: auto;
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
  }
  .pead-picks-empty {
    padding: 12px;
    color: var(--muted);
    font-size: 12px;
    border: 1px dashed var(--border);
    border-radius: 10px;
    margin-bottom: 14px;
  }
  .signal-filter {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
  }
  .signal-filter-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-right: 2px;
  }
  .signal-btn {
    padding: 5px 9px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--btn-bg);
    color: var(--muted);
    cursor: pointer;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }
  .signal-btn.on {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }
  .signal-btn.buy.on { background: #15803d; border-color: #15803d; }
  .signal-btn.fund.on { background: #a16207; border-color: #a16207; }
  .signal-btn.tq.on { background: #1d4ed8; border-color: #1d4ed8; }
  .signal-btn.bb.on { background: #b45309; border-color: #b45309; }
  .signal-btn.both.on { background: #7c3aed; border-color: #7c3aed; }
  .pead-search {
    flex: 1 1 180px;
    max-width: 300px;
    min-width: 140px;
    background: var(--input-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    padding: 6px 10px;
    font-size: 12px;
  }
  .pead-search::placeholder { color: var(--muted); }
  .pead-search:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-soft);
  }
  .count { color: var(--muted); font-size: 12px; font-weight: 600; flex: 1 1 auto; }
  .col-toggle button {
    padding: 4px 8px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--btn-bg);
    color: var(--muted);
    font-size: 11px;
    cursor: pointer;
  }
  .col-toggle button.on { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
  .table-wrap {
    flex: 1;
    min-height: 0;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    box-shadow: var(--shadow);
  }
  table#pead-table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    min-width: 620px;
  }
  #pead-table th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--thead);
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    text-transform: none;
    letter-spacing: 0.01em;
    padding: 6px 8px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  #pead-table th.col-num { text-align: right; }
  #pead-table th .th-inner {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    width: 100%;
  }
  #pead-table th.col-num .th-inner { justify-content: flex-end; }
  #pead-table th:hover { color: var(--accent); }
  #pead-table tr.pead-row > td {
    padding: 5px 8px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    vertical-align: middle;
    color: var(--text);
    font-size: 12px;
  }
  #pead-table td.pead-expand-td {
    padding: 0;
    border-bottom: 1px solid var(--border);
    white-space: normal;
    vertical-align: top;
  }
  #pead-table td.col-num { text-align: right; }
  #pead-table th.col-company,
  #pead-table td.company-td { width: 34%; }
  #pead-table th.col-num,
  #pead-table td.col-num { width: 11%; }
  th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--thead);
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    text-transform: none;
    letter-spacing: 0.01em;
    padding: 6px 8px;
    text-align: left;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  th:hover { color: var(--accent); }
  td {
    padding: 5px 8px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    vertical-align: middle;
    color: var(--text);
    font-size: 12px;
  }
  td.sym-td {
    font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: -0.02em;
    color: var(--text);
  }
  td.sector-td {
    color: var(--muted);
    font-size: 12px;
    font-weight: 500;
    max-width: 150px;
    white-space: normal;
    line-height: 1.35;
    letter-spacing: -0.01em;
  }
  td.company-td {
    white-space: normal;
    min-width: 160px;
    max-width: 280px;
    vertical-align: middle;
  }
  tr:nth-child(even) td { background: var(--row-even); }
  tr:hover td { background: var(--row-hover); }
  .company-cell { min-width: 0; }
  .company-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .company-name-wrap {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex: 1;
    min-width: 0;
  }
  .company-name {
    font-weight: 600;
    font-size: 14px;
    color: var(--text);
    line-height: 1.4;
    letter-spacing: -0.01em;
    white-space: normal;
    word-break: break-word;
    min-width: 0;
  }
  .company-tags-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 5px 6px;
    margin-top: 5px;
    min-height: 0;
  }
  .company-tags-row:empty { display: none; margin: 0; }
  .pead-skip {
    color: var(--muted);
    cursor: help;
    border-bottom: 1px dotted var(--muted);
  }
  .ss-holders { margin-top: 6px; font-size: 11px; color: var(--muted); line-height: 1.4; }
  .ss-holders strong { color: var(--text); font-weight: 600; }
  .ss-best-tag {
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 1px 6px;
    border-radius: 4px;
    margin-right: 6px;
    background: var(--green-bg);
    color: var(--green-dk);
  }
  .ss-best-yes {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    font-weight: 700;
    font-size: 13px;
    background: var(--green-bg);
    color: var(--green-dk);
  }
  .strat-signal-yes {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    font-weight: 700;
    font-size: 11px;
    background: var(--accent-soft);
    color: var(--accent);
  }
  .strat-signal-yes.bb {
    background: var(--amber-bg);
    color: var(--amber);
  }
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
  .corp-tag-sme { color: #9a3412; background: #ffedd5; }
  .corp-tag-dem { color: #92400e; background: #fef3c7; }
  .corp-tag-spin { color: #0e7490; background: #cffafe; }
  .corp-tag-tq { color: #1d4ed8; background: #dbeafe; }
  .corp-tag-bb { color: #b45309; background: #fef3c7; }
  [data-theme="dark"] .corp-tag-bg { color: #ddd6fe; background: #4c1d95; }
  [data-theme="dark"] .corp-tag-hold { color: #bfdbfe; background: #1e3a8a; }
  [data-theme="dark"] .corp-tag-sme { color: #fdba74; background: #7c2d12; }
  [data-theme="dark"] .corp-tag-dem { color: #fde68a; background: #78350f; }
  [data-theme="dark"] .corp-tag-spin { color: #a5f3fc; background: #155e75; }
  [data-theme="dark"] .corp-tag-tq { color: #bfdbfe; background: #1e3a8a; }
  [data-theme="dark"] .corp-tag-bb { color: #fde68a; background: #78350f; }
  .bg-tag {
    color: #a78bfa;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 3px;
  }
  .company-actions {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .links-inline { display: inline-flex; gap: 4px; flex-shrink: 0; }
  .links-inline a {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    background: var(--link-bg);
    color: var(--link);
    text-decoration: none;
    font-size: 10px;
    font-weight: 700;
    line-height: 1.4;
  }
  .links-inline a:hover { text-decoration: underline; }
  .sub { color: var(--muted); font-size: 11px; }
  .num { color: var(--text); font-weight: 500; font-variant-numeric: tabular-nums; }
  .g-high { color: var(--green); font-weight: 700; }
  .g-mid { color: var(--amber); font-weight: 700; }
  .g-low { color: var(--red); font-weight: 700; }
  .g-pos { color: var(--green); font-weight: 600; }
  .g-neg { color: var(--red); font-weight: 600; }
  .g-fpe-good { color: var(--green); font-weight: 600; }
  .g-fpe-mid { color: var(--amber); font-weight: 600; }
  .g-fpe-bad { color: var(--red); font-weight: 600; }
  #pead-table tr.pead-row > td .g-fpe-good { color: var(--green); font-weight: 600; }
  #pead-table tr.pead-row > td .g-fpe-mid { color: var(--amber); font-weight: 600; }
  #pead-table tr.pead-row > td .g-fpe-bad { color: var(--red); font-weight: 600; }
  .badge-score {
    display: inline-block;
    min-width: 42px;
    text-align: center;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.2;
    font-variant-numeric: tabular-nums;
  }
  .badge-score.high {
    background: var(--green-bg);
    color: var(--green);
    border: 1px solid rgba(74, 222, 128, 0.25);
  }
  .badge-score.mid {
    background: var(--amber-bg);
    color: var(--amber);
    border: 1px solid rgba(251, 191, 36, 0.25);
  }
  .badge-score.low {
    background: var(--red-bg);
    color: var(--red);
    border: 1px solid rgba(248, 113, 113, 0.2);
  }
  [data-theme="dark"] .badge-score.high {
    background: #1a3328;
    color: #4ade80;
    border-color: #166534;
  }
  [data-theme="dark"] .badge-score.mid {
    background: #2d2818;
    color: #fbbf24;
    border-color: #854d0e;
  }
  [data-theme="dark"] .badge-score.low {
    background: #2d1a1a;
    color: #f87171;
    border-color: #991b1b;
  }
  .sort-hint {
    color: var(--muted);
    font-size: 11px;
    font-weight: 500;
    margin-bottom: 6px;
  }
  .calc-dt { color: var(--muted); font-size: 11px; font-weight: 500; font-variant-numeric: tabular-nums; }
  .sort-ind {
    color: var(--muted);
    font-size: 10px;
    opacity: 0.55;
    flex-shrink: 0;
  }
  .sort-ind.active { color: var(--accent); opacity: 1; font-weight: 700; }
  .show-sidebar-btn { display: none; margin-bottom: 8px; }
  .dash.sidebar-hidden .show-sidebar-btn { display: inline-block; }
  tr.pead-row { cursor: pointer; }
  tr.pead-row.expanded td { background: var(--accent-soft) !important; }
  tr.pead-expand td.pead-expand-td {
    padding: 0;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    white-space: normal;
    vertical-align: top;
  }
  #pead-table td.pead-expand-td .pead-card {
    width: 100%;
    max-width: none;
    border: none;
    border-radius: 0;
    box-shadow: none;
    padding: 14px 16px 16px;
    box-sizing: border-box;
  }
  .pead-card .pead-section { width: 100%; }
  .q-panel { overflow-x: auto; padding: 4px 0 2px; }
  .q-table { width: 100%; border-collapse: collapse; min-width: 480px; font-size: 11px; }
  .q-table th, .q-table td {
    padding: 4px 8px;
    border: 1px solid var(--border);
    text-align: right;
    white-space: nowrap;
  }
  .q-table th:first-child, .q-table td.q-label {
    text-align: left;
    font-weight: 600;
    color: var(--text);
    min-width: 120px;
    position: sticky;
    left: 0;
    background: var(--panel);
    z-index: 1;
  }
  .q-table th { color: var(--muted); font-size: 10px; text-transform: uppercase; background: var(--thead); }
  .q-table th.q-recent, .q-table td.q-recent { background: rgba(37, 99, 235, 0.08); }
  .pead-card .q-table th.q-latest,
  .pead-card .q-table td.q-latest {
    background: rgba(34, 197, 94, 0.14);
    font-weight: 700;
  }
  [data-theme="dark"] .q-table th.q-recent,
  [data-theme="dark"] .q-table td.q-recent { background: rgba(88, 166, 255, 0.12); }
  .q-table td.q-up { color: var(--green); font-weight: 700; }
  .q-table td.q-down { color: var(--red); font-weight: 700; }
  .q-table td.q-flat { color: var(--muted); }
  .pead-empty { color: var(--muted); font-size: 12px; padding: 8px 4px; }
  .pead-card {
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    padding: 16px 18px 14px;
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
    gap: 0;
    width: 100%;
    max-width: none;
    box-sizing: border-box;
  }
  .pead-card.pead-card-compact {
    padding: 10px 12px 8px;
    border-radius: 8px;
    gap: 8px;
  }
  .pead-hero {
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 14px;
  }
  .pead-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }
  .pead-top-left { min-width: 0; flex: 1; }
  .pead-top-right {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 6px;
    flex-shrink: 0;
  }
  .pead-capline {
    font-size: 11px;
    color: var(--muted);
    font-weight: 500;
    white-space: nowrap;
    text-align: right;
  }
  .pead-capline-below {
    margin-top: 6px;
    line-height: 1.3;
  }
  .pead-capline-below .pead-cap-label {
    font-size: 11px;
    font-weight: 500;
    color: var(--muted);
  }
  .pead-capline-below .pead-cap-val {
    font-size: 16px;
    font-weight: 700;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .pead-ema-line {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 5px;
    font-size: 11px;
    font-weight: 600;
  }
  .pead-ema-line.pead-ema-good { color: var(--green); }
  .pead-ema-line.pead-ema-warn { color: var(--amber); }
  .pead-ema-detail {
    font-size: 10px;
    font-weight: 500;
    color: var(--muted);
  }
  .pead-hero-compact .pead-top-right {
    justify-content: flex-start;
  }
  .pead-about { margin-top: 10px; }
  .pead-section {
    padding: 14px 0;
    border-bottom: 1px solid var(--border);
  }
  .pead-section:last-child { border-bottom: none; padding-bottom: 0; }
  .pead-section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
  }
  .pead-section-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.01em;
    margin-bottom: 10px;
  }
  .pead-section-head .pead-section-title { margin-bottom: 0; }
  .pead-card .pead-range-section {
    padding: 8px 0 10px;
    max-width: 340px;
  }
  .pead-card .pead-range-section .pead-section-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .pead-card .pead-range-section .range-wrap { margin-top: 0; }
  .pead-card .pead-range-section .range-ends {
    font-size: 10px;
    font-weight: 700;
    margin-bottom: 4px;
  }
  .pead-card .pead-range-section .range-track {
    height: 5px;
  }
  .pead-card .pead-range-section .range-thumb {
    width: 10px;
    height: 10px;
    margin-top: -5px;
    margin-left: -5px;
    border-width: 1.5px;
  }
  .pead-trend-chart {
    display: block;
    width: 100%;
    height: 88px;
    margin-bottom: 8px;
  }
  .pead-trend-line {
    fill: none;
    stroke: var(--accent);
    stroke-width: 2;
    stroke-linejoin: round;
    stroke-linecap: round;
  }
  .pead-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 14px;
    font-size: 11px;
    color: var(--muted);
  }
  .pead-legend-item { display: inline-flex; align-items: center; gap: 5px; }
  .pead-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .pead-dot.up { background: var(--green); }
  .pead-dot.down { background: var(--red); }
  .pead-news-block .pead-section-title { margin-bottom: 8px; }
  .pead-news-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 8px 10px;
    align-items: start;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
  }
  .pead-news-row:last-child { border-bottom: none; padding-bottom: 0; }
  .pead-sent {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 999px;
    white-space: nowrap;
    line-height: 1.4;
  }
  .pead-sent.sent-pos { color: #166534; background: rgba(34, 197, 94, 0.18); }
  .pead-sent.sent-neu { color: #57534e; background: rgba(120, 113, 108, 0.15); }
  .pead-news-link {
    font-size: 12px;
    font-weight: 600;
    color: var(--text);
    text-decoration: none;
    line-height: 1.35;
  }
  .pead-news-link:hover { color: var(--link); text-decoration: underline; }
  .pead-news-when {
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
  }
  .pead-card .q-block-title {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: -0.01em;
    text-transform: none;
    color: var(--text);
    margin-bottom: 10px;
  }
  .pead-card .q-panel { padding: 0; overflow-x: auto; }
  .pead-card .q-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    min-width: 0;
    font-size: 12px;
    table-layout: auto;
  }
  .pead-card .q-table th,
  .pead-card .q-table td {
    padding: 9px 12px;
    border: none;
    border-bottom: 1px solid var(--border);
    text-align: right;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    vertical-align: middle;
  }
  .pead-card .q-table thead th {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
    background: transparent;
    border-bottom: 1px solid var(--border);
    padding-top: 0;
  }
  .pead-card .q-table tbody tr:last-child td {
    border-bottom: none;
  }
  .pead-card .q-table th:first-child,
  .pead-card .q-table td.q-label {
    text-align: left;
    font-weight: 600;
    color: var(--muted);
    min-width: 108px;
    position: static;
    background: transparent;
  }
  .pead-card .q-table td.q-label {
    color: var(--text);
    font-weight: 500;
  }
  .pead-card .q-table th.q-recent,
  .pead-card .q-table td.q-recent {
    background: transparent;
  }
  .pead-card .q-table th.q-latest,
  .pead-card .q-table td.q-latest {
    background: rgba(34, 197, 94, 0.1);
    font-weight: 700;
  }
  [data-theme="dark"] .pead-card .q-table th.q-latest,
  [data-theme="dark"] .pead-card .q-table td.q-latest {
    background: rgba(34, 197, 94, 0.14);
  }
  .pead-card .q-table td.q-up {
    color: var(--green);
    font-weight: 700;
    background: rgba(34, 197, 94, 0.08);
  }
  .pead-card .q-table td.q-down {
    color: var(--red);
    font-weight: 700;
    background: rgba(239, 68, 68, 0.08);
  }
  .pead-card .q-table td.q-flat {
    color: var(--muted);
    background: transparent;
  }
  .pead-card .q-table td.q-latest.q-up {
    background: rgba(34, 197, 94, 0.16);
  }
  .pead-card .q-table td.q-latest.q-down {
    background: rgba(239, 68, 68, 0.12);
  }
  .pead-detail {
    display: flex;
    flex-direction: column;
    gap: 12px;
    width: 100%;
  }
  .pead-detail-hero {
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--panel);
    padding: 14px 16px 12px;
    box-shadow: var(--shadow);
  }
  .pead-detail-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }
  .pead-detail-titleblk { min-width: 0; flex: 1; }
  .pead-detail-name {
    font-size: 16px;
    font-weight: 700;
    line-height: 1.25;
    letter-spacing: -0.02em;
    color: var(--text);
  }
  .pead-detail-sub {
    font-size: 12px;
    font-weight: 700;
    color: var(--text);
    margin-top: 0;
    line-height: 1.35;
  }
  .pead-detail-subsector {
    font-size: 11px;
    color: var(--muted);
    line-height: 1.35;
    margin-top: 2px;
  }
  .pead-holdings-head {
    padding: 0 0 12px;
    margin-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }
  .pead-holdings-head .pead-detail-name {
    margin-bottom: 4px;
  }
  .pead-detail-links {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 12px;
    margin-top: 6px;
  }
  .pead-detail-web .co-website { font-size: 11px; }
  .pead-score-ring { flex-shrink: 0; color: var(--border); }
  .pead-score-ring-txt {
    fill: var(--text);
    font-size: 13px;
    font-weight: 700;
    font-family: "JetBrains Mono", ui-monospace, monospace;
  }
  .pead-detail-price-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 10px;
  }
  .pead-detail-price {
    font-size: 26px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.03em;
    line-height: 1;
  }
  .pead-chip {
    font-size: 12px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    padding: 2px 7px;
    border-radius: 6px;
  }
  .pead-chip.pos { color: var(--green); background: rgba(34, 197, 94, 0.12); }
  .pead-chip.neg { color: var(--red); background: rgba(239, 68, 68, 0.12); }
  .pead-detail-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(88px, 1fr));
    gap: 8px 12px;
  }
  .pead-metric { min-width: 0; }
  .pead-metric-lbl {
    display: block;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 2px;
  }
  .pead-metric-val {
    font-size: 13px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }
  .pead-metric-val.pos { color: var(--green); }
  .pead-metric-val.neg { color: var(--red); }
  .pead-metric-date { font-size: 11px; font-weight: 600; color: var(--muted); }
  .pead-detail-about {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
  }
  .pead-detail-grid {
    display: grid;
    grid-template-columns: minmax(200px, 240px) minmax(0, 1fr);
    gap: 12px;
    align-items: start;
  }
  @media (max-width: 900px) {
    .pead-detail-grid { grid-template-columns: 1fr; }
  }
  .pead-detail-side {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .pead-side-card {
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    padding: 10px 12px 12px;
  }
  .pead-detail-main {
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel);
    padding: 10px 12px 12px;
    min-width: 0;
  }
  .pead-detail-main.solo { width: 100%; }
  .q-block-title {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 8px;
  }
  .pead-detail-foot .expand-detail-stack { margin-top: 0; }
  .expand-hint { color: var(--muted); font-size: 10px; margin-left: 6px; }
  tr.pead-row.expanded .expand-hint::after { content: "▴"; }
  tr.pead-row:not(.expanded) .expand-hint::after { content: "▾"; }
  .expand-body.expand-pead {
    display: block;
    width: 100%;
  }
  .expand-main {
    min-width: 0;
    width: 100%;
  }
  .expand-detail-stack {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    margin-top: 8px;
    width: 100%;
    align-items: start;
  }
  @media (max-width: 960px) {
    .expand-detail-stack { grid-template-columns: 1fr; }
  }
  .expand-info-card {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--panel);
    padding: 8px 10px 10px;
    min-width: 0;
  }
  .expand-info-card.profile { border-left: 3px solid var(--accent); }
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
    color: var(--muted);
  }
  .expand-card-action {
    font-size: 10px;
    font-weight: 600;
    color: var(--link);
    text-decoration: none;
    white-space: nowrap;
  }
  .expand-card-action:hover { text-decoration: underline; }
  .expand-info-card .co-profile {
    margin: 0;
    padding: 0;
    border-top: none;
    gap: 5px;
  }
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
    border-bottom: 1px solid var(--border);
  }
  .co-news-item:last-child { border-bottom: none; }
  .co-news-meta {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: 2px;
    font-size: 9px;
    color: var(--muted);
  }
  .co-news-tag {
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--link);
    background: var(--accent-soft);
    padding: 1px 5px;
    border-radius: 999px;
  }
  .co-news-link {
    font-size: 11px;
    line-height: 1.35;
    color: var(--text);
    text-decoration: none;
    font-weight: 600;
  }
  .co-news-link:hover { color: var(--link); text-decoration: underline; }
  .expand-wrap { display: flex; flex-direction: column; gap: 14px; width: 100%; }
  .note-stack {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 10px;
    width: 100%;
  }
  .note-card {
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--panel);
    padding: 12px 14px;
    line-height: 1.45;
    font-size: 12px;
    box-shadow: var(--shadow);
  }
  .note-card.business { border-left: 4px solid var(--accent); }
  .note-card.market { border-left: 4px solid var(--green); }
  .note-card.triggers { border-left: 4px solid var(--amber); }
  .note-title {
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 6px;
  }
  .note-body { color: var(--text); white-space: pre-wrap; }
  .note-list { margin: 0; padding-left: 18px; color: var(--text); }
  .note-list li { margin-bottom: 4px; }
  .note-list li:last-child { margin-bottom: 0; }
  .note-source {
    grid-column: 1 / -1;
    margin-top: 2px;
    font-size: 10px;
    color: var(--muted);
    font-style: italic;
  }
  .snap-panel {
    min-width: 220px;
    max-width: 300px;
    font-size: 11px;
    line-height: 1.3;
  }
  .snap-metrics {
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px 12px;
    margin-bottom: 8px;
  }
  .snap-metric {
    display: inline-flex;
    align-items: baseline;
    gap: 6px;
    white-space: nowrap;
  }
  .snap-metric-label {
    font-size: 12px;
    color: var(--muted);
    font-weight: 500;
  }
  .snap-metric-val {
    font-size: 14px;
    font-weight: 700;
    color: var(--text);
    font-variant-numeric: tabular-nums;
  }
  .snap-metric-val.pos { color: var(--green); }
  .snap-metric-val.neg { color: var(--red); }
  .snap-class {
    font-size: 11px;
    color: var(--muted);
    line-height: 1.35;
    margin: -6px 0 12px;
    word-break: break-word;
  }
  .snap-class-sep { margin: 0 5px; opacity: 0.5; }
  .co-profile {
    margin: 12px 0 0;
    padding: 12px 0 0;
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .co-profile-website { line-height: 1.35; }
  .co-website {
    color: var(--link);
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
    font-size: 11px;
    line-height: 1.45;
    color: var(--muted);
    word-break: break-word;
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
    font-size: 12px;
    line-height: 1.55;
    color: var(--text);
    opacity: 0.88;
    white-space: pre-wrap;
    word-break: break-word;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
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
    color: var(--link);
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
    color: var(--muted);
    margin-bottom: 8px;
  }
  .ma-pills {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .ma-pill {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: #f8fafc;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  .ma-pill .ma-period {
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    min-width: 22px;
    text-align: center;
  }
  .ma-pill .ma-val {
    font-weight: 700;
    font-size: 12px;
    color: var(--text);
    margin-left: auto;
  }
  .ma-pill.above {
    border-color: rgba(5, 150, 105, 0.45);
    background: rgba(5, 150, 105, 0.12);
  }
  .ma-pill.below {
    border-color: rgba(220, 38, 38, 0.4);
    background: rgba(220, 38, 38, 0.1);
  }
  .ma-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    font-size: 11px;
    font-weight: 800;
    line-height: 1;
    flex-shrink: 0;
  }
  .ma-icon.up { color: var(--green); }
  .ma-icon.down { color: var(--red); }
  .pead-main-row {
    display: flex;
    align-items: flex-start;
    gap: 12px 18px;
    width: 100%;
  }
  .pead-main-row .pead-metrics-card {
    flex: 0 0 min(380px, 38%);
    max-width: 400px;
    min-width: 260px;
  }
  .pead-main-row .pead-q-section {
    flex: 1 1 280px;
    min-width: 0;
    padding: 0 !important;
    border-top: none !important;
    overflow-x: auto;
  }
  .pead-card-compact .pead-q-section .q-block {
    border: 1px solid rgba(148, 163, 184, 0.32);
    border-radius: 8px;
    padding: 8px 10px 6px;
    background: rgba(248, 250, 252, 0.55);
  }
  [data-theme="dark"] .pead-card-compact .pead-q-section .q-block {
    border-color: rgba(148, 163, 184, 0.22);
    background: rgba(15, 23, 42, 0.35);
  }
  .pead-card-compact .pead-q-section .q-table th,
  .pead-card-compact .pead-q-section .q-table td {
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  }
  .pead-card-compact .pead-q-section .q-table thead th {
    border-bottom: 1px solid rgba(148, 163, 184, 0.28);
  }
  .pead-card-compact .pead-q-section .q-table tbody tr:last-child td {
    border-bottom: none;
  }
  .pead-main-row .q-panel {
    overflow-x: auto;
  }
  @media (max-width: 720px) {
    .pead-main-row {
      flex-direction: column;
    }
    .pead-main-row .pead-metrics-card {
      flex: 1 1 auto;
      max-width: none;
      width: 100%;
    }
    .pead-main-row .pead-q-section {
      width: 100%;
      border-top: 1px solid var(--border) !important;
      padding-top: 8px !important;
    }
  }
  .pead-metrics-card {
    margin-top: 0;
    width: 100%;
    font-size: 11px;
    line-height: 1.25;
  }
  .pead-panel-sub {
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    margin-bottom: 6px;
    line-height: 1.3;
  }
  .pead-metrics-card .snap-metrics {
    margin-bottom: 8px;
    gap: 6px 14px;
  }
  .pead-metrics-card .snap-metric {
    gap: 4px;
  }
  .pead-metrics-card .snap-metric-label {
    font-size: 11px;
  }
  .pead-metrics-card .snap-metric-val {
    font-size: 14px;
  }
  .pead-metrics-card .snap-metric .pead-chip {
    margin-left: 4px;
    font-size: 9px;
    padding: 1px 5px;
  }
  .pead-metrics-card .snap-section-tight {
    margin-top: 8px;
  }
  .pead-metrics-card .snap-label {
    margin-bottom: 5px;
    font-size: 9px;
  }
  .pead-ma-pills {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 5px;
  }
  .pead-ma-pills .ma-pill {
    padding: 4px 7px;
    gap: 4px;
    border-radius: 6px;
  }
  .pead-ma-pills .ma-pill .ma-period {
    font-size: 10px;
    min-width: 18px;
  }
  .pead-ma-pills .ma-pill .ma-val {
    font-size: 10px;
    font-weight: 700;
  }
  .pead-ma-pills .ma-icon {
    width: 11px;
    height: 11px;
    font-size: 9px;
  }
  .pead-ma-pills .ma-pill:nth-child(4) {
    grid-column: 1;
  }
  .pead-metrics-card .range-ends {
    font-size: 10px;
    margin-bottom: 4px;
  }
  .pead-metrics-card .range-track {
    height: 5px;
  }
  .pead-metrics-card .range-thumb {
    width: 10px;
    height: 10px;
    margin-top: -5px;
    margin-left: -5px;
    border-width: 1.5px;
  }
  .pead-insight-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 10px 14px;
    padding: 8px 0 0;
    border-top: 1px solid var(--border);
  }
  .pead-insight-row.single {
    grid-template-columns: 1fr;
  }
  .pead-insight-label {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 5px;
  }
  .pead-insight-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    margin-bottom: 5px;
  }
  .pead-insight-head .pead-insight-label {
    margin-bottom: 0;
  }
  .pead-insight-head .expand-card-action {
    font-size: 10px;
  }
  .pead-about-desc {
    font-size: 11px;
    line-height: 1.45;
    -webkit-line-clamp: 2;
  }
  .pead-insight-about .co-profile-more {
    font-size: 10px;
    margin-top: 2px;
  }
  .pead-news-compact-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .pead-news-compact-row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 6px 8px;
    align-items: start;
    padding: 4px 0;
    text-decoration: none;
    color: inherit;
    border-radius: 4px;
  }
  .pead-news-compact-row:hover .pead-news-compact-title {
    color: var(--link);
    text-decoration: underline;
  }
  .pead-news-compact-title {
    font-size: 11px;
    font-weight: 600;
    line-height: 1.35;
    color: var(--text);
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
  }
  .pead-insight-row .pead-sent {
    font-size: 8px;
    padding: 1px 5px;
  }
  .pead-insight-row .pead-news-when {
    font-size: 9px;
  }
  .pead-q-section {
    padding: 4px 0 8px !important;
    border-top: 1px solid var(--border);
    border-bottom: none !important;
  }
  .pead-card-compact .q-block-title {
    font-size: 11px;
    margin-bottom: 6px;
  }
  .pead-card-compact .q-table th,
  .pead-card-compact .q-table td {
    padding: 5px 8px;
    font-size: 11px;
  }
  .pead-card-compact .q-table thead th {
    font-size: 9px;
    padding-bottom: 4px;
  }
  .range-wrap { margin-top: 2px; }
  .range-ends {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    font-weight: 700;
    margin-bottom: 8px;
    font-variant-numeric: tabular-nums;
  }
  .range-low { color: var(--red); }
  .range-high { color: var(--green); }
  .range-track {
    position: relative;
    height: 8px;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--red) 0%, #fbbf24 50%, var(--green) 100%);
  }
  .range-thumb {
    position: absolute;
    top: 50%;
    width: 14px;
    height: 14px;
    margin-top: -7px;
    margin-left: -7px;
    border-radius: 50%;
    background: #4f46e5;
    border: 2px solid #fff;
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.3);
  }
  #pead-table td.pead-expand-td .pead-q-table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    min-width: 0;
    font-size: 12px;
  }
  #pead-table td.pead-expand-td .pead-q-section .q-block {
    border: 1px solid rgba(148, 163, 184, 0.32);
    border-radius: 8px;
    padding: 8px 10px 6px;
    background: rgba(248, 250, 252, 0.55);
  }
  [data-theme="dark"] #pead-table td.pead-expand-td .pead-q-section .q-block {
    border-color: rgba(148, 163, 184, 0.22);
    background: rgba(15, 23, 42, 0.35);
  }
  #pead-table td.pead-expand-td .pead-q-table th,
  #pead-table td.pead-expand-td .pead-q-table td {
    border: none;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    padding: 7px 12px;
    text-align: right;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
    vertical-align: middle;
    background: transparent;
    position: static;
  }
  [data-theme="dark"] #pead-table td.pead-expand-td .pead-q-table th,
  [data-theme="dark"] #pead-table td.pead-expand-td .pead-q-table td {
    border-bottom-color: rgba(148, 163, 184, 0.16);
  }
  #pead-table td.pead-expand-td .pead-q-table thead th {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
    background: transparent;
    border-bottom: 1px solid rgba(148, 163, 184, 0.28);
    padding: 0 12px 8px;
  }
  #pead-table td.pead-expand-td .pead-q-table tbody tr:last-child td {
    border-bottom: none;
  }
  #pead-table td.pead-expand-td .pead-q-table th:first-child,
  #pead-table td.pead-expand-td .pead-q-table td.q-label {
    width: 18%;
    text-align: left;
    font-weight: 500;
    color: var(--text);
  }
  #pead-table td.pead-expand-td .pead-q-table th.q-latest,
  #pead-table td.pead-expand-td .pead-q-table td.q-latest {
    background: rgba(34, 197, 94, 0.1);
    font-weight: 700;
  }
  #pead-table td.pead-expand-td .pead-q-table td.q-up {
    color: var(--green);
    font-weight: 700;
    background: rgba(34, 197, 94, 0.08);
  }
  #pead-table td.pead-expand-td .pead-q-table td.q-down {
    color: var(--red);
    font-weight: 700;
    background: rgba(239, 68, 68, 0.08);
  }
  #pead-table td.pead-expand-td .pead-q-table td.q-flat {
    color: var(--muted);
    background: transparent;
  }
  #pead-table td.pead-expand-td .pead-q-table td.q-latest.q-up {
    background: rgba(34, 197, 94, 0.14);
  }
  #pead-table td.pead-expand-td .pead-q-table td.q-latest.q-down {
    background: rgba(239, 68, 68, 0.12);
  }
  #pead-table td.pead-expand-td .q-panel {
    width: 100%;
    padding: 0;
    overflow: visible;
  }
</style>
"""


def format_generated_ist(dt: datetime | str | None = None) -> str:
    """Format timestamp like FinanciallyFree: Generated YYYY-MM-DD HH:MM IST."""
    if dt is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(dt, str):
        parsed = pd.Timestamp(dt).to_pydatetime()
    else:
        parsed = dt
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZoneInfo("Asia/Kolkata")).strftime(
        "Generated %Y-%m-%d %H:%M IST"
    )


def _scan_generated_ist(df: pd.DataFrame) -> str:
    if df.empty or "calculation_date" not in df.columns:
        return format_generated_ist()
    series = df["calculation_date"].dropna()
    if series.empty:
        return format_generated_ist()
    return format_generated_ist(str(series.iloc[0]))


def _pead_fmt_pct(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        n = float(val)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if n > 0 else ""
    return f"{sign}{n:.1f}%"


def _pead_fmt_num1(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        return f"{float(val):.1f}"
    except (TypeError, ValueError):
        return "—"


def _pead_fmt_date_short(val) -> str:
    s = safe_str(val)
    if not s:
        return "—"
    try:
        return pd.Timestamp(s).strftime("%d %b")
    except Exception:
        return s[:10]


def _pead_score_tier(score, high_min: float) -> str:
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return "mid"
    try:
        n = float(score)
    except (TypeError, ValueError):
        return "mid"
    if n > high_min:
        return "high"
    if n < 0 or n <= high_min * 0.35:
        return "low"
    return "mid"


def _pead_fnum(val) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None
    if pd.isna(n):
        return None
    return n


def _pead_fwd_pe_quality(pe: float | None) -> str:
    """good / mid / bad / missing — aligned with PEAD table Fwd PE coloring."""
    n = _pead_fnum(pe)
    if n is None or n <= 0 or n >= 500:
        return "missing"
    if n > 40:
        return "bad"
    if n > 20:
        return "mid"
    return "good"


def _pead_pick_quality(
    row: pd.Series,
    *,
    high_min: float,
    is_psq: bool = False,
) -> str:
    """
    Strong / soft / caution / watch — EarningsQ-style badge for top cards.

    Strong prefers high score + sensible Fwd PE + cooperating returns.
    Caution = high score but rich Fwd PE or fading price.
    """
    score = _pead_fnum(row.get("pead_score"))
    fpe = _pead_fnum(row.get("forward_pe"))
    returns = _pead_fnum(row.get("returns_pct"))
    daily = _pead_fnum(row.get("daily_ret_pct"))
    sales = _pead_fnum(row.get("sales_yoy"))
    np_y = _pead_fnum(row.get("np_yoy"))
    pe_q = _pead_fwd_pe_quality(fpe)

    if score is None:
        return "watch"
    if score > high_min and (
        pe_q == "bad"
        or (returns is not None and returns < -5 and (daily is None or daily < 0))
    ):
        return "caution"
    if is_psq:
        surprise = _pead_fnum(row.get("surprise_growth"))
        peg = _pead_fnum(row.get("peg"))
        if (
            score > high_min
            and surprise is not None
            and surprise > 0
            and (peg is None or 0 < peg <= 2.0)
            and (returns is None or returns >= -2)
        ):
            return "strong"
        if score > high_min * 0.7:
            return "soft"
        return "watch"

    growth_ok = (sales is None or sales > -10) and (np_y is None or np_y > -5)
    pe_ok = pe_q in {"good", "mid"}
    price_ok = (returns is None or returns >= -2) and (daily is None or daily >= -3)
    if score > high_min and pe_ok and growth_ok and price_ok:
        return "strong"
    if score > high_min:
        return "soft"
    return "watch"


def _pead_pick_rank(
    row: pd.Series,
    *,
    high_min: float,
    is_psq: bool = False,
) -> float:
    """Blend rank so Top picks prefer quality Fwd PE, not score alone."""
    score = _pead_fnum(row.get("pead_score")) or 0.0
    fpe = _pead_fnum(row.get("forward_pe"))
    returns = _pead_fnum(row.get("returns_pct")) or 0.0
    daily = _pead_fnum(row.get("daily_ret_pct")) or 0.0
    pe_q = _pead_fwd_pe_quality(fpe)

    # Fwd PE: prefer good (≤20) and mid (≤40); penalize rich / missing.
    if pe_q == "good":
        pe_bonus = 12.0
    elif pe_q == "mid":
        pe_bonus = 10.0
    elif pe_q == "bad":
        pe_bonus = -12.0
    else:
        pe_bonus = -6.0

    price_bonus = max(-8.0, min(8.0, returns * 0.15 + daily * 0.2))
    tech_bonus = 0.0
    if json_safe_bool(row.get("has_tq")):
        tech_bonus += 3.0
    if json_safe_bool(row.get("has_bb")) and safe_str(row.get("bb_signal")).upper() == "NEW_BREAKOUT":
        tech_bonus += 3.0

    quality = _pead_pick_quality(row, high_min=high_min, is_psq=is_psq)
    tag_bonus = {"strong": 8.0, "soft": 2.0, "caution": -6.0, "watch": 0.0}.get(quality, 0.0)

    if is_psq:
        surprise = _pead_fnum(row.get("surprise_growth")) or 0.0
        peg = _pead_fnum(row.get("peg"))
        peg_bonus = 4.0 if peg is not None and 0 < peg <= 1.5 else (0.0 if peg is None else -4.0)
        return round(score + surprise * 0.15 + peg_bonus + price_bonus + tech_bonus + tag_bonus, 3)

    return round(score + pe_bonus + price_bonus + tech_bonus + tag_bonus, 3)


def _pead_fmt_fpe_html(val) -> str:
    txt = _pead_fmt_num1(val)
    if txt == "—":
        return '<span class="pead-fpe missing">—</span>'
    q = _pead_fwd_pe_quality(_pead_fnum(val))
    return f'<span class="pead-fpe {q}">{html.escape(txt)}</span>'


def _pead_pick_card(row: pd.Series, *, variant: str, high_min: float) -> str:
    ticker = safe_str(row.get("ticker")).upper()
    market = safe_str(row.get("market")) or "NSE"
    sc_url, tv_url = research_links(ticker, market)
    name = html.escape(safe_str(row.get("name")) or ticker)
    score = row.get("pead_score")
    tier = _pead_score_tier(score, high_min)
    score_txt = (
        f"{float(score):.1f}"
        if score is not None and not (isinstance(score, float) and pd.isna(score))
        else "—"
    )
    is_psq = str(variant).lower() in (
        "psq",
        "positive_surprise",
        "positive_surprise_quant",
    )
    score_lbl = "PSQ" if is_psq else "PEAD"
    quality = _pead_pick_quality(row, high_min=high_min, is_psq=is_psq)
    badge_labels = {
        "strong": "Strong",
        "soft": "Soft",
        "caution": "Caution",
        "watch": "Watch",
    }
    badge = (
        f'<span class="pead-pick-badge {quality}">'
        f'{badge_labels.get(quality, "Watch")}</span>'
    )
    if is_psq:
        stats = (
            ("Surprise", html.escape(_pead_fmt_pct(row.get("surprise_growth")))),
            ("PEG", html.escape(_pead_fmt_num1(row.get("peg")))),
            ("Fwd PE", _pead_fmt_fpe_html(row.get("forward_pe"))),
            ("Returns", html.escape(_pead_fmt_pct(row.get("returns_pct")))),
        )
    else:
        stats = (
            ("Fwd PE", _pead_fmt_fpe_html(row.get("forward_pe"))),
            ("Returns", html.escape(_pead_fmt_pct(row.get("returns_pct")))),
            ("Sales YoY", html.escape(_pead_fmt_pct(row.get("sales_yoy")))),
            ("Daily", html.escape(_pead_fmt_pct(row.get("daily_ret_pct")))),
        )
    chips: list[str] = []
    if json_safe_bool(row.get("has_tq")):
        chips.append('<span class="pead-pick-chip tq">TQ</span>')
    if json_safe_bool(row.get("has_bb")) and safe_str(row.get("bb_signal")).upper() == "NEW_BREAKOUT":
        chips.append('<span class="pead-pick-chip bb">BB NEW</span>')
    pe_q = _pead_fwd_pe_quality(_pead_fnum(row.get("forward_pe")))
    if pe_q == "good":
        chips.append('<span class="pead-pick-chip pe-good">PE ok</span>')
    elif pe_q == "bad":
        chips.append('<span class="pead-pick-chip pe-bad">Rich PE</span>')
    chips_html = (
        f'<div class="pead-pick-chips">{"".join(chips)}</div>' if chips else ""
    )
    stats_html = "".join(
        f'<div class="pead-pick-stat"><span>{html.escape(lbl)}</span>'
        f"<b>{val}</b></div>"
        for lbl, val in stats
    )
    return f"""
    <div class="pead-pick {tier} {quality}" data-ticker="{html.escape(ticker)}" title="Click to expand row">
      <div class="pead-pick-top">
        <div>
          <a class="pead-pick-ticker" href="{html.escape(tv_url)}" target="_blank" rel="noopener noreferrer"
             onclick="event.stopPropagation()">{html.escape(ticker)}</a>
          <div class="pead-pick-name">{name}</div>
          {chips_html}
        </div>
        <div class="pead-pick-scoreblk">
          {badge}
          <div class="pead-pick-score {tier}">{html.escape(score_txt)}</div>
          <div class="pead-pick-score-lbl">{score_lbl}</div>
        </div>
      </div>
      <div class="pead-pick-stats">{stats_html}</div>
      <div class="pead-pick-links">
        <a href="{html.escape(sc_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">SC</a>
        <a href="{html.escape(tv_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">TV</a>
        <span class="pead-pick-date">{html.escape(_pead_fmt_date_short(row.get("result_date")))}</span>
      </div>
    </div>
    """


def _build_top_picks_html(
    df: pd.DataFrame,
    *,
    variant: str = "pead2",
    high_min: float = 40.0,
    top_n: int = 8,
) -> str:
    if df is None or df.empty or "pead_score" not in df.columns:
        return ""
    work = df.copy()
    work["_score"] = pd.to_numeric(work["pead_score"], errors="coerce")
    work = work[work["_score"].notna()].copy()
    if work.empty:
        return ""
    is_psq = str(variant).lower() in (
        "psq",
        "positive_surprise",
        "positive_surprise_quant",
    )
    work["_pick_rank"] = work.apply(
        lambda r: _pead_pick_rank(r, high_min=high_min, is_psq=is_psq),
        axis=1,
    )
    work["_quality"] = work.apply(
        lambda r: _pead_pick_quality(r, high_min=high_min, is_psq=is_psq),
        axis=1,
    )
    work["_pe_q"] = work.apply(
        lambda r: _pead_fwd_pe_quality(_pead_fnum(r.get("forward_pe"))),
        axis=1,
    )
    # Prefer score > threshold + Fwd PE good/mid (≤ 40); rich PE only as filler.
    high = work[work["_score"] > float(high_min)].copy()
    pe_ok = high["_pe_q"].isin(["good", "mid"])
    strong = high[(high["_quality"] == "strong") & pe_ok].sort_values(
        "_pick_rank", ascending=False
    )
    soft_ok = high[(high["_quality"] != "strong") & pe_ok].sort_values(
        "_pick_rank", ascending=False
    )
    rich = high[~pe_ok].sort_values("_pick_rank", ascending=False)
    pool = pd.concat([strong, soft_ok, rich], ignore_index=True)
    if pool.empty:
        pool = work.sort_values("_pick_rank", ascending=False)
    picks = pool.head(top_n)
    label = "Top surprises" if is_psq else "Top picks"
    strong_n = int((picks["_quality"] == "strong").sum()) if len(picks) else 0
    pe_ok_n = int(picks["_pe_q"].isin(["good", "mid"]).sum()) if len(picks) else 0
    if strong_n:
        meta = (
            f"{len(picks)} names · {strong_n} strong · "
            f"score &gt; {high_min:.0f} · Fwd PE good/mid (≤ 40)"
        )
    elif pe_ok_n:
        meta = (
            f"{len(picks)} names · score &gt; {high_min:.0f} · "
            f"Fwd PE good/mid preferred"
        )
    elif len(high):
        meta = (
            f"{len(picks)} names · score &gt; {high_min:.0f} · "
            f"ranked by score + Fwd PE + returns"
        )
    else:
        meta = f"{len(picks)} names · ranked by score + Fwd PE"
    cards = "".join(
        _pead_pick_card(r, variant=variant, high_min=high_min)
        for _, r in picks.iterrows()
    )
    if not cards:
        return '<div class="pead-picks-empty">No scored names in this scan.</div>'
    return (
        f'<div class="pead-section-label">{html.escape(label)} · {meta}</div>'
        f'<div class="pead-picks">{cards}</div>'
        '<div class="pead-picks-empty pead-picks-empty-filter" style="display:none">'
        "No top picks match this filter."
        "</div>"
    )


from stocks.core.json_utils import json_dumps, json_safe_bool, json_safe_obj, json_safe_scalar
from stocks.market.google_news import attach_google_news_to_rows


def _json_script_tag(tag_id: str, obj) -> str:
    """Safe JSON in HTML — escape ``<`` so ``</script>`` in data cannot break the page."""
    payload = json_dumps(obj, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c")
    return f'<script type="application/json" id="{html.escape(tag_id)}">{payload}</script>'


def limit_pead_report_df(
    df: pd.DataFrame,
    max_rows: int | None,
) -> tuple[pd.DataFrame, int]:
    """Return (report slice, universe total) sorted by latest result / score."""
    total = len(df)
    if df is None or df.empty or not max_rows or total <= max_rows:
        return df if df is not None else pd.DataFrame(), total
    work = df.copy()
    sort_cols = [c for c in ("result_date", "pead_score") if c in work.columns]
    if sort_cols:
        work = work.sort_values(
            sort_cols,
            ascending=[False] * len(sort_cols),
            na_position="last",
        )
    return work.head(max_rows).reset_index(drop=True), total


def _slim_snapshot(snapshot: dict | None) -> dict:
    if not isinstance(snapshot, dict):
        return {}
    return {k: snapshot[k] for k in _SNAPSHOT_SLIM_KEYS if k in snapshot}


def _split_row_payload(
    row_data: dict,
    *,
    expand_keys: frozenset[str] | None = None,
) -> tuple[dict, dict]:
    """Table row vs heavy expand-panel fields (keeps iframe payload small)."""
    keys = expand_keys or _EXPAND_PAYLOAD_KEYS
    table = dict(row_data)
    expand: dict = {}
    # Always strip heavy fields from the table row — even if not embedded in expand.
    for key in _EXPAND_PAYLOAD_KEYS:
        if key not in table:
            continue
        val = table.pop(key)
        if key not in keys:
            continue
        if key == "snapshot":
            val = _slim_snapshot(val if isinstance(val, dict) else None)
        if val:
            expand[key] = val
    return table, expand


def _table_and_expand_rows(
    df: pd.DataFrame,
    *,
    include_news: bool = True,
    slim_expand: bool = False,
) -> tuple[list[dict], dict[str, dict]]:
    full = _rows_for_json(df, include_news=include_news)
    expand_keys = _EXPAND_KEYS_LARGE if slim_expand else _EXPAND_PAYLOAD_KEYS
    table_rows: list[dict] = []
    expand_by_ticker: dict[str, dict] = {}
    for row in full:
        table, expand = _split_row_payload(row, expand_keys=expand_keys)
        table_rows.append(table)
        ticker = safe_str(table.get("ticker")).upper()
        if ticker and expand:
            expand_by_ticker[ticker] = expand
    return table_rows, expand_by_ticker


def _rows_for_json(df: pd.DataFrame, *, include_news: bool = True) -> list[dict]:
    sync_stock_notes_from_file()
    work = attach_stock_notes(df, sync_file=False)
    ss_map = superstar_pead_map(
        work["ticker"].astype(str).str.strip().str.upper().unique().tolist()
        if not work.empty and "ticker" in work.columns
        else []
    )
    mcap_map: dict[str, float] = {}
    if not work.empty and "ticker" in work.columns:
        tickers = work["ticker"].astype(str).str.strip().str.upper().unique().tolist()
        mcap_df = load_market_cap_from_db(tickers)
        if not mcap_df.empty:
            mcap_map = {
                safe_str(t).upper(): float(v)
                for t, v in zip(mcap_df["ticker"], mcap_df["market_cap_cr"], strict=False)
                if safe_str(t) and v is not None and not pd.isna(v)
            }
    rows: list[dict] = []
    for _, row in attach_strategy_breakout_signals(enrich_pead_candidates(work)).iterrows():
        ticker = safe_str(row.get("ticker"))
        market = resolve_listing_market(ticker, safe_str(row.get("market")) or None)
        sc_url, tv_url = research_links(ticker, market)
        row_mcap = row.get("market_cap_cr")
        if (row_mcap is None or pd.isna(row_mcap)) and ticker:
            row_mcap = mcap_map.get(ticker.upper())
        row_data = {
                "ticker": ticker,
                "name": safe_str(row.get("name")),
                "market": market,
                "market_cap_cr": json_safe_scalar(row_mcap),
                "price": json_safe_scalar(
                    row.get("price")
                    if row.get("price") is not None and not (
                        isinstance(row.get("price"), float) and pd.isna(row.get("price"))
                    )
                    else row.get("current_price")
                ),
                "pe_ratio": json_safe_scalar(row.get("pe_ratio")),
                "pead_score": json_safe_scalar(row.get("pead_score")),
                "pead_note": (
                    safe_str(row.get("pead_note"))
                    or safe_str(row.get("pead_status"))
                    or None
                ),
                "comfortable_buy_price": json_safe_scalar(row.get("comfortable_buy_price")),
                "buy_headroom_pct": json_safe_scalar(row.get("buy_headroom_pct")),
                "valuation_pass": json_safe_scalar(row.get("valuation_pass")),
                "sector": safe_str(row.get("sector")) or None,
                "industry": safe_str(row.get("industry")) or None,
                "sub_sector": safe_str(row.get("sub_sector")) or None,
                "chg_from_snapshot_pct": json_safe_scalar(row.get("chg_from_snapshot_pct")),
                "pnl_pct": json_safe_scalar(row.get("pnl_pct")),
                "snapshot_price": json_safe_scalar(row.get("snapshot_price")),
                **corp_tags_dict_for_ticker(ticker),
                **{k: v for k, v in (ss_map.get(ticker.upper()) or {}).items() if k != "ss_holders"},
                "sales_yoy": json_safe_scalar(row.get("sales_yoy")),
                "np_yoy": json_safe_scalar(row.get("np_yoy")),
                "eps_yoy": json_safe_scalar(row.get("eps_yoy")),
                "surprise_growth": json_safe_scalar(row.get("surprise_growth")),
                "peg": json_safe_scalar(row.get("peg")),
                "napkin_pe": json_safe_scalar(row.get("napkin_pe")),
                "napkin_near_pe": json_safe_scalar(row.get("napkin_near_pe")),
                "napkin_required_cagr": json_safe_scalar(row.get("napkin_required_cagr")),
                "napkin_growth": json_safe_scalar(row.get("napkin_growth")),
                "napkin_gap": json_safe_scalar(row.get("napkin_gap")),
                "napkin_fair_pe": json_safe_scalar(row.get("napkin_fair_pe")),
                "surv_type": safe_str(row.get("surv_type")) or None,
                "surv_stage": safe_str(row.get("surv_stage")) or None,
                "drawdown_pct": json_safe_scalar(row.get("drawdown_pct")),
                "bounce_pct": json_safe_scalar(row.get("bounce_pct")),
                "distress_flags": safe_str(row.get("distress_flags")) or None,
                "distress_reason": safe_str(row.get("distress_reason")) or None,
                "fisher_growth": json_safe_scalar(row.get("fisher_growth")),
                "fisher_margin": json_safe_scalar(row.get("fisher_margin")),
                "fisher_quality": json_safe_scalar(row.get("fisher_quality")),
                "fisher_checks": safe_str(row.get("fisher_checks")) or None,
                "fisher_manual": safe_str(row.get("fisher_manual")) or None,
                "calculation_date": safe_str(row.get("calculation_date")) or None,
                "sc": sc_url,
                "tv": tv_url,
                "result_date": json_safe_scalar(row.get("result_date")),
                "forward_pe": json_safe_scalar(row.get("forward_pe")),
                "returns_pct": json_safe_scalar(row.get("returns_pct")),
                "daily_ret_pct": json_safe_scalar(row.get("daily_ret_pct")),
                "quarter_end": json_safe_scalar(row.get("quarter_end")),
                "sales_qoq": json_safe_scalar(row.get("sales_qoq")),
                "np_qoq": json_safe_scalar(row.get("np_qoq")),
                "ebidt_yoy": json_safe_scalar(row.get("ebidt_yoy")),
                "ebidt_qoq": json_safe_scalar(row.get("ebidt_qoq")),
                "cf_profit": json_safe_scalar(row.get("cf_profit")),
                "sales_bust": json_safe_bool(row.get("sales_bust")),
                "sales_streak": json_safe_scalar(row.get("sales_streak")),
                "has_tq": json_safe_bool(row.get("has_tq")),
                "has_bb": json_safe_bool(row.get("has_bb")),
                "tq_score": json_safe_scalar(row.get("tq_score")),
                "tq_crossover": safe_str(row.get("tq_crossover")) or None,
                "tq_timeframe": safe_str(row.get("tq_timeframe")) or None,
                "bb_signal": safe_str(row.get("bb_signal")) or None,
                "bb_timeframe": safe_str(row.get("bb_timeframe")) or None,
                "rev_jump": json_safe_scalar(row.get("rev_jump")),
                "op_jump": json_safe_scalar(row.get("op_jump")),
                "eps_jump": json_safe_scalar(row.get("eps_jump")),
                "opm_pct": json_safe_scalar(row.get("opm_pct")),
                "opm_room_pp": json_safe_scalar(row.get("opm_room_pp")),
                "gap_pct": json_safe_scalar(row.get("gap_pct")),
                "vol_ratio": json_safe_scalar(row.get("vol_ratio")),
                "pead1_signal": safe_str(row.get("pead1_signal") or row.get("signal")) or None,
            }
        note = row.get("stock_note")
        if isinstance(note, dict) and (
            note.get("business") or note.get("market_position") or note.get("triggers")
        ):
            row_data["stock_note"] = {
                "business": safe_str(note.get("business")) or None,
                "market_position": safe_str(note.get("market_position")) or None,
                "triggers": list(note.get("triggers") or []),
                "source": safe_str(note.get("source")) or None,
            }
        quarters = row.get("quarters")
        if isinstance(quarters, dict) and quarters.get("labels"):
            row_data["quarters"] = sanitize_quarter_panel(quarters)
        snapshot = row.get("snapshot")
        snap_price = json_safe_scalar(snapshot.get("price") if isinstance(snapshot, dict) else None)
        if isinstance(snapshot, dict) and snap_price is not None:
            snap = dict(snapshot)
            mcap = row_mcap if row_mcap is not None and not pd.isna(row_mcap) else row.get("market_cap_cr")
            if mcap is not None and pd.notna(mcap) and snap.get("market_cap_cr") is None:
                snap["market_cap_cr"] = round(float(mcap), 1)
            elif snap.get("market_cap_cr") is not None and row_data.get("market_cap_cr") is None:
                row_data["market_cap_cr"] = json_safe_scalar(snap.get("market_cap_cr"))
            row_data["snapshot"] = snap
            if snap.get("long_description"):
                row_data["long_description"] = snap["long_description"]
            if snap.get("website"):
                row_data["website"] = sanitize_website(snap["website"])
            for key in (
                "company_sector",
                "company_industry",
                "headquarters",
                "employees",
            ):
                if snap.get(key) is not None:
                    row_data[key] = json_safe_scalar(snap.get(key))
        elif json_safe_scalar(row.get("price")) is not None:
            row_data["snapshot"] = {
                "price": row_data["price"],
                "market_cap_cr": row_data.get("market_cap_cr"),
                "pe": row_data.get("pe_ratio"),
                "pe_ratio": row_data.get("pe_ratio"),
                "forward_pe": row_data.get("forward_pe"),
                "cagr": None,
                "w52_low": None,
                "w52_high": None,
                "moving_averages": [],
            }
        rows.append(json_safe_obj(row_data))
    if include_news and rows:
        # Only hydrate news for small boards — full NSE embeds blow the iframe.
        fetch_news = len(rows) <= 80
        return attach_google_news_to_rows(rows, fetch_missing=fetch_news)
    return rows


def build_pead2_dashboard_html(
    df: pd.DataFrame,
    *,
    df_previous: pd.DataFrame | None = None,
    title: str = "Top PEAD Candidates",
    list_label: str = "PEAD candidates",
    show_scored_split: bool = False,
    standalone: bool = True,
    default_sort_col: str = "result_date",
    default_sort_dir: int = -1,
    recent_filter_days: int | None = None,
    recent_day_options: tuple[int, ...] | None = None,
    variant: str = "pead2",
    score_high_min: float | None = None,
    max_rows: int | None = None,
    report_total: int | None = None,
) -> str:
    del recent_filter_days, recent_day_options
    report_total = report_total if report_total is not None else len(df)
    df, _ = limit_pead_report_df(df, max_rows)
    cap_note = ""
    if report_total > len(df):
        cap_note = (
            f" · showing {len(df):,} of {report_total:,} "
            f"(search table · Download CSV for full list)"
        )
    is_pead1 = str(variant).lower() in ("pead1", "pead_1", "1")
    is_psq = str(variant).lower() in ("psq", "positive_surprise", "positive_surprise_quant")
    is_peg_aware = str(variant).lower() in ("peg_aware", "peg-aware", "pegaware")
    is_fisher = str(variant).lower() in ("fisher", "fisher_multibagger", "multibagger")
    is_napkin = str(variant).lower() in ("napkin", "napkin_investing", "lotusdew")
    is_distress = str(variant).lower() in (
        "distress",
        "distressed",
        "surveillance",
        "turnaround",
    )
    is_holdings = str(variant).lower() in ("holdings", "portfolio", "holding")
    list_label_js = json_dumps(list_label)
    show_scored_split_js = "true" if show_scored_split else "false"
    updated = _scan_generated_ist(df)
    large_report = len(df) >= _LARGE_REPORT_ROWS
    table_current, expand_current = _table_and_expand_rows(
        df,
        include_news=not large_report,
        slim_expand=large_report,
    )
    prev_df = df_previous if df_previous is not None else pd.DataFrame()
    if is_pead1 or is_holdings or large_report:
        # Previous quarter doubles payload; skip on large NSE boards.
        prev_df = pd.DataFrame()
    prev_df, _ = limit_pead_report_df(prev_df, max_rows)
    table_previous, expand_previous = _table_and_expand_rows(
        prev_df,
        include_news=not large_report,
        slim_expand=large_report,
    )
    expand_by_ticker = {**expand_previous, **expand_current}
    data_current_tag = _json_script_tag("pead-data-current", table_current)
    data_previous_tag = _json_script_tag("pead-data-previous", table_previous)
    expand_tag = _json_script_tag("pead-expand-data", expand_by_ticker)
    has_previous = len(table_previous) > 0
    high_min = 5.0 if is_pead1 else 40.0
    if is_psq:
        high_min = 55.0
    if is_peg_aware:
        high_min = 40.0
    if is_fisher:
        high_min = 55.0
    if is_napkin:
        high_min = 50.0
    if is_distress:
        high_min = 55.0
    if score_high_min is not None:
        high_min = float(score_high_min)

    if is_holdings:
        cols_js = """[
  {id:"company", label:"Company", fmt:"company", def:true},
  {id:"price", label:"Price", fmt:"num2", def:true},
  {id:"result_date", label:"Result Date", fmt:"date", def:true, title:"Latest earnings result date (PEAD)"},
  {id:"pead_score", label:"PEAD Score", fmt:"score", def:true},
  {id:"pe_ratio", label:"PE", fmt:"pe", def:true, title:"Trailing P/E"},
  {id:"forward_pe", label:"Forward PE", fmt:"fpe", def:true, title:"Forward P/E from Yahoo / snapshot"},
  {id:"market_cap_cr", label:"Mcap Cr", fmt:"num1", def:false},
  {id:"pnl_pct", label:"PnL %", fmt:"pct", def:false, title:"Vs average buy price when set"},
]"""
        default_sort_col = "company" if not default_sort_col or default_sort_col == "name" else default_sort_col
        col_btn_title = "Show mcap / PnL"
        quarter_toggle = ""
        signal_filter_btns = """
        <button type="button" class="signal-btn on" data-signal="all">All</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB NEW</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>"""
        default_signal_filter = "all"
    elif is_pead1:
        # Default cols mirror PEAD 2 density (PE / Fwd PE visible; extras behind Columns).
        cols_js = """[
  {id:"company", label:"Company", fmt:"company", def:true},
  {id:"pead_score", label:"PEAD1 Score", fmt:"score", def:true},
  {id:"pead1_signal", label:"Signal", fmt:"signal", def:true},
  {id:"result_date", label:"Result Date", fmt:"date", def:true},
  {id:"pe_ratio", label:"PE", fmt:"pe", def:true, title:"Trailing P/E"},
  {id:"forward_pe", label:"Forward PE", fmt:"fpe", def:true, title:"Forward P/E from Yahoo / snapshot"},
  {id:"rev_jump", label:"Rev×", fmt:"jump", def:true, title:"Latest revenue ÷ avg of prior 3 quarters"},
  {id:"op_jump", label:"Op×", fmt:"jump", def:true, title:"Latest operating profit ÷ avg of prior 3 quarters"},
  {id:"eps_jump", label:"EPS×", fmt:"jump", def:true, title:"Latest EPS ÷ avg of prior 3 quarters"},
  {id:"opm_pct", label:"OPM%", fmt:"num1", def:false},
  {id:"gap_pct", label:"Gap%", fmt:"pct", def:false},
  {id:"vol_ratio", label:"Vol×", fmt:"jump", def:false},
  {id:"opm_room_pp", label:"Room pp", fmt:"num1", def:false},
  {id:"quarter_end", label:"Quarter", fmt:"date_iso", def:false},
]"""
        default_sort_col = default_sort_col if default_sort_col else "pead_score"
        if default_sort_col == "result_date":
            default_sort_col = "pead_score"
        col_btn_title = "Show OPM / gap / Vol× / room / quarter"
        quarter_toggle = ""
        signal_filter_btns = """
        <button type="button" class="signal-btn" data-signal="all">All</button>
        <button type="button" class="signal-btn buy on" data-signal="buy" title="Fundamentals + gap/volume — stocks to buy">Buy</button>
        <button type="button" class="signal-btn fund" data-signal="fund" title="Fundamentals only — watchlist">FUND</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB NEW</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>"""
        default_signal_filter = "buy"
    elif is_distress:
        cols_js = """[
  {id:"company", label:"Company", fmt:"company", def:true},
  {id:"pead_score", label:"Distress Score", fmt:"score", def:true, title:"Recovery optionality among surveillance / seed names"},
  {id:"surv_type", label:"List", fmt:"text", def:true, title:"ASM / GSM / SEED"},
  {id:"surv_stage", label:"Stage", fmt:"text", def:true},
  {id:"drawdown_pct", label:"vs 52W High", fmt:"pct", def:true},
  {id:"bounce_pct", label:"vs 52W Low", fmt:"pct", def:true},
  {id:"eps_yoy", label:"EPS YoY", fmt:"pct", def:true},
  {id:"sales_yoy", label:"Sales YoY", fmt:"pct", def:true},
  {id:"returns_pct", label:"Returns", fmt:"pct", def:true},
  {id:"forward_pe", label:"Forward PE", fmt:"fpe", def:false},
  {id:"distress_flags", label:"Flags", fmt:"text", def:false},
  {id:"distress_reason", label:"Why", fmt:"text", def:false},
]"""
        default_sort_col = "pead_score"
        col_btn_title = "Show PE / flags / reason columns"
        quarter_toggle = f"""
          <span class="quarter-toggle">
            <button type="button" class="quarter-btn on" id="btn-q-current">Current Quarter</button>
            <button type="button" class="quarter-btn" id="btn-q-previous" {"disabled" if not has_previous else ""}>Previous Quarter</button>
          </span>"""
        signal_filter_btns = """
        <button type="button" class="signal-btn on" data-signal="all">All</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB NEW</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>"""
        default_signal_filter = "all"
    elif is_napkin:
        cols_js = """[
  {id:"company", label:"Company", fmt:"company", def:true},
  {id:"pead_score", label:"Napkin Score", fmt:"score", def:true, title:"Growth coverage of required near-term CAGR (1× = 50)"},
  {id:"napkin_pe", label:"PE", fmt:"num1", def:true, title:"Forward PE preferred, else trailing"},
  {id:"napkin_near_pe", label:"Near PE", fmt:"num1", def:true, title:"Near-term slice ≈ 30% × PE (terminal ~70%)"},
  {id:"napkin_required_cagr", label:"Req CAGR", fmt:"pct", def:true, title:"Earnings CAGR baked into near-term PE over 5Y"},
  {id:"napkin_growth", label:"Growth", fmt:"pct", def:true, title:"EPS/sales/NP YoY or assumed market growth"},
  {id:"napkin_gap", label:"Gap", fmt:"pct", def:true, title:"Growth − required CAGR (pp)"},
  {id:"napkin_fair_pe", label:"Fair PE", fmt:"num1", def:true, title:"PE justified by growth under napkin weights"},
  {id:"result_date", label:"Result Date", fmt:"date", def:false},
  {id:"returns_pct", label:"Returns", fmt:"pct", def:false},
  {id:"eps_yoy", label:"EPS YoY", fmt:"pct", def:false},
  {id:"sales_yoy", label:"Sales YoY", fmt:"pct", def:false},
]"""
        default_sort_col = "pead_score"
        col_btn_title = "Show result date / returns / YoY columns"
        quarter_toggle = f"""
          <span class="quarter-toggle">
            <button type="button" class="quarter-btn on" id="btn-q-current">Current Quarter</button>
            <button type="button" class="quarter-btn" id="btn-q-previous" {"disabled" if not has_previous else ""}>Previous Quarter</button>
          </span>"""
        signal_filter_btns = """
        <button type="button" class="signal-btn on" data-signal="all">All</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB NEW</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>"""
        default_signal_filter = "all"
    elif is_psq:
        cols_js = """[
  {id:"company", label:"Company", fmt:"company", def:true},
  {id:"pead_score", label:"PSQ Score", fmt:"score", def:true},
  {id:"result_date", label:"Result Date", fmt:"date", def:true},
  {id:"surprise_growth", label:"Surprise YoY", fmt:"pct", def:true, title:"Seasonality-adjusted YoY (EPS → sales → NP)"},
  {id:"peg", label:"PEG", fmt:"num1", def:true, title:"Forward PE ÷ floored YoY growth"},
  {id:"forward_pe", label:"Forward PE", fmt:"fpe", def:true},
  {id:"eps_yoy", label:"EPS YoY", fmt:"pct", def:true},
  {id:"returns_pct", label:"Returns", fmt:"pct", def:true},
  {id:"sales_yoy", label:"Sales YoY", fmt:"pct", def:false},
  {id:"np_yoy", label:"NP YoY", fmt:"pct", def:false},
  {id:"daily_ret_pct", label:"Daily Ret", fmt:"daily", def:false},
  {id:"cf_profit", label:"CF/Profit", fmt:"cf", def:false},
]"""
        default_sort_col = "pead_score"
        col_btn_title = "Show sales / NP / daily / CF columns"
        quarter_toggle = f"""
          <span class="quarter-toggle">
            <button type="button" class="quarter-btn on" id="btn-q-current">Current Quarter</button>
            <button type="button" class="quarter-btn" id="btn-q-previous" {"disabled" if not has_previous else ""}>Previous Quarter</button>
          </span>"""
        signal_filter_btns = """
        <button type="button" class="signal-btn on" data-signal="all">All</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB NEW</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>"""
        default_signal_filter = "all"
    elif is_peg_aware:
        cols_js = """[
  {id:"company", label:"Company", fmt:"company", def:true},
  {id:"pead_score", label:"PEG-aware Score", fmt:"score", def:true},
  {id:"result_date", label:"Result Date", fmt:"date", def:true},
  {id:"surprise_growth", label:"Surprise YoY", fmt:"pct", def:true, title:"Seasonality-adjusted YoY (EPS → sales → NP)"},
  {id:"peg", label:"PEG", fmt:"num1", def:true, title:"Forward PE ÷ floored YoY growth (gate ≤ 2)"},
  {id:"forward_pe", label:"Forward PE", fmt:"fpe", def:true, title:"Price ÷ latest quarter EPS × 4"},
  {id:"returns_pct", label:"Returns", fmt:"pct", def:true},
  {id:"napkin_near_pe", label:"Near PE", fmt:"num1", def:false, title:"Napkin readout: ~30% × PE (not scored)"},
  {id:"napkin_required_cagr", label:"Req CAGR", fmt:"pct", def:false, title:"Napkin readout: CAGR baked into near-term PE"},
  {id:"napkin_gap", label:"Gap", fmt:"pct", def:false, title:"Napkin readout: growth − required CAGR (pp)"},
  {id:"daily_ret_pct", label:"Daily Ret", fmt:"daily", def:false},
  {id:"sales_yoy", label:"Sales YoY", fmt:"pct", def:false},
  {id:"sales_qoq", label:"Sales QoQ", fmt:"pct", def:false},
  {id:"np_yoy", label:"NP YoY", fmt:"pct", def:false},
  {id:"np_qoq", label:"NP QoQ", fmt:"pct", def:false},
  {id:"ebidt_yoy", label:"EBIDT YoY", fmt:"pct", def:false},
  {id:"ebidt_qoq", label:"EBIDT QoQ", fmt:"pct", def:false},
  {id:"cf_profit", label:"CF/Profit", fmt:"cf", def:false},
]"""
        default_sort_col = "pead_score"
        col_btn_title = "Show napkin / growth / CF columns"
        quarter_toggle = f"""
          <span class="quarter-toggle">
            <button type="button" class="quarter-btn on" id="btn-q-current">Current Quarter</button>
            <button type="button" class="quarter-btn" id="btn-q-previous" {"disabled" if not has_previous else ""}>Previous Quarter</button>
          </span>"""
        signal_filter_btns = """
        <button type="button" class="signal-btn on" data-signal="all">All</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB NEW</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>"""
        default_signal_filter = "all"
    elif is_fisher:
        cols_js = """[
  {id:"company", label:"Company", fmt:"company", def:true},
  {id:"pead_score", label:"Fisher Score", fmt:"score", def:true},
  {id:"fisher_checks", label:"Checks", fmt:"text", def:true, title:"Quantitative Fisher proxy checks passed"},
  {id:"result_date", label:"Result Date", fmt:"date", def:true},
  {id:"sales_yoy", label:"Sales YoY", fmt:"pct", def:true, title:"Fisher #1 sales runway"},
  {id:"np_yoy", label:"NP YoY", fmt:"pct", def:true, title:"Fisher #5/#6 margins"},
  {id:"cf_profit", label:"CF/Profit", fmt:"cf", def:true, title:"Fisher #10 cash quality"},
  {id:"forward_pe", label:"Forward PE", fmt:"fpe", def:true},
  {id:"fisher_growth", label:"Growth", fmt:"num1", def:false},
  {id:"fisher_margin", label:"Margin", fmt:"num1", def:false},
  {id:"fisher_quality", label:"Quality", fmt:"num1", def:false},
  {id:"returns_pct", label:"Returns", fmt:"pct", def:false},
  {id:"eps_yoy", label:"EPS YoY", fmt:"pct", def:false},
  {id:"sales_qoq", label:"Sales QoQ", fmt:"pct", def:false},
  {id:"fisher_manual", label:"Scuttlebutt", fmt:"text", def:false, title:"Qualitative points needing manual research"},
]"""
        default_sort_col = "pead_score"
        col_btn_title = "Show sub-scores / scuttlebutt / QoQ"
        quarter_toggle = f"""
          <span class="quarter-toggle">
            <button type="button" class="quarter-btn on" id="btn-q-current">Current Quarter</button>
            <button type="button" class="quarter-btn" id="btn-q-previous" {"disabled" if not has_previous else ""}>Previous Quarter</button>
          </span>"""
        signal_filter_btns = """
        <button type="button" class="signal-btn on" data-signal="all">All</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB NEW</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>"""
        default_signal_filter = "all"
    else:
        cols_js = """[
  {id:"company", label:"Company", fmt:"company", def:true},
  {id:"pead_score", label:"PEAD Score", fmt:"score", def:true},
  {id:"result_date", label:"Result Date", fmt:"date", def:true},
  {id:"forward_pe", label:"Forward PE", fmt:"fpe", def:true, title:"Price ÷ latest quarter EPS × 4"},
  {id:"returns_pct", label:"Returns", fmt:"pct", def:true},
  {id:"daily_ret_pct", label:"Daily Ret", fmt:"daily", def:true},
  {id:"sales_yoy", label:"Sales YoY", fmt:"pct", def:false},
  {id:"sales_qoq", label:"Sales QoQ", fmt:"pct", def:false},
  {id:"np_yoy", label:"NP YoY", fmt:"pct", def:false},
  {id:"np_qoq", label:"NP QoQ", fmt:"pct", def:false},
  {id:"ebidt_yoy", label:"EBIDT YoY", fmt:"pct", def:false},
  {id:"ebidt_qoq", label:"EBIDT QoQ", fmt:"pct", def:false},
  {id:"cf_profit", label:"CF/Profit", fmt:"cf", def:false},
]"""
        col_btn_title = "Show growth / CF columns"
        quarter_toggle = f"""
          <span class="quarter-toggle">
            <button type="button" class="quarter-btn on" id="btn-q-current">Current Quarter</button>
            <button type="button" class="quarter-btn" id="btn-q-previous"{" disabled" if not has_previous else ""}>Previous Quarter</button>
            <button type="button" class="quarter-btn" id="btn-refresh-returns" title="Update Returns &amp; Daily Ret from latest Yahoo prices">Refresh</button>
          </span>"""
        signal_filter_btns = """
        <button type="button" class="signal-btn on" data-signal="all">All</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB NEW</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>"""
        default_signal_filter = "all"

    is_pead2_default = not any(
        (
            is_pead1,
            is_holdings,
            is_peg_aware,
            is_fisher,
            is_napkin,
            is_distress,
        )
    )
    show_top_picks = is_pead2_default or is_psq or is_holdings
    picks_html = (
        _build_top_picks_html(df, variant=variant, high_min=high_min)
        if show_top_picks
        else ""
    )
    if is_psq:
        legend_html = (
            '<div class="pead-legend">'
            "<span>Start with <b>high-score</b> cards — NSE XBRL surprise + growth.</span>"
            "</div>"
        )
    elif is_holdings:
        legend_html = (
            '<div class="pead-legend">'
            "<span><b>Strong</b> = high PEAD + sensible Fwd PE (≤40) + price not fading.</span>"
            "<span><b>Caution</b> = high score but rich PE / weak returns — dig deeper.</span>"
            "</div>"
        )
    elif is_pead2_default:
        if large_report:
            legend_html = (
                '<div class="pead-legend">'
                "<span><b>Strong</b> = high PEAD + sensible Fwd PE (≤40) + cooperating returns.</span>"
                "<span>Large NSE board — showing top rows; use search / Download CSV for the rest.</span>"
                "</div>"
            )
        else:
            legend_html = (
                '<div class="pead-legend">'
                "<span><b>Strong</b> = high PEAD + sensible Fwd PE (≤40) + cooperating returns.</span>"
                "<span><b>Caution</b> = rich PE or fading price — dig deeper before acting.</span>"
                "</div>"
            )
    else:
        legend_html = ""

    body = f"""
<div class="dash" id="dash">
  <main class="main">
    <div class="topbar">
      <div>
        <h1 class="title">🏆 {html.escape(title)}</h1>
        <div class="meta">
          {html.escape(updated)} · panel {_PEAD2_UI_BUILD} · click row to expand detail{html.escape(cap_note)}
          {quarter_toggle}
        </div>
      </div>
      <div class="top-actions">
        <button class="icon-btn" id="btn-theme" type="button" title="Toggle theme">Light</button>
        <button class="icon-btn" id="btn-fs" type="button" title="Fullscreen">Fullscreen</button>
      </div>
    </div>
    {legend_html}
    {picks_html}
    <div class="toolbar">
      <input class="pead-search" id="pead-search" type="search" placeholder="Search ticker or name…" autocomplete="off" />
      <div class="signal-filter" id="signal-filter">
        <span class="signal-filter-label">Show</span>
        {signal_filter_btns}
      </div>
      <div class="count" id="count-label">0 companies</div>
      <div class="col-toggle">
        <button type="button" id="btn-cols" title="{html.escape(col_btn_title)}">Columns (<span id="col-visible">6</span>/<span id="col-total">13</span>)</button>
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
{data_current_tag}
{data_previous_tag}
{expand_tag}
<script>
{EXPAND_PANEL_JS}
const DATA_CURRENT = JSON.parse(document.getElementById("pead-data-current").textContent);
const DATA_PREVIOUS = JSON.parse(document.getElementById("pead-data-previous").textContent);
const EXPAND_BY_TICKER = JSON.parse(document.getElementById("pead-expand-data").textContent);
function rowDetail(r) {{
  if (!r || !r.ticker) return r;
  const extra = EXPAND_BY_TICKER[r.ticker];
  return extra ? Object.assign({{}}, r, extra) : r;
}}
const HAS_PREVIOUS = {"true" if has_previous else "false"};
const LIST_LABEL = {list_label_js};
const SHOW_SCORED_SPLIT = {show_scored_split_js};
const SCORE_HIGH_MIN = {high_min};
const IS_HOLDINGS = {"true" if is_holdings else "false"};
let quarterMode = "current";
const COLS = {cols_js};
let showAllCols = false;

function visibleCols() {{
  return COLS.filter(c => c.def || showAllCols);
}}

function updateColBtn() {{
  const n = visibleCols().length;
  document.getElementById("col-visible").textContent = String(n);
  document.getElementById("col-total").textContent = String(COLS.length);
  document.getElementById("btn-cols").classList.toggle("on", showAllCols);
}}
document.getElementById("btn-cols").onclick = () => {{
  showAllCols = !showAllCols;
  updateColBtn();
  render();
}};
updateColBtn();
let sortCol = {json.dumps(default_sort_col)};
let sortDir = {default_sort_dir};
let expandedTicker = null;
let searchQuery = "";
let signalFilter = {json.dumps(default_signal_filter)};

function pead1Signal(r) {{
  const s = String(r.pead1_signal || r.signal || "").toUpperCase();
  if (s === "BUY" || s === "EARNINGS_BUY") return "buy";
  if (s === "FUND" || s === "EARNINGS_FUNDAMENTAL") return "fund";
  return "";
}}

function rowMatchesSignal(r) {{
  if (signalFilter === "all") return true;
  if (signalFilter === "buy") return pead1Signal(r) === "buy";
  if (signalFilter === "fund") return pead1Signal(r) === "fund";
  const tq = !!r.has_tq;
  const bb = !!r.has_bb && String(r.bb_signal || "").toUpperCase() === "NEW_BREAKOUT";
  if (signalFilter === "tq") return tq;
  if (signalFilter === "bb") return bb;
  if (signalFilter === "both") return tq && bb;
  return true;
}}

function setSignalFilter(mode) {{
  signalFilter = mode;
  document.querySelectorAll("#signal-filter .signal-btn").forEach(btn => {{
    btn.classList.toggle("on", btn.dataset.signal === mode);
  }});
  render();
}}

document.querySelectorAll("#signal-filter .signal-btn").forEach(btn => {{
  btn.onclick = () => setSignalFilter(btn.dataset.signal || "all");
}});

function colById(id) {{
  return COLS.find(c => c.id === id) || COLS[0];
}}

function compareRows(a, b, col) {{
  if (col.fmt === "company") {{
    const av = String(a.name || a.ticker || "").toLowerCase();
    const bv = String(b.name || b.ticker || "").toLowerCase();
    return av.localeCompare(bv) * sortDir;
  }}
  if (col.fmt === "date" || col.id === "result_date") {{
    const av = String(a.result_date || "");
    const bv = String(b.result_date || "");
    return av.localeCompare(bv) * sortDir;
  }}
  const av = num(a[col.id]);
  const bv = num(b[col.id]);
  if (av === null && bv === null) return 0;
  if (av === null) return 1;
  if (bv === null) return -1;
  return (av - bv) * sortDir;
}}

const root = document.documentElement;
const dash = document.getElementById("dash");
const themeKey = "pead2-theme";

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
  document.getElementById("btn-fs").classList.toggle("on", on);
}}

document.getElementById("btn-theme").onclick = toggleTheme;
document.getElementById("btn-fs").onclick = toggleFs;
document.addEventListener("keydown", (e) => {{
  if (e.key === "Escape" && dash.classList.contains("fs")) toggleFs();
}});
loadTheme();

function activeData() {{
  return quarterMode === "previous" ? DATA_PREVIOUS : DATA_CURRENT;
}}

function setQuarterMode(mode) {{
  if (mode === "previous" && !HAS_PREVIOUS) return;
  quarterMode = mode;
  expandedTicker = null;
  const btnCur = document.getElementById("btn-q-current");
  const btnPrev = document.getElementById("btn-q-previous");
  if (btnCur) btnCur.classList.toggle("on", mode === "current");
  if (btnPrev) btnPrev.classList.toggle("on", mode === "previous");
  render();
}}
const _btnQCur = document.getElementById("btn-q-current");
const _btnQPrev = document.getElementById("btn-q-previous");
const _btnRefresh = document.getElementById("btn-refresh-returns");
if (_btnQCur) _btnQCur.onclick = () => setQuarterMode("current");
if (_btnQPrev) _btnQPrev.onclick = () => setQuarterMode("previous");
if (_btnRefresh) _btnRefresh.onclick = () => {{
  _btnRefresh.disabled = true;
  _btnRefresh.textContent = "…";
  try {{
    const w = window.top || window.parent;
    const url = new URL(w.location.href);
    url.searchParams.set("pead2_refresh", "1");
    w.location.assign(url.toString());
  }} catch (_) {{
    _btnRefresh.disabled = false;
    _btnRefresh.textContent = "Refresh";
  }}
}};

function num(v) {{ return v === null || v === undefined || v === "" ? null : Number(v); }}
function fmtPctNum(n) {{
  const v = Number(n);
  if (!isFinite(v)) return "—";
  const t = Math.trunc(v * 10) / 10;
  return t.toLocaleString("en-IN", {{
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }});
}}
function fmtPct(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  const cls = n >= 0 ? "g-pos" : "g-neg";
  const sign = n >= 0 ? "+" : "";
  return `<span class="${{cls}}">${{sign}}${{fmtPctNum(n)}}%</span>`;
}}
function fmtDaily(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  const cls = n >= 0 ? "g-pos" : "g-neg";
  const sign = n >= 0 ? "+" : "";
  return `<span class="${{cls}}">${{sign}}${{fmtPctNum(n)}}%</span>`;
}}
function fmtScore(v, r) {{
  const n = num(v);
  if (n === null || isNaN(n)) {{
    if (IS_HOLDINGS && r && r.pead_note) {{
      return `<span class="pead-skip" title="${{esc(r.pead_note)}}">—</span>`;
    }}
    return "—";
  }}
  let tier = "mid";
  if (n > SCORE_HIGH_MIN) tier = "high";
  else if (n < 0) tier = "low";
  else if (n <= SCORE_HIGH_MIN * 0.35) tier = "low";
  return `<span class="badge-score ${{tier}}">${{n.toFixed(1)}}</span>`;
}}
function fmtJump(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  const cls = n >= 1.5 ? "g-pos" : (n >= 1.0 ? "" : "g-neg");
  return `<span class="${{cls}}">${{n.toFixed(2)}}×</span>`;
}}
function fmtNum1(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  return n.toFixed(1);
}}
function fmtNum2(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  return n.toFixed(2);
}}
function fmtSignal(v) {{
  const s = String(v || "").toUpperCase();
  if (!s) return "—";
  if (s === "BUY" || s === "EARNINGS_BUY") return `<span class="badge-score high">BUY</span>`;
  if (s === "FUND" || s === "EARNINGS_FUNDAMENTAL") return `<span class="badge-score mid">FUND</span>`;
  return esc(s);
}}
function fmtPe(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  const cls = n < 0 ? "g-neg" : "";
  return `<span class="${{cls}}">${{n.toFixed(1)}}</span>`;
}}
function fmtFpe(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  if (n >= 500) return `<span class="g-fpe-bad">${{n.toFixed(1)}}</span>`;
  let cls = "g-fpe-good";
  if (n > 40) cls = "g-fpe-bad";
  else if (n > 20) cls = "g-fpe-mid";
  return `<span class="${{cls}}">${{n.toFixed(1)}}</span>`;
}}
function fmtCf(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  let cls = "g-fpe-good";
  if (n < 0.5) cls = "g-fpe-bad";
  else if (n < 1.2) cls = "g-fpe-mid";
  return `<span class="${{cls}}">${{n.toFixed(2)}}</span>`;
}}
function fmtCheck(pass) {{
  if (pass === true) return `<span class="g-pos">✓</span>`;
  if (pass === false) return `<span class="g-neg">✗</span>`;
  return "—";
}}
function fmtDateIso(v) {{
  if (!v) return "—";
  return String(v).slice(0, 10);
}}
function fmtRet(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  const cls = n >= 0 ? "g-pos" : "g-neg";
  const sign = n >= 0 ? "+" : "";
  return `<span class="${{cls}}">${{sign}}${{fmtPctNum(n)}}%</span>`;
}}
function fmtNum(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  return `<span class="g-mid">${{n.toFixed(2)}}</span>`;
}}
function fmtDate(v) {{
  if (!v) return "—";
  const parts = String(v).split("-");
  if (parts.length === 3) {{
    const d = parseInt(parts[2], 10);
    const m = parseInt(parts[1], 10);
    return `${{d}}/${{m}}/${{parts[0]}}`;
  }}
  return String(v);
}}
function fmtPrice(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  return `<span class="num">₹${{n.toLocaleString("en-IN", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }})}}</span>`;
}}
function fmtWebPill(web) {{
  if (!web) return "";
  let href = String(web).trim();
  if (!/^https?:\\/\\//i.test(href)) href = "https://" + href;
  const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  let title = href;
  try {{
    const host = new URL(href).hostname.replace(/^www\\./i, "");
    if (host) title = host;
  }} catch (_) {{}}
  return `<a href="${{esc(href)}}" target="_blank" rel="noopener noreferrer" title="${{esc(title)}}">Web</a>`;
}}
function fmtCompany(r) {{
  const name = r.name || r.ticker;
  const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  const tags = fmtCorpTags(r);
  const web = r.website || (r.snapshot && r.snapshot.website);
  let links =
    `<span class="links-inline">` +
    `<a href="${{esc(r.sc)}}" target="_blank" rel="noopener noreferrer" title="screener.in">SC</a>` +
    `<a href="${{esc(r.tv)}}" target="_blank" rel="noopener noreferrer" title="TradingView">TV</a>`;
  if (web) links += fmtWebPill(web);
  links += `</span>`;
  const label = (IS_HOLDINGS && r.ticker) ? String(r.ticker) : name;
  return (
    `<div class="company-cell">` +
    `<div class="company-top">` +
    `<div class="company-name-wrap">` +
    `<span class="company-name" title="${{esc(name)}}">${{esc(label)}}</span>` +
    `</div>` +
    `<span class="company-actions">` +
    `<span class="expand-hint" title="Click row for price, quarterly data &amp; news"></span>` +
    links +
    `</span></div>` +
    (tags ? `<div class="company-tags-row">${{tags}}</div>` : "") +
    `</div>`
  );
}}
function cell(col, r) {{
  switch(col.fmt) {{
    case "company": return fmtCompany(r);
    case "score": return fmtScore(r.pead_score, r);
    case "date": return fmtDate(r.result_date);
    case "date_iso": return fmtDateIso(r[col.id] || r.result_date);
    case "pe": return fmtPe(r.pe_ratio);
    case "fpe": return fmtFpe(r.forward_pe);
    case "cf": return fmtCf(r.cf_profit);
    case "check": return fmtCheck(r[col.id]);
    case "pct": return fmtPct(r[col.id]);
    case "daily": return fmtDaily(r.daily_ret_pct);
    case "jump": return fmtJump(r[col.id]);
    case "num1": return fmtNum1(r[col.id]);
    case "num2": return fmtNum2(r[col.id]);
    case "text": return (r[col.id] == null || r[col.id] === "") ? "—" : String(r[col.id]);
    case "signal": return fmtSignal(r.pead1_signal || r.signal);
    default: return r[col.id] ?? "—";
  }}
}}

function syncExpandPanelWidth() {{
  const wrap = document.getElementById("table-wrap");
  const table = document.getElementById("pead-table");
  if (!wrap || !table) return;
  const w = wrap.clientWidth;
  document.querySelectorAll("tr.pead-expand td.pead-expand-td").forEach(td => {{
    td.style.width = w + "px";
    td.style.maxWidth = w + "px";
  }});
}}

function toggleExpand(ticker) {{
  expandedTicker = expandedTicker === ticker ? null : ticker;
  render();
  if (expandedTicker) {{
    requestAnimationFrame(() => {{
      syncExpandPanelWidth();
      const open = document.querySelector("tr.pead-expand");
      if (open) open.scrollIntoView({{ block: "nearest", behavior: "smooth" }});
    }});
  }}
}}

function colClass(c) {{
  return c.id === "company" ? "col-company" : "col-num";
}}

function renderHead() {{
  const tr = document.getElementById("thead");
  tr.innerHTML = "";
  const cols = visibleCols();
  cols.forEach(c => {{
    const th = document.createElement("th");
    th.className = colClass(c);
    const active = sortCol === c.id;
    const arrow = active ? (sortDir < 0 ? "↓" : "↑") : "↕";
    th.innerHTML =
      `<span class="th-inner"><span class="th-label">${{c.label}}</span>` +
      `<span class="sort-ind${{active ? " active" : ""}}">${{arrow}}</span></span>`;
    if (c.title) th.title = c.title;
    th.onclick = () => {{
      if (sortCol === c.id) sortDir *= -1;
      else {{
        sortCol = c.id;
        sortDir = (c.id === "company") ? 1 : -1;
      }}
      render();
    }};
    tr.appendChild(th);
  }});
}}

function rowMatchesSearch(r, q) {{
  const hay = [r.ticker, r.name, r.sector, r.industry, r.sub_sector]
    .map(v => String(v || "").toLowerCase())
    .join(" ");
  return hay.includes(q);
}}

function render() {{
  const DATA = activeData();
  let rows = DATA.slice();
  if (signalFilter !== "all") {{
    rows = rows.filter(r => rowMatchesSignal(r));
  }}
  if (searchQuery) {{
    rows = rows.filter(r => rowMatchesSearch(r, searchQuery));
  }}
  const sortColumn = colById(sortCol);
  rows.sort((a, b) => compareRows(a, b, sortColumn));
  const quarterLabel = quarterMode === "previous" ? "Previous" : "Current";
  const scored = rows.filter(r => num(r.pead_score) !== null).length;
  const total = DATA.length;
  const filtered = signalFilter !== "all" || searchQuery;
  let countText = filtered && rows.length !== total
    ? `${{rows.length}} of ${{total}}`
    : `${{rows.length}}`;
  countText = `${{LIST_LABEL}} (${{countText}}`;
  if (SHOW_SCORED_SPLIT && scored < rows.length) {{
    countText += ` · ${{scored}} with PEAD scores`;
  }}
  if (signalFilter !== "all") {{
    const sigLabels = {{
      buy: "Buy",
      fund: "FUND",
      tq: "TQ weekly",
      bb: "BB NEW",
      both: "TQ + BB NEW",
    }};
    const sigLabel = sigLabels[signalFilter] || signalFilter;
    countText += ` · ${{sigLabel}} only`;
  }}
  countText += ` · ${{quarterLabel}} quarter · latest results first)`;
  document.getElementById("count-label").textContent = countText;
  renderHead();
  const tb = document.getElementById("tbody");
  tb.innerHTML = "";
  rows.forEach(r => {{
    const isOpen = expandedTicker === r.ticker;
    const tr = document.createElement("tr");
    tr.className = "pead-row"
      + (isOpen ? " expanded" : "");
    tr.onclick = (e) => {{
      if (e.target.closest("a")) return;
      toggleExpand(r.ticker);
    }};
    const cols = visibleCols();
    cols.forEach(c => {{
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
      td.colSpan = cols.length;
      td.className = "pead-expand-td";
      td.innerHTML = renderPeadExpandPanel(rowDetail(r));
      tr2.appendChild(td);
      tb.appendChild(tr2);
    }}
  }});
  syncExpandPanelWidth();
  syncPickCards(rows);
}}

function syncPickCards(visibleRows) {{
  const picks = document.querySelectorAll(".pead-pick[data-ticker]");
  if (!picks.length) return;
  const filterActive = signalFilter !== "all" || !!searchQuery;
  const visible = new Set((visibleRows || []).map(r => String(r.ticker || "").toUpperCase()));
  let shown = 0;
  picks.forEach(el => {{
    const t = String(el.getAttribute("data-ticker") || "").toUpperCase();
    const ok = !filterActive || visible.has(t);
    el.style.display = ok ? "" : "none";
    if (ok) shown += 1;
  }});
  const empty = document.querySelector(".pead-picks-empty-filter");
  if (empty) {{
    empty.style.display = filterActive && shown === 0 ? "" : "none";
  }}
}}

document.getElementById("pead-search").oninput = (e) => {{
  searchQuery = e.target.value.trim().toLowerCase();
  render();
}};

function bindPickCards() {{
  document.querySelectorAll(".pead-pick[data-ticker]").forEach(el => {{
    el.onclick = (e) => {{
      if (e.target.closest("a")) return;
      const t = el.getAttribute("data-ticker");
      if (t) toggleExpand(t);
    }};
  }});
}}

render();
bindPickCards();
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


def pead2_iframe_height(row_count: int, *, expanded: bool = False, with_top_picks: bool = True) -> int:
    """Tall embed so dashboard fills the page; internal scroll in table."""
    base = min(1500, max(960, 920 + min(row_count, 40) * 2))
    if with_top_picks and row_count > 0:
        base += 240
    return base + (480 if expanded else 0)
