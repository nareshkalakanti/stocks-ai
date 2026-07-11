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
from stocks.strategies.pead2.strategy import enrich_pead_candidates
from stocks.strategies.pead2.quarters import sanitize_quarter_panel
from stocks.shared.links import screener_url, tradingview_url
from stocks.core.text_utils import safe_str


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
  .count { color: var(--muted); font-size: 12px; font-weight: 600; }
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
    padding: 12px 16px 16px;
    border-bottom: 1px solid var(--border);
    white-space: normal;
    vertical-align: top;
    width: 100%;
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
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }
  .company-name {
    font-weight: 600;
    font-size: 14px;
    color: var(--text);
    line-height: 1.4;
    letter-spacing: -0.01em;
    white-space: normal;
    word-break: break-word;
    flex: 1;
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
  tr.pead-expand td {
    padding: 8px 10px 10px;
    background: var(--panel-2);
    border-bottom: 1px solid var(--border);
    white-space: normal;
    vertical-align: top;
    width: 100%;
  }
  .pead-expand-td { padding: 12px 16px 16px; }
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
  [data-theme="dark"] .q-table th.q-recent,
  [data-theme="dark"] .q-table td.q-recent { background: rgba(88, 166, 255, 0.12); }
  .q-table td.q-up,
  #pead-table .q-table td.q-up { color: var(--green); font-weight: 700; }
  .q-table td.q-down,
  #pead-table .q-table td.q-down { color: var(--red); font-weight: 700; }
  .q-table td.q-flat,
  #pead-table .q-table td.q-flat { color: var(--muted); }
  .q-empty { color: var(--muted); font-size: 12px; padding: 8px 4px; }
  .expand-hint { color: var(--muted); font-size: 10px; margin-left: 6px; }
  tr.pead-row.expanded .expand-hint::after { content: "▴"; }
  tr.pead-row:not(.expanded) .expand-hint::after { content: "▾"; }
  .expand-body.expand-pead {
    display: grid;
    grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
    gap: 12px;
    align-items: start;
    width: 100%;
  }
  .expand-body.expand-pead.expand-pead-solo {
    grid-template-columns: minmax(0, 1fr);
  }
  @media (max-width: 960px) {
    .expand-body.expand-pead { grid-template-columns: 1fr; }
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
    for _, row in enrich_pead_candidates(work).iterrows():
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


def _recent_day_pills_html(options: tuple[int, ...]) -> str:
    parts = [
        f'<button type="button" class="quarter-btn recent-day-btn" data-days="{int(d)}">{int(d)}d</button>'
        for d in options
    ]
    parts.append('<button type="button" class="quarter-btn recent-day-btn" data-days="">All</button>')
    return (
        '<span class="recent-days-label">Results</span>'
        + "".join(parts)
    )


def build_pead2_dashboard_html(
    df: pd.DataFrame,
    *,
    df_previous: pd.DataFrame | None = None,
    title: str = "Top PEAD Candidates",
    standalone: bool = True,
    default_sort_col: str = "returns_pct",
    default_sort_dir: int = -1,
    recent_filter_days: int | None = None,
    recent_day_options: tuple[int, ...] | None = None,
) -> str:
    day_options = recent_day_options or (7, 15, 30, 60)
    default_days = recent_filter_days
    if default_days is None and day_options:
        default_days = 30 if 30 in day_options else day_options[0]
    recent_pills = _recent_day_pills_html(day_options)
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
          {html.escape(updated)} · FF-style PEAD score · click row for quarterly data &amp; price snapshot
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
      <div class="count" id="count-label">0 companies</div>
      <div class="col-toggle">
        <div class="recent-days quarter-toggle" id="recent-days">{recent_pills}</div>
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
const RECENT_DAY_DEFAULT = {json.dumps(default_days)};
let recentOnlyDays = RECENT_DAY_DEFAULT;
let recentFilterOn = RECENT_DAY_DEFAULT != null;
let expandedTicker = null;

function recentCutoffIso() {{
  if (!recentOnlyDays) return null;
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - Number(recentOnlyDays));
  return d.toISOString().slice(0, 10);
}}

function passesRecentFilter(r) {{
  if (!recentFilterOn || !recentOnlyDays) return true;
  const rd = String(r.result_date || "");
  const cutoff = recentCutoffIso();
  return cutoff && rd && rd >= cutoff;
}}

function updateRecentDayPills() {{
  document.querySelectorAll(".recent-day-btn").forEach(btn => {{
    const raw = btn.dataset.days;
    const days = raw ? Number(raw) : null;
    const on = recentFilterOn
      ? days === recentOnlyDays
      : days === null;
    btn.classList.toggle("on", on);
  }});
}}

document.querySelectorAll(".recent-day-btn").forEach(btn => {{
  btn.onclick = () => {{
    const raw = btn.dataset.days;
    if (!raw) {{
      recentFilterOn = false;
    }} else {{
      recentOnlyDays = Number(raw);
      recentFilterOn = true;
      sortCol = "result_date";
      sortDir = -1;
    }}
    updateRecentDayPills();
    render();
  }};
}});
updateRecentDayPills();

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
function fmtCompany(r) {{
  const name = r.name || r.ticker;
  const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"/g,"&quot;");
  const tags = fmtCorpTags(r);
  return (
    `<div class="company-cell">` +
    `<div class="company-top">` +
    `<span class="company-name" title="${{esc(name)}}">${{esc(name)}}</span>` +
    `<span class="company-actions">` +
    `<span class="expand-hint" title="Click row for price, quarterly data &amp; news"></span>` +
    `<span class="links-inline">` +
    `<a href="${{r.sc}}" target="_blank" rel="noopener noreferrer" title="screener.in">SC</a>` +
    `<a href="${{r.tv}}" target="_blank" rel="noopener noreferrer" title="TradingView">TV</a>` +
    `</span></span></div>` +
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
    case "pct": return fmtPct(r[col.id]);
    case "daily": return fmtDaily(r.daily_ret_pct);
    default: return r[col.id] ?? "—";
  }}
}}

function toggleExpand(ticker) {{
  expandedTicker = expandedTicker === ticker ? null : ticker;
  render();
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

function render() {{
  const DATA = activeData();
  let rows = DATA.filter(passesRecentFilter);
  const sortColumn = colById(sortCol);
  rows.sort((a, b) => compareRows(a, b, sortColumn));
  const recentNote = recentFilterOn && recentOnlyDays ? ` · last ${{recentOnlyDays}}d results` : "";
  document.getElementById("count-label").textContent =
    `PEAD Candidates (${{rows.length}} companies · ${{quarterMode === "previous" ? "Previous" : "Current"}} quarter${{recentNote}})`;
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
      td.innerHTML = renderExpandPanel(r);
      tr2.appendChild(td);
      tb.appendChild(tr2);
    }}
  }});
}}

render();
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
    return base + (360 if expanded else 0)
