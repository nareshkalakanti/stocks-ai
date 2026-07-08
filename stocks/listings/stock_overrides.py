"""Manual corrections for the India stocks universe."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str

# Display names and search aliases for tickers that need clearer labels.
_NAME_OVERRIDES: dict[str, str] = {
    "KAMOPAINTS": "Kamdhenu Ventures (Komo Paints)",
    "KAMDHENU": "Kamdhenu Limited",
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
}


def stock_display_name(ticker: str) -> str | None:
    return _NAME_OVERRIDES.get(safe_str(ticker).upper())


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
