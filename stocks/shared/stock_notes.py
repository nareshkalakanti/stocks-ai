"""Curated company narrative (business, market position, trigger points) for reports."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stocks.core.config import STOCK_NOTES_PATH
from stocks.core.database import init_db, load_stock_notes_map, upsert_stock_note
from stocks.core.text_utils import safe_str


def _normalize_note(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    business = safe_str(raw.get("business"))
    market_position = safe_str(raw.get("market_position"))
    triggers_raw = raw.get("triggers") or []
    triggers = [
        safe_str(t) for t in triggers_raw if safe_str(t)
    ] if isinstance(triggers_raw, list) else []
    source = safe_str(raw.get("source"))
    if not business and not market_position and not triggers:
        return None
    return {
        "business": business,
        "market_position": market_position,
        "triggers": triggers,
        "source": source,
    }


def load_stock_notes_file(path: Path | None = None) -> dict[str, dict]:
    """Read ``data/stock_notes.json`` keyed by ticker."""
    file_path = path or STOCK_NOTES_PATH
    if not file_path.exists():
        return {}
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict] = {}
    for ticker, raw in payload.items():
        key = safe_str(ticker).upper()
        if not key:
            continue
        note = _normalize_note(raw if isinstance(raw, dict) else {})
        if note:
            out[key] = note
    return out


def sync_stock_notes_from_file(path: Path | None = None) -> int:
    """Import JSON file into SQLite ``stock_notes`` table. Returns rows upserted."""
    notes = load_stock_notes_file(path)
    if not notes:
        return 0
    init_db()
    for ticker, note in notes.items():
        upsert_stock_note(
            ticker,
            business=note.get("business"),
            market_position=note.get("market_position"),
            triggers=note.get("triggers"),
            source=note.get("source"),
        )
    return len(notes)


def stock_note_for_ticker(ticker: str, *, cache: dict[str, dict] | None = None) -> dict | None:
    key = safe_str(ticker).upper()
    if not key:
        return None
    notes = cache if cache is not None else load_stock_notes_map([key])
    return notes.get(key)


def attach_stock_notes(df: pd.DataFrame, *, sync_file: bool = True) -> pd.DataFrame:
    """
    Add ``stock_note`` column (dict or None) by merging SQLite notes for tickers in ``df``.

    When ``sync_file`` is True, refreshes DB from ``data/stock_notes.json`` first.
    """
    if df is None or df.empty or "ticker" not in df.columns:
        return df
    if sync_file:
        sync_stock_notes_from_file()
    tickers = df["ticker"].astype(str).str.upper().tolist()
    notes = load_stock_notes_map(tickers)
    out = df.copy()
    out["stock_note"] = out["ticker"].astype(str).str.upper().map(notes)
    return out
