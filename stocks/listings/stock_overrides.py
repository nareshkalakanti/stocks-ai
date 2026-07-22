"""Manual corrections for the India stocks universe."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str

# Display names and search aliases for tickers that need clearer labels.
_NAME_OVERRIDES: dict[str, str] = {
    "KAMOPAINTS": "Kamdhenu Ventures (Komo Paints)",
    "KAMDHENU": "Kamdhenu Limited",
    "SURAJEST": "Suraj Estate Developers Limited",
    "EPACKPEB": "Epack Prefab Technologies Limited",
    "ZODIAC": "Zodiac Energy Limited",
    "ARTEMISMED": "Artemis Medicare Services Limited",
}

# Insert NSE rows when missing from the HuggingFace dataset.
_REQUIRED_NSE: dict[str, dict[str, str]] = {
    "KAMOPAINTS": {
        "name": "Kamdhenu Ventures (Komo Paints)",
        "sector": "Process industries",
    },
    "KAMDHENU": {
        "name": "Kamdhenu Limited",
        "sector": "Non-energy minerals",
    },
    "EPACKPEB": {
        "name": "Epack Prefab Technologies Limited",
        "sector": "Industrials",
        "industry": "Building Products - Prefab Structures",
        "sub_sector": "Building Products - Prefab Structures",
    },
    "SILPO": {
        "name": "SILPO Limited",
        "sector": "",
    },
    "SURAJEST": {
        "name": "Suraj Estate Developers Limited",
        "sector": "Real Estate",
        "industry": "Real Estate",
    },
    "ZODIAC": {
        "name": "Zodiac Energy Limited",
        "sector": "Energy",
        "sub_sector": "Renewable Energy Equipment & Services",
    },
    "ARTEMISMED": {
        "name": "Artemis Medicare Services Limited",
        "sector": "Healthcare",
        "sub_sector": "Hospitals & Diagnostic Centres",
    },
}


def stock_display_name(ticker: str) -> str | None:
    key = safe_str(ticker).upper()
    if key in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[key]
    required = _REQUIRED_NSE.get(key)
    if required:
        name = safe_str(required.get("name"))
        return name or None
    return None


def ticker_meta_override(ticker: str) -> dict[str, str]:
    """Name / sector fields from manual overrides (for holdings backfill)."""
    key = safe_str(ticker).upper()
    out: dict[str, str] = {}
    name = stock_display_name(key)
    if name:
        out["name"] = name
    required = _REQUIRED_NSE.get(key) or {}
    for col in ("sector", "industry", "sub_sector"):
        val = safe_str(required.get(col))
        if val:
            out[col] = val
    return out


def apply_stock_overrides(stocks: pd.DataFrame) -> pd.DataFrame:
    if stocks.empty and not _REQUIRED_NSE:
        return stocks

    out = stocks.copy()
    for col in ("ticker", "name", "market", "sector", "industry", "sub_sector"):
        if col not in out.columns:
            out[col] = ""

    tickers = out["ticker"].astype(str).str.upper()
    for ticker, name in _NAME_OVERRIDES.items():
        mask = tickers == ticker
        if mask.any():
            out.loc[mask, "name"] = name

    existing = set(tickers)
    extra_rows: list[dict[str, str]] = []
    for ticker, fields in _REQUIRED_NSE.items():
        row = {"ticker": ticker, "market": "NSE", **fields}
        if ticker in existing:
            mask = tickers == ticker
            for col in ("name", "market", "sector", "industry", "sub_sector"):
                val = safe_str(fields.get(col))
                if val:
                    out.loc[mask, col] = val
            continue
        extra_rows.append(row)
    if extra_rows:
        out = pd.concat([out, pd.DataFrame(extra_rows)], ignore_index=True)

    return out
