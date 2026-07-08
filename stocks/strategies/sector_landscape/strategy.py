"""Group labels and equal-weight sector index math."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str

# Short names for industry card titles (Pharma - CDMO style).
_SECTOR_SHORT: dict[str, str] = {
    "Pharmaceuticals & Healthcare": "Pharma",
    "Automobile & Ancillaries": "Auto",
    "Banking & Finance": "Finance",
    "IT & Technology": "IT",
    "FMCG & Consumer Goods": "FMCG",
    "Consumer Durables": "Durables",
    "Real Estate & Construction": "Realty",
    "Metals & Mining": "Metals",
    "Oil & Gas & Energy": "Energy",
    "Power & Utilities": "Power",
    "Chemicals & Petrochemicals": "Chemicals",
    "Textiles & Apparel": "Textiles",
    "Media & Entertainment": "Media",
    "Transportation & Logistics": "Transport",
    "Hotels, Tourism & Leisure": "Hotels",
    "Telecom": "Telecom",
    "Agriculture & Agro": "Agri",
    "Engineering & Capital Goods": "Engineering",
    "Commercial & Business Services": "Services",
    "Retail": "Retail",
    "Diversified & Others": "Diversified",
}


def sector_short_name(sector: str) -> str:
    sector = safe_str(sector)
    if not sector:
        return ""
    return _SECTOR_SHORT.get(sector, sector.split("&")[0].strip().split()[0])


def group_key(sector: str, industry: str, *, kind: str) -> str:
    """Return grouping label for sector or industry mode."""
    sector = safe_str(sector)
    industry = safe_str(industry)
    if kind == "sector":
        return sector or "Unknown"
    short = sector_short_name(sector)
    if industry and industry != sector:
        return f"{short} - {industry}" if short else industry
    return sector or industry or "Unknown"


def rebase_100(close: pd.Series) -> pd.Series:
    s = close.dropna().astype(float)
    if len(s) < 2:
        return pd.Series(dtype=float)
    base = float(s.iloc[0])
    if base == 0:
        return pd.Series(dtype=float)
    return (s / base) * 100.0


def total_return_pct(close: pd.Series) -> float | None:
    s = close.dropna().astype(float)
    if len(s) < 2:
        return None
    base = float(s.iloc[0])
    if base == 0:
        return None
    return round((float(s.iloc[-1]) / base - 1.0) * 100.0, 2)


def equal_weight_index(series_map: dict[str, pd.Series]) -> pd.Series:
    """Equal-weight rebased index across stocks (100 at first common week)."""
    if not series_map:
        return pd.Series(dtype=float)
    rebased: dict[str, pd.Series] = {}
    for ticker, close in series_map.items():
        if close is None or close.empty:
            continue
        rb = rebase_100(close)
        if not rb.empty:
            rebased[ticker] = rb
    if not rebased:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(rebased)
    return frame.mean(axis=1, skipna=True).dropna()


def series_to_points(series: pd.Series, *, max_points: int = 48) -> list[dict]:
    """Downsample a price series for chart JSON."""
    s = series.dropna()
    if s.empty:
        return []
    if len(s) > max_points:
        step = max(1, len(s) // max_points)
        s = s.iloc[::step]
    out: list[dict] = []
    for ts, val in s.items():
        if pd.isna(val):
            continue
        label = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        out.append({"d": label, "v": round(float(val), 2)})
    return out
