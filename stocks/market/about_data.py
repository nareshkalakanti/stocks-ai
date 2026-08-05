"""Company about data — Yahoo + scraped About Us in ``company_profile_cache``."""

from __future__ import annotations

import pandas as pd

from stocks.core.database import (
    get_connection,
    init_db,
    load_company_profiles_from_db,
    load_stocks_from_db,
    save_company_profiles,
)
from stocks.core.text_utils import safe_str, sanitize_website
from stocks.market.company_profile import _fetch_yfinance_profile, website_override
from stocks.market.website_about_batch import scrape_and_save_about


def _preferred_about(yf_about: str, scraped_about: str, legacy: str = "") -> str:
    return scraped_about or yf_about or legacy or ""


def load_about_list(
    *,
    market: str | None = None,
    limit: int | None = None,
    missing_only: bool = False,
) -> pd.DataFrame:
    """Listings joined with website + Yahoo about + scraped About Us."""
    init_db()
    stocks = load_stocks_from_db()
    if stocks.empty:
        return pd.DataFrame()
    work = stocks.copy()
    work["ticker"] = work["ticker"].astype(str).str.strip().str.upper()
    if market and market != "All":
        work = work[work["market"].astype(str).str.upper() == market.upper()]
    work = work.drop_duplicates("ticker", keep="first")
    if limit and limit > 0:
        work = work.head(int(limit))

    tickers = work["ticker"].tolist()
    profiles = load_company_profiles_from_db(tickers)

    rows: list[dict] = []
    for _, row in work.iterrows():
        t = safe_str(row.get("ticker")).upper()
        if not t:
            continue
        prof = profiles.get(t) or {}
        yf_about = safe_str(prof.get("yf_about")).strip()
        scraped = safe_str(prof.get("scraped_about")).strip()
        legacy = safe_str(prof.get("long_description")).strip()
        # Backfill display from legacy single column when split fields empty.
        if not yf_about and not scraped and legacy:
            src = safe_str(prof.get("source")).lower()
            if src == "website_about":
                scraped = legacy
            else:
                yf_about = legacy
        website = sanitize_website(prof.get("website")) or ""
        item = {
            "ticker": t,
            "name": safe_str(row.get("name")) or t,
            "market": safe_str(row.get("market")) or safe_str(prof.get("market")) or "",
            "website": website,
            "yf_about": yf_about,
            "scraped_about": scraped,
            "about": _preferred_about(yf_about, scraped, legacy),
            "source": safe_str(prof.get("source")),
            "has_yf": bool(yf_about),
            "has_scraped": bool(scraped),
            "has_web": bool(website),
        }
        if missing_only and item["has_yf"] and item["has_scraped"] and item["has_web"]:
            continue
        rows.append(item)

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["market", "ticker"]).reset_index(drop=True)


def refresh_yahoo_about(
    tickers: list[str],
    *,
    markets: dict[str, str] | None = None,
    progress_callback=None,
) -> dict[str, int]:
    """Fetch Yahoo ``longBusinessSummary`` into ``yf_about`` for each ticker."""
    markets = markets or {}
    ok = err = skip = 0
    total = len(tickers)
    for i, raw in enumerate(tickers, start=1):
        ticker = safe_str(raw).upper()
        if progress_callback:
            try:
                progress_callback(i - 1, total, ticker)
            except Exception:
                pass
        if not ticker:
            skip += 1
            continue
        market = markets.get(ticker) or "NSE"
        try:
            yf = _fetch_yfinance_profile(ticker, market)
        except Exception:
            err += 1
            continue
        about = safe_str(yf.get("yf_about") or yf.get("long_description")).strip()
        website = sanitize_website(yf.get("website")) or website_override(ticker)
        if not about and not website:
            err += 1
            continue
        stored = load_company_profiles_from_db([ticker]).get(ticker) or {}
        scraped = safe_str(stored.get("scraped_about")).strip()
        legacy = safe_str(stored.get("long_description")).strip()
        payload = {
            "ticker": ticker,
            "market": market or stored.get("market"),
            "website": website or sanitize_website(stored.get("website")),
            "yf_about": about or None,
            "scraped_about": scraped or None,
            "long_description": _preferred_about(about, scraped, legacy) or None,
            "company_sector": yf.get("company_sector") or stored.get("company_sector"),
            "company_industry": yf.get("company_industry") or stored.get("company_industry"),
            "headquarters": yf.get("headquarters") or stored.get("headquarters"),
            "employees": yf.get("employees") or stored.get("employees"),
            "theme_tags": yf.get("theme_tags") or stored.get("theme_tags"),
            "end_markets": yf.get("end_markets") or stored.get("end_markets"),
            "source": stored.get("source") or "yfinance",
        }
        save_company_profiles([payload])
        ok += 1
    if progress_callback:
        try:
            progress_callback(total, total, "")
        except Exception:
            pass
    return {"tried": total, "ok": ok, "errors": err, "skipped": skip}


def refresh_scraped_about(
    tickers: list[str],
    *,
    markets: dict[str, str] | None = None,
    names: dict[str, str] | None = None,
    force: bool = False,
    progress_callback=None,
) -> dict[str, int]:
    """Scrape corporate About Us into ``scraped_about``."""
    markets = markets or {}
    names = names or {}
    ok = err = skip = 0
    total = len(tickers)
    for i, raw in enumerate(tickers, start=1):
        ticker = safe_str(raw).upper()
        if progress_callback:
            try:
                progress_callback(i - 1, total, ticker)
            except Exception:
                pass
        if not ticker:
            skip += 1
            continue
        result = scrape_and_save_about(
            ticker,
            markets.get(ticker) or "NSE",
            force=force,
            company_name=names.get(ticker),
        )
        if result.get("skipped"):
            skip += 1
        elif result.get("ok"):
            ok += 1
        else:
            err += 1
    if progress_callback:
        try:
            progress_callback(total, total, "")
        except Exception:
            pass
    return {"tried": total, "ok": ok, "errors": err, "skipped": skip}


def about_coverage_stats(df: pd.DataFrame | None = None) -> dict[str, int]:
    view = df if df is not None else load_about_list()
    if view is None or view.empty:
        return {"total": 0, "website": 0, "yf_about": 0, "scraped_about": 0, "both": 0}
    return {
        "total": int(len(view)),
        "website": int(view["has_web"].sum()) if "has_web" in view.columns else 0,
        "yf_about": int(view["has_yf"].sum()) if "has_yf" in view.columns else 0,
        "scraped_about": int(view["has_scraped"].sum()) if "has_scraped" in view.columns else 0,
        "both": int(((view.get("has_yf") == True) & (view.get("has_scraped") == True)).sum())
        if "has_yf" in view.columns and "has_scraped" in view.columns
        else 0,
    }


def migrate_legacy_about_columns() -> int:
    """Copy ``long_description`` into yf_about / scraped_about when those are empty."""
    init_db()
    with get_connection() as conn:
        # Ensure columns exist (init_db / ensure columns).
        cols = {row[1] for row in conn.execute("PRAGMA table_info(company_profile_cache)")}
        if "yf_about" not in cols or "scraped_about" not in cols:
            return 0
        cur = conn.execute(
            """
            UPDATE company_profile_cache
            SET scraped_about = long_description
            WHERE (scraped_about IS NULL OR TRIM(scraped_about) = '')
              AND long_description IS NOT NULL AND TRIM(long_description) != ''
              AND LOWER(COALESCE(source, '')) = 'website_about'
            """
        )
        n1 = cur.rowcount or 0
        cur = conn.execute(
            """
            UPDATE company_profile_cache
            SET yf_about = long_description
            WHERE (yf_about IS NULL OR TRIM(yf_about) = '')
              AND long_description IS NOT NULL AND TRIM(long_description) != ''
              AND LOWER(COALESCE(source, '')) != 'website_about'
            """
        )
        n2 = cur.rowcount or 0
    return int(n1 + n2)
