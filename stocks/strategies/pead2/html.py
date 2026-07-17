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
from stocks.shared.links import screener_url, tradingview_url
from stocks.core.text_utils import safe_str


_PEAD2_UI_BUILD = "2026-07-17a"

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
  .corp-tag-dem { color: #92400e; background: #fef3c7; }
  .corp-tag-spin { color: #0e7490; background: #cffafe; }
  .corp-tag-tq { color: #1d4ed8; background: #dbeafe; }
  .corp-tag-bb { color: #b45309; background: #fef3c7; }
  [data-theme="dark"] .corp-tag-bg { color: #ddd6fe; background: #4c1d95; }
  [data-theme="dark"] .corp-tag-hold { color: #bfdbfe; background: #1e3a8a; }
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


from stocks.core.json_utils import json_dumps, json_safe_obj, json_safe_scalar
from stocks.market.google_news import attach_google_news_to_rows


def _rows_for_json(df: pd.DataFrame) -> list[dict]:
    sync_stock_notes_from_file()
    work = attach_stock_notes(df, sync_file=False)
    ss_map = superstar_pead_map(
        work["ticker"].astype(str).str.strip().str.upper().unique().tolist()
        if not work.empty and "ticker" in work.columns
        else []
    )
    rows: list[dict] = []
    for _, row in attach_strategy_breakout_signals(enrich_pead_candidates(work)).iterrows():
        ticker = safe_str(row.get("ticker"))
        market = safe_str(row.get("market")) or None
        row_data = {
                "ticker": ticker,
                "name": safe_str(row.get("name")),
                "market_cap_cr": json_safe_scalar(row.get("market_cap_cr")),
                "price": json_safe_scalar(row.get("price")),
                "pe_ratio": json_safe_scalar(row.get("pe_ratio")),
                "pead_score": json_safe_scalar(row.get("pead_score")),
                "comfortable_buy_price": json_safe_scalar(row.get("comfortable_buy_price")),
                "buy_headroom_pct": json_safe_scalar(row.get("buy_headroom_pct")),
                "valuation_pass": json_safe_scalar(row.get("valuation_pass")),
                "sector": safe_str(row.get("sector")) or None,
                "industry": safe_str(row.get("industry")) or None,
                "sub_sector": safe_str(row.get("sub_sector")) or None,
                **corp_tags_dict_for_ticker(ticker),
                **{k: v for k, v in (ss_map.get(ticker.upper()) or {}).items() if k != "ss_holders"},
                "sales_yoy": json_safe_scalar(row.get("sales_yoy")),
                "np_yoy": json_safe_scalar(row.get("np_yoy")),
                "eps_yoy": json_safe_scalar(row.get("eps_yoy")),
                "calculation_date": safe_str(row.get("calculation_date")) or None,
                "sc": row.get("screener_link") or screener_url(ticker, market),
                "tv": row.get("tv_link") or tradingview_url(ticker, market),
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
                "sales_bust": bool(row.get("sales_bust")),
                "sales_streak": json_safe_scalar(row.get("sales_streak")),
                "has_tq": bool(row.get("has_tq")),
                "has_bb": bool(row.get("has_bb")),
                "tq_score": json_safe_scalar(row.get("tq_score")),
                "tq_crossover": safe_str(row.get("tq_crossover")) or None,
                "tq_timeframe": safe_str(row.get("tq_timeframe")) or None,
                "bb_signal": safe_str(row.get("bb_signal")) or None,
                "bb_timeframe": safe_str(row.get("bb_timeframe")) or None,
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
            mcap = row.get("market_cap_cr")
            if mcap is not None and pd.notna(mcap) and snap.get("market_cap_cr") is None:
                snap["market_cap_cr"] = round(float(mcap), 1)
            row_data["snapshot"] = snap
            if snap.get("long_description"):
                row_data["long_description"] = snap["long_description"]
            if snap.get("website"):
                row_data["website"] = snap["website"]
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
    return attach_google_news_to_rows(rows)


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
) -> str:
    del recent_filter_days, recent_day_options
    list_label_js = json_dumps(list_label)
    show_scored_split_js = "true" if show_scored_split else "false"
    updated = _scan_generated_ist(df)
    data_current = json_dumps(_rows_for_json(df), separators=(",", ":"))
    prev_df = df_previous if df_previous is not None else pd.DataFrame()
    data_previous = json_dumps(_rows_for_json(prev_df), separators=(",", ":"))
    has_previous = len(prev_df) > 0

    body = f"""
<div class="dash" id="dash">
  <main class="main">
    <div class="topbar">
      <div>
        <h1 class="title">🏆 {html.escape(title)}</h1>
        <div class="meta">
          {html.escape(updated)} · panel {_PEAD2_UI_BUILD} · click row to expand detail
          <span class="quarter-toggle">
            <button type="button" class="quarter-btn on" id="btn-q-current">Current Quarter</button>
            <button type="button" class="quarter-btn" id="btn-q-previous"{" disabled" if not has_previous else ""}>Previous Quarter</button>
          </span>
        </div>
      </div>
      <div class="top-actions">
        <button class="icon-btn" id="btn-theme" type="button" title="Toggle theme">Light</button>
        <button class="icon-btn" id="btn-fs" type="button" title="Fullscreen">Fullscreen</button>
      </div>
    </div>
    <div class="toolbar">
      <input class="pead-search" id="pead-search" type="search" placeholder="Search ticker or name…" autocomplete="off" />
      <div class="signal-filter" id="signal-filter">
        <span class="signal-filter-label">Show</span>
        <button type="button" class="signal-btn on" data-signal="all">All</button>
        <button type="button" class="signal-btn tq" data-signal="tq">TQ weekly</button>
        <button type="button" class="signal-btn bb" data-signal="bb">BB weekly</button>
        <button type="button" class="signal-btn both" data-signal="both">TQ + BB</button>
      </div>
      <div class="count" id="count-label">0 companies</div>
      <div class="col-toggle">
        <button type="button" id="btn-cols" title="Show growth / CF columns">Columns (<span id="col-visible">6</span>/<span id="col-total">13</span>)</button>
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
<script>
{EXPAND_PANEL_JS}
const DATA_CURRENT = {data_current};
const DATA_PREVIOUS = {data_previous};
const HAS_PREVIOUS = {"true" if has_previous else "false"};
const LIST_LABEL = {list_label_js};
const SHOW_SCORED_SPLIT = {show_scored_split_js};
let quarterMode = "current";
const COLS = [
  {{id:"company", label:"Company", fmt:"company", def:true}},
  {{id:"pead_score", label:"PEAD Score", fmt:"score", def:true}},
  {{id:"result_date", label:"Result Date", fmt:"date", def:true}},
  {{id:"forward_pe", label:"Forward PE", fmt:"fpe", def:true, title:"Price ÷ latest quarter EPS × 4"}},
  {{id:"returns_pct", label:"Returns", fmt:"pct", def:true}},
  {{id:"daily_ret_pct", label:"Daily Ret", fmt:"daily", def:true}},
  {{id:"sales_yoy", label:"Sales YoY", fmt:"pct", def:false}},
  {{id:"sales_qoq", label:"Sales QoQ", fmt:"pct", def:false}},
  {{id:"np_yoy", label:"NP YoY", fmt:"pct", def:false}},
  {{id:"np_qoq", label:"NP QoQ", fmt:"pct", def:false}},
  {{id:"ebidt_yoy", label:"EBIDT YoY", fmt:"pct", def:false}},
  {{id:"ebidt_qoq", label:"EBIDT QoQ", fmt:"pct", def:false}},
  {{id:"cf_profit", label:"CF/Profit", fmt:"cf", def:false}},
];
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
let signalFilter = "all";

function rowMatchesSignal(r) {{
  if (signalFilter === "all") return true;
  const tq = !!r.has_tq;
  const bb = !!r.has_bb;
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
  document.getElementById("btn-q-current").classList.toggle("on", mode === "current");
  document.getElementById("btn-q-previous").classList.toggle("on", mode === "previous");
  render();
}}
document.getElementById("btn-q-current").onclick = () => setQuarterMode("current");
document.getElementById("btn-q-previous").onclick = () => setQuarterMode("previous");

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
function fmtScore(v) {{
  const n = num(v);
  if (n === null || isNaN(n)) return "—";
  let tier = "mid";
  if (n > 40) tier = "high";
  else if (n < 0) tier = "low";
  else if (n <= 15) tier = "low";
  return `<span class="badge-score ${{tier}}">${{n.toFixed(1)}}</span>`;
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
  return (
    `<div class="company-cell">` +
    `<div class="company-top">` +
    `<div class="company-name-wrap">` +
    `<span class="company-name" title="${{esc(name)}}">${{esc(name)}}</span>` +
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
    case "score": return fmtScore(r.pead_score);
    case "date": return fmtDate(r.result_date);
    case "date_iso": return fmtDateIso(r.result_date);
    case "fpe": return fmtFpe(r.forward_pe);
    case "cf": return fmtCf(r.cf_profit);
    case "check": return fmtCheck(r[col.id]);
    case "pct": return fmtPct(r[col.id]);
    case "daily": return fmtDaily(r.daily_ret_pct);
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
    const sigLabel = signalFilter === "tq" ? "TQ weekly" : signalFilter === "bb" ? "BB weekly" : "TQ + BB";
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
      td.innerHTML = renderPeadExpandPanel(r);
      tr2.appendChild(td);
      tb.appendChild(tr2);
    }}
  }});
  syncExpandPanelWidth();
}}

document.getElementById("pead-search").oninput = (e) => {{
  searchQuery = e.target.value.trim().toLowerCase();
  render();
}};

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


def pead2_iframe_height(row_count: int, *, expanded: bool = False) -> int:
    """Tall embed so dashboard fills the page; internal scroll in table."""
    base = min(1500, max(960, 920 + min(row_count, 40) * 2))
    return base + (480 if expanded else 0)
