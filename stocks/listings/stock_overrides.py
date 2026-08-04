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

# Sector / industry fixes when sqlite taxonomy is wrong (optional market / name match).
# Prefer Screener peer buckets where checked.
_CLASSIFICATION_OVERRIDES: tuple[dict[str, str], ...] = (
    {
        "ticker": "KIRLOSIND",
        "sector": "Industrials",
        "industry": "Iron & Steel Products",
        "sub_sector": "Iron & Steel Products",
    },
    {
        # BSE SME castings / containers — not Consumer Finance (ticker collides with NSE commercials).
        "ticker": "KALYANI",
        "market": "BSE",
        "name_contains": "Cast-Tech",
        "sector": "Industrials",
        "industry": "Castings & Containers",
        "sub_sector": "Castings & Containers",
    },
    {
        # NSE — commercial vehicle / petroleum dealer, surrendered NBFC.
        "ticker": "KALYANI",
        "market": "NSE",
        "name_contains": "Commercial",
        "sector": "Automobile & Ancillaries",
        "industry": "Dealers-Commercial Vehicles",
        "sub_sector": "Dealers-Commercial Vehicles",
    },
    {
        # Healthcare ITES / US payer BPO — not Specialized Finance.
        "ticker": "SAGILITY",
        "sector": "IT & Technology",
        "industry": "IT Enabled Services",
        "sub_sector": "IT Enabled Services",
    },
    {
        # e-Governance / commercial services — not Investment Banking.
        "ticker": "ALANKIT",
        "sector": "Commercial & Business Services",
        "industry": "Diversified Commercial Services",
        "sub_sector": "Diversified Commercial Services",
    },
    {
        # NSE SME biodiesel — not Investment Banking (ticker collides with BSE finance name).
        "ticker": "RAJPUTANA",
        "name_contains": "Biodiesel",
        "sector": "Oil & Gas & Energy",
        "industry": "Biofuels",
        "sub_sector": "Biofuels",
    },
    {
        # IT / ITES holding — not Capital Markets.
        "ticker": "UNITEDINT",
        "sector": "IT & Technology",
        "industry": "IT Enabled Services",
        "sub_sector": "IT Enabled Services",
    },
    {
        # NSE SME power / industrial cables (Vidhut Cables).
        "ticker": "BHADORA",
        "market": "NSE SME",
        "name": "Bhadora Industries Limited",
        "sector": "Capital Goods",
        "industry": "Cables",
        "sub_sector": "Cables",
    },
    {
        # NSE SME LT power / control / AB cables.
        "ticker": "PRIMECAB",
        "market": "NSE SME",
        "name": "Prime Cable Industries Limited",
        "sector": "Capital Goods",
        "industry": "Cables",
        "sub_sector": "Cables",
    },
    {
        # BSE SME digital textile printing machines + consumables.
        "ticker": "TRUECOLORS",
        "market": "BSE",
        "name": "True Colors Limited",
        "sector": "Capital Goods",
        "industry": "Industrial Machinery",
        "sub_sector": "Industrial Machinery",
    },
    {
        "ticker": "ASHIKAG",
        "sector": "Banking & Finance",
        "industry": "Non Banking Financial Company (NBFC)",
        "sub_sector": "Non Banking Financial Company (NBFC)",
    },
    {
        "ticker": "GRANDOAK",
        "sector": "FMCG & Consumer Goods",
        "industry": "Breweries & Distilleries",
        "sub_sector": "Breweries & Distilleries",
    },
    {
        "ticker": "KLBRENG-B",
        "sector": "Engineering & Capital Goods",
        "industry": "Industrial Products",
        "sub_sector": "Industrial Products",
    },
    {
        "ticker": "MCCHRLS-B",
        "sector": "Hotels, Tourism & Leisure",
        "industry": "Hotels & Resorts",
        "sub_sector": "Hotels & Resorts",
    },
    {
        "ticker": "SINGERIND",
        "sector": "Consumer Durables",
        "industry": "Household Appliances",
        "sub_sector": "Household Appliances",
    },
    {
        "ticker": "TAALTECH",
        "sector": "IT & Technology",
        "industry": "IT Consulting & Software",
        "sub_sector": "IT Consulting & Software",
    },
    {
        "ticker": "BGLOBAL",
        "sector": "IT & Technology",
        "industry": "IT Services",
        "sub_sector": "IT Services",
    },
    {
        "ticker": "CMICABLES",
        "sector": "Engineering & Capital Goods",
        "industry": "Cables",
        "sub_sector": "Cables",
    },
    {
        "ticker": "GENSOL",
        "sector": "Power & Utilities",
        "industry": "Renewable Energy Equipment & Services",
        "sub_sector": "Renewable Energy Equipment & Services",
    },
    {
        "ticker": "SKIL",
        "sector": "Real Estate & Construction",
        "industry": "Construction & Engineering",
        "sub_sector": "Construction & Engineering",
    },
    {
        "ticker": "CLCIND",
        "sector": "Textiles & Apparel",
        "industry": "Textile Manufacturing",
        "sub_sector": "Textile Manufacturing",
    },
    {
        "ticker": "DSKULKARNI",
        "sector": "Real Estate & Construction",
        "industry": "Real Estate - Development",
        "sub_sector": "Real Estate - Development",
    },
)


def classification_overrides() -> tuple[dict[str, str], ...]:
    """Ticker classification patches (also applied when refreshing sqlite DBs)."""
    return _CLASSIFICATION_OVERRIDES


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
    for rule in _CLASSIFICATION_OVERRIDES:
        if safe_str(rule.get("ticker")).upper() != key:
            continue
        if rule.get("name_contains"):
            continue  # ambiguous without company-name context
        for col in ("sector", "industry", "sub_sector"):
            val = safe_str(rule.get(col))
            if val:
                out[col] = val
        name = safe_str(rule.get("name"))
        if name and "name" not in out:
            out["name"] = name
        break
    return out


def _apply_classification_overrides(out: pd.DataFrame) -> pd.DataFrame:
    if out.empty or not _CLASSIFICATION_OVERRIDES:
        return out
    tickers = out["ticker"].astype(str).str.upper()
    markets = (
        out["market"].astype(str).str.upper()
        if "market" in out.columns
        else pd.Series("", index=out.index)
    )
    names = out["name"].astype(str) if "name" in out.columns else pd.Series("", index=out.index)
    for rule in _CLASSIFICATION_OVERRIDES:
        ticker = safe_str(rule.get("ticker")).upper()
        if not ticker:
            continue
        mask = tickers == ticker
        market = safe_str(rule.get("market")).upper()
        if market:
            mask &= markets == market
        name_contains = safe_str(rule.get("name_contains"))
        if name_contains:
            mask &= names.str.contains(name_contains, case=False, na=False)
        if not mask.any():
            continue
        for col in ("sector", "industry", "sub_sector"):
            val = safe_str(rule.get(col))
            if val:
                out.loc[mask, col] = val
    return out


def apply_stock_overrides(stocks: pd.DataFrame) -> pd.DataFrame:
    if stocks.empty and not _REQUIRED_NSE and not _CLASSIFICATION_OVERRIDES:
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

    return _apply_classification_overrides(out)
