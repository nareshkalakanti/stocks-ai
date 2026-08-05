"""Company profile (website/about) — saved in SQLite, screener only on first fetch."""

from __future__ import annotations

import yfinance as yf

from stocks.core.database import load_company_profiles_from_db, save_company_profiles, save_market_cap_to_db
from stocks.core.config import YFINANCE_REQUEST_DELAY
from stocks.core.text_utils import safe_str, sanitize_website
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.screener_profile import fetch_screener_profile
from stocks.market.yfinance_limits import call_throttled

PROFILE_KEYS = (
    "website",
    "long_description",
    "yf_about",
    "scraped_about",
    "company_sector",
    "company_industry",
    "headquarters",
    "employees",
    "products",
    "end_markets",
    "ir_url",
    "theme_tags",
    "website_status",
)

# Manual website fixes when Yahoo/screener miss the corporate site.
_WEBSITE_OVERRIDES: dict[str, str] = {
    "ZODIAC": "https://zodiacenergy.com/",
    "ARTEMISMED": "https://www.artemishospitals.com/",
    "AARTECH": "https://www.aartechsolonics.com/",
    "INA": "https://www.insolationenergy.in/",
    # Screener only links Google search; Yahoo/corporate site known.
    "VAML": "https://www.vedantalimited.com/",
    "CLEANMAX": "https://www.cleanmax.com/",
    "ASHIKAG": "https://www.ashikagroup.com/",
    "KLBRENG-B": "https://www.kilburnengg.com/",
    "MCCHRLS-B": "https://www.maccharlesindia.com/",
    "SINGERIND": "https://www.singerindia.com/",
    "TAALTECH": "https://www.taaltech.com/",
    "FINCABLES": "https://finolex.com/",
    "ECLERX": "https://www.eclerx.com/",
    "POLYPLEX": "https://www.polyplex.com/",
    "SUBEXLTD": "https://www.subex.com/",
    "FILATEX": "https://www.filatex.com/",
    "BBOX": "https://www.blackbox.com/",
    "APCOTEXIND": "https://www.apcotex.com/",
    "FCL": "https://www.fineotex.com/",
    "INDOBORAX": "https://www.indoborax.com/",
    "BANSWRAS": "https://www.banswarasyntex.com/",
    "AYMSYNTEX": "https://www.aymsyntex.com/",
    "STYRENIX": "https://www.styrenix.com/",
    "ABSLAMC": "https://mutualfund.adityabirlacapital.com/",
    "NPST": "https://www.npstx.com/",
    "HEXATRADEX": "https://www.hexatradex.com/",
    "LAGNAM": "https://www.lagnamspintex.com/",
    "RELCHEMQ": "https://www.relchemotex.com/",
    "ORIENTALTL": "https://www.orientaltrimex.com/",
    "RUDRA": "https://www.rudraglobal.com/",
    "MAHAPEXLTD": "https://www.maharashtraapex.com/",
    "BSE": "https://www.bseindia.com/",
    "SRTL": "https://www.shreeramtwistex.com/",
    "AASTHA": "https://www.aastha-spintex.com/",
    "NIMBSPROJ": "https://www.nimbusprojectsltd.com/",
    "GRANDOAK": "https://www.pifl.in/",
}


def website_override(ticker: str) -> str | None:
    """Manual corporate website for a ticker, if configured."""
    raw = safe_str(_WEBSITE_OVERRIDES.get(safe_str(ticker).upper()))
    if not raw:
        return None
    cleaned = sanitize_website(raw)
    # Trust explicit overrides even when host is normally filtered (e.g. BSE → bseindia.com).
    if cleaned:
        return cleaned
    if raw.startswith(("http://", "https://")):
        return raw if raw.endswith("/") else raw + "/"
    return f"https://{raw}"



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
    return (
        not safe_str(data.get("long_description")).strip()
        or not sanitize_website(data.get("website"))
        or not safe_str(data.get("company_sector")).strip()
        or not safe_str(data.get("company_industry")).strip()
    )


def _apply_stored_row(target: dict, stored: dict) -> dict:
    out = dict(target)
    for key in PROFILE_KEYS:
        if out.get(key) is None and stored.get(key) is not None:
            value = stored[key]
            if key == "website":
                value = sanitize_website(value)
            out[key] = value
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


def _fetch_yfinance_profile(ticker: str, market: str | None) -> dict:
    """Best-effort website + about + sector/HQ from Yahoo when screener omits them."""
    symbol = to_yfinance_symbol(ticker, market)
    try:
        info = call_throttled(
            lambda: yf.Ticker(symbol).info,
            delay=YFINANCE_REQUEST_DELAY,
        ) or {}
    except Exception:
        return {}
    if not isinstance(info, dict):
        return {}
    out: dict = {}
    website = sanitize_website(info.get("website"))
    if website:
        out["website"] = website
    about = safe_str(info.get("longBusinessSummary")).strip()
    if about:
        out["long_description"] = about
        out["yf_about"] = about
    sector = safe_str(info.get("sector") or info.get("sectorDisp")).strip()
    if sector:
        out["company_sector"] = sector
    industry = safe_str(info.get("industry") or info.get("industryDisp")).strip()
    if industry:
        out["company_industry"] = industry
    employees = info.get("fullTimeEmployees")
    try:
        if employees is not None and int(employees) > 0:
            out["employees"] = int(employees)
    except (TypeError, ValueError):
        pass
    hq_bits = [
        safe_str(info.get("address1")),
        safe_str(info.get("city")),
        safe_str(info.get("state")),
        safe_str(info.get("country")),
    ]
    hq = ", ".join(b for b in hq_bits if b)
    if hq:
        out["headquarters"] = hq
    # Theme / end-market tags from Yahoo about (same tagger as website scrape).
    if about:
        try:
            from stocks.market.website_about import extract_end_markets, extract_theme_tags

            tags = extract_theme_tags(about, industry, sector)
            markets = extract_end_markets(about, industry, sector)
            if tags:
                out["theme_tags"] = tags
            if markets:
                out["end_markets"] = markets
        except Exception:
            pass
    raw_mcap = info.get("marketCap")
    try:
        if raw_mcap is not None:
            val = float(raw_mcap)
            if val > 0:
                out["market_cap_cr"] = round(val / 1e7, 1)
    except (TypeError, ValueError):
        pass
    return out


def merge_company_profile(
    data: dict,
    ticker: str,
    market: str | None,
) -> dict:
    """
    Use website/about from SQLite when present.
    Only calls screener.in / Yahoo when the DB row is missing website or about.
    Always saves yfinance (or merged) profile fields to SQLite.
    """
    ticker_key = safe_str(ticker).upper()
    if not ticker_key:
        return dict(data)

    out = dict(data)
    override_web = _WEBSITE_OVERRIDES.get(ticker_key)
    if override_web:
        out["website"] = override_web
    if out.get("website") is not None:
        out["website"] = sanitize_website(out.get("website"))
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

    source = "yfinance"
    scraped = fetch_screener_profile(ticker_key, market)
    if scraped:
        mcap = scraped.pop("market_cap_cr", None)
        out = _apply_stored_row(out, scraped)
        source = "screener"
        if mcap is not None:
            try:
                save_market_cap_to_db(
                    ticker_key,
                    float(mcap),
                    market=market,
                )
            except Exception:
                pass

    # Screener often only has a Google "Company website" search — fill from Yahoo.
    if _profile_incomplete(out):
        yf_profile = _fetch_yfinance_profile(ticker_key, market)
        if yf_profile:
            yf_mcap = yf_profile.pop("market_cap_cr", None)
            out = _apply_stored_row(out, yf_profile)
            if source != "screener":
                source = "yfinance"
            if yf_mcap is not None:
                try:
                    save_market_cap_to_db(
                        ticker_key,
                        float(yf_mcap),
                        market=market,
                    )
                except Exception:
                    pass

    if override_web and not sanitize_website(out.get("website")):
        out["website"] = override_web

    _save_profile_if_needed(
        out,
        ticker=ticker_key,
        market=market,
        source=source,
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
