"""Disk cache for intrinsic value / headwind scan results."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stocks.core.database import (
    HEADWIND_SCAN_CACHE_VERSION,
    load_headwind_scan_cache,
    load_intrinsic_value_cache,
    save_headwind_scan_cache,
    save_intrinsic_value_cache,
)
from stocks.core.text_utils import safe_str


def load_cached_iv_rows(tickers: list[str], *, max_hours: int) -> pd.DataFrame:
    return load_intrinsic_value_cache(tickers, max_hours=max_hours)


def persist_iv_rows(rows: list[dict]) -> None:
    save_intrinsic_value_cache(rows)


def iv_row_from_cache(row: pd.Series) -> dict:
    return {
        "ticker": safe_str(row.get("ticker")).upper(),
        "market": safe_str(row.get("market")) or None,
        "name": safe_str(row.get("name")),
        "price": row.get("price"),
        "market_cap_cr": row.get("market_cap_cr"),
        "sales_growth_3y": row.get("sales_growth_3y"),
        "roce_3y": row.get("roce_3y"),
        "pb": row.get("pb"),
        "pe_ratio": row.get("pe_ratio"),
        "forward_pe": row.get("forward_pe"),
        "pcf": row.get("pcf"),
        "cash_ratio": row.get("cash_ratio"),
    }


def _fill_pe_values(
    out: pd.DataFrame,
    col: str,
    *,
    missing_mask: pd.Series,
    values: pd.Series,
) -> None:
    """Fill numeric PE columns only where values has a real number."""
    if not missing_mask.any():
        return
    mapped = pd.to_numeric(values, errors="coerce")
    fill = missing_mask & mapped.notna()
    if not fill.any():
        return
    if out[col].dtype != "float64":
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out.loc[fill, col] = mapped.loc[fill].to_numpy(dtype=float, na_value=np.nan)


def ensure_pe_ratios(
    frame: pd.DataFrame,
    *,
    max_hours: int,
    pead_max_hours: int | None = None,
) -> pd.DataFrame:
    """Fill missing PE / Fwd PE from IV cache, then PEAD2 cache."""
    if frame is None or frame.empty or "ticker" not in frame.columns:
        return frame

    out = frame.copy()
    for col in ("pe_ratio", "forward_pe"):
        if col not in out.columns:
            out[col] = pd.NA

    missing = out["pe_ratio"].isna() | out["forward_pe"].isna()
    if not missing.any():
        return out

    tickers = (
        out.loc[missing, "ticker"]
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
    )
    cached = load_cached_iv_rows(tickers, max_hours=max_hours)
    if not cached.empty:
        by_ticker = cached.copy()
        by_ticker["ticker"] = by_ticker["ticker"].astype(str).str.upper()
        by_ticker = by_ticker.drop_duplicates(subset=["ticker"], keep="last").set_index("ticker")
        keys = out["ticker"].astype(str).str.strip().str.upper()

        if "pe_ratio" in by_ticker.columns:
            _fill_pe_values(
                out,
                "pe_ratio",
                missing_mask=out["pe_ratio"].isna(),
                values=keys.map(by_ticker["pe_ratio"]),
            )
        if "forward_pe" in by_ticker.columns:
            _fill_pe_values(
                out,
                "forward_pe",
                missing_mask=out["forward_pe"].isna(),
                values=keys.map(by_ticker["forward_pe"]),
            )

    still = out["pe_ratio"].isna() | out["forward_pe"].isna()
    if still.any():
        from stocks.strategies.pead2.cache_lookup import load_pead_pe_by_ticker

        pead_hours = pead_max_hours if pead_max_hours is not None else max_hours
        pead_pe = load_pead_pe_by_ticker(
            out.loc[still, "ticker"].astype(str).str.upper().unique().tolist(),
            max_hours=pead_hours,
        )
        if pead_pe:
            keys = out["ticker"].astype(str).str.strip().str.upper()
            for col in ("pe_ratio", "forward_pe"):
                col_missing = out[col].isna()
                if not col_missing.any():
                    continue
                _fill_pe_values(
                    out,
                    col,
                    missing_mask=col_missing,
                    values=keys.map(lambda t, c=col: (pead_pe.get(t) or {}).get(c)),
                )

    return out


def load_cached_headwind_scan(
    *,
    max_hours: int,
    scan_market: str = "NSE",
    min_mcap_cr: float | None = None,
) -> dict[str, Any] | None:
    raw = load_headwind_scan_cache(
        max_hours=max_hours,
        cache_version=HEADWIND_SCAN_CACHE_VERSION,
        scan_market=scan_market,
    )
    if not raw:
        return None
    if min_mcap_cr is not None:
        cached_floor = raw.get("min_mcap_cr")
        if cached_floor is None or float(cached_floor) != float(min_mcap_cr):
            return None
    sectors = pd.DataFrame(raw.get("sectors") or [])
    if sectors.empty:
        return None
    ranked = pd.DataFrame(raw.get("ranked") or [])
    if ranked.empty:
        return None
    return {
        "ranked": ranked,
        "sectors": sectors,
        "scanned": int(raw.get("scanned") or 0),
        "with_data": int(raw.get("with_data") or len(ranked)),
        "industry_col": safe_str(raw.get("industry_col")),
        "fetched_at_display": safe_str(raw.get("fetched_at_display")),
    }


def save_cached_headwind_scan(
    result: dict[str, Any],
    *,
    scan_market: str = "NSE",
    min_mcap_cr: float | None = None,
) -> None:
    ranked = result.get("ranked")
    sectors = result.get("sectors")
    if not isinstance(sectors, pd.DataFrame) or sectors.empty:
        return
    if not isinstance(ranked, pd.DataFrame) or ranked.empty:
        return
    payload = {
        "ranked": ranked.to_dict(orient="records"),
        "sectors": sectors.to_dict(orient="records"),
        "scanned": int(result.get("scanned") or 0),
        "with_data": int(result.get("with_data") or 0),
        "industry_col": safe_str(result.get("industry_col")),
        "min_mcap_cr": float(min_mcap_cr) if min_mcap_cr is not None else None,
    }
    save_headwind_scan_cache(payload, cache_version=HEADWIND_SCAN_CACHE_VERSION, scan_market=scan_market)
