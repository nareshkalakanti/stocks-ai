"""Company profile (website/about) — saved in SQLite, screener only on first fetch."""

from __future__ import annotations

from stocks.core.database import load_company_profiles_from_db, save_company_profiles
from stocks.core.text_utils import safe_str
from stocks.market.screener_profile import fetch_screener_profile

PROFILE_KEYS = (
    "website",
    "long_description",
    "company_sector",
    "company_industry",
    "headquarters",
    "employees",
)

# Manual website fixes when Yahoo/screener miss the corporate site.
_WEBSITE_OVERRIDES: dict[str, str] = {
    "ZODIAC": "https://zodiacenergy.com/",
    "ARTEMISMED": "https://www.artemishospitals.com/",
}


def _pick_profile(data: dict) -> dict:
    out: dict = {}
    for key in PROFILE_KEYS:
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


def _profile_incomplete(data: dict) -> bool:
    return not safe_str(data.get("long_description")).strip() or not safe_str(
        data.get("website")
    ).strip()


def _apply_stored_row(target: dict, stored: dict) -> dict:
    out = dict(target)
    for key in PROFILE_KEYS:
        if out.get(key) is None and stored.get(key) is not None:
            out[key] = stored[key]
    return out


def _save_profile_if_needed(
    data: dict,
    *,
    ticker: str,
    market: str | None,
    source: str,
    stored: dict,
) -> None:
    """Persist profile fields to SQLite when the DB row is missing or incomplete."""
    payload = _pick_profile({**stored, **data})
    if not payload:
        return
    if stored and all(stored.get(k) == payload.get(k) for k in payload):
        return
    save_company_profiles(
        [
            {
                "ticker": ticker,
                "market": market or stored.get("market"),
                "source": stored.get("source") or source,
                **payload,
            }
        ]
    )


def merge_company_profile(
    data: dict,
    ticker: str,
    market: str | None,
) -> dict:
    """
    Use website/about from SQLite when present.
    Only calls screener.in when the DB row is missing website or about.
    Always saves yfinance (or merged) profile fields to SQLite.
    """
    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return dict(data)

    out = dict(data)
    override_web = _WEBSITE_OVERRIDES.get(ticker_key)
    if override_web:
        out["website"] = override_web
    stored_rows = load_company_profiles_from_db([ticker_key])
    stored = stored_rows.get(ticker_key) or {}
    out = _apply_stored_row(out, stored)

    if not _profile_incomplete(out):
        _save_profile_if_needed(
            out,
            ticker=ticker_key,
            market=market,
            source="yfinance",
            stored=stored,
        )
        return out

    scraped = fetch_screener_profile(ticker_key, market)
    if scraped:
        out = _apply_stored_row(out, scraped)
        _save_profile_if_needed(
            out,
            ticker=ticker_key,
            market=market,
            source="screener",
            stored=stored,
        )
        return out

    _save_profile_if_needed(
        out,
        ticker=ticker_key,
        market=market,
        source="yfinance",
        stored=stored,
    )
    return out


def hydrate_blob_profile(blob: dict) -> dict:
    """Attach stored profile to a PEAD2 row from SQLite; backfill DB from blob snapshot."""
    ticker = safe_str(blob.get("ticker")).upper()
    if not ticker:
        return blob
    lags = blob.get("lags")
    if not isinstance(lags, dict):
        return blob
    lag0 = lags.get("0")
    if not isinstance(lag0, dict):
        return blob
    snap = lag0.get("snapshot")
    base = dict(snap) if isinstance(snap, dict) else {}
    merged = merge_company_profile(base, ticker, blob.get("market"))
    if merged == base and not base:
        return blob
    out = dict(blob)
    new_lags = dict(lags)
    new_lag0 = dict(lag0)
    new_lag0["snapshot"] = merged
    new_lags["0"] = new_lag0
    out["lags"] = new_lags
    return out


def backfill_profiles_from_pead2_blobs(blobs: list[dict]) -> int:
    """Copy snapshot website/about/sector from PEAD2 cache blobs into company_profile_cache."""
    if not blobs:
        return 0
    tickers = [safe_str(b.get("ticker")).upper() for b in blobs if safe_str(b.get("ticker"))]
    before = load_company_profiles_from_db(tickers)
    saved = 0
    for blob in blobs:
        ticker = safe_str(blob.get("ticker")).upper()
        if not ticker:
            continue
        lag0 = (blob.get("lags") or {}).get("0")
        if not isinstance(lag0, dict):
            continue
        snap = lag0.get("snapshot")
        if not isinstance(snap, dict) or not _pick_profile(snap):
            continue
        prior = before.get(ticker) or {}
        if prior and not _profile_incomplete(prior):
            continue
        merge_company_profile(snap, ticker, blob.get("market"))
        saved += 1
    return saved
