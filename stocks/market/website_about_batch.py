"""Batch scrape About Us for NSE / NSE SME listings into company_profile_cache."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from stocks.core.config import DATA_DIR, WEB_ABOUT_MAX_PAGES, WEB_ABOUT_REQUEST_DELAY
from stocks.core.database import (
    _write_lock,
    get_connection,
    init_db,
    load_company_profiles_from_db,
    save_company_profiles,
)
from stocks.core.text_utils import safe_str, sanitize_website
from stocks.listings.stocks_data import apply_market_column_filter, load_india_stocks
from stocks.market.company_profile import _fetch_yfinance_profile, website_override
from stocks.market.screener_profile import fetch_screener_profile
from stocks.market.website_about import scrape_website_about, verify_corporate_website
from stocks.market.website_search import search_corporate_website

WEBSITE_STATUS_OK = "ok"
WEBSITE_STATUS_NOT_FOUND = "not_found"


def _profile_row(
    ticker: str,
    market: str | None,
    *,
    website: str | None,
    about: str | None,
    source: str,
    stored: dict | None = None,
    products: str | None = None,
    end_markets: str | None = None,
    ir_url: str | None = None,
    theme_tags: str | None = None,
    website_status: str | None = None,
    yf_about: str | None = None,
    scraped_about: str | None = None,
) -> dict:
    base = dict(stored or {})

    def _pick(new: str | None, key: str) -> str | None:
        if new is not None:
            text = safe_str(new).strip()
            return text or None  # "" clears stored value
        return safe_str(base.get(key)).strip() or None

    status = website_status
    if status is None:
        status = WEBSITE_STATUS_OK if sanitize_website(website or base.get("website")) else (
            safe_str(base.get("website_status")) or None
        )

    scraped = (
        safe_str(scraped_about).strip()
        if scraped_about is not None
        else (
            safe_str(about).strip()
            if about is not None and source == "website_about"
            else safe_str(base.get("scraped_about")).strip()
        )
    ) or None
    yf = (
        safe_str(yf_about).strip()
        if yf_about is not None
        else safe_str(base.get("yf_about")).strip()
    ) or None
    preferred = scraped or yf or (
        safe_str(about).strip()
        if about is not None
        else safe_str(base.get("long_description")).strip()
    ) or None

    return {
        "ticker": ticker,
        "market": market or base.get("market"),
        "website": (
            sanitize_website(website)
            if website is not None
            else sanitize_website(base.get("website"))
        ),
        "long_description": preferred,
        "yf_about": yf,
        "scraped_about": scraped,
        "company_sector": base.get("company_sector"),
        "company_industry": base.get("company_industry"),
        "headquarters": base.get("headquarters"),
        "employees": base.get("employees"),
        "source": source or base.get("source") or "website_about",
        "products": _pick(products, "products"),
        "end_markets": _pick(end_markets, "end_markets"),
        "ir_url": _pick(ir_url, "ir_url"),
        "theme_tags": _pick(theme_tags, "theme_tags"),
        "website_status": status,
    }


def resolve_website(
    ticker: str,
    market: str | None,
    *,
    stored: dict | None = None,
    verify: bool = True,
    company_name: str | None = None,
    use_web_search: bool = True,
) -> tuple[str | None, str]:
    """
    Find a proper corporate website.

    Order: manual override → cache → Yahoo → screener → public web search.
    Optionally verify the URL loads. Returns (website, source_hint).
    """
    key = safe_str(ticker).upper()
    prof = stored if stored is not None else (load_company_profiles_from_db([key]).get(key) or {})

    candidates: list[tuple[str, str, dict]] = []

    override = website_override(key)
    if override:
        candidates.append((override, "override", prof))

    cached = sanitize_website(prof.get("website"))
    if cached and cached != override:
        candidates.append((cached, "cache", prof))

    yf_prof = _fetch_yfinance_profile(key, market) or {}
    yf_web = sanitize_website(yf_prof.get("website"))
    if yf_web and yf_web not in {cached, override}:
        candidates.append(
            (
                yf_web,
                "yfinance",
                {**prof, **{k: v for k, v in yf_prof.items() if k != "market_cap_cr"}},
            )
        )

    scraped = fetch_screener_profile(key, market) or {}
    sc_web = sanitize_website(scraped.get("website"))
    if sc_web and sc_web not in {cached, yf_web, override}:
        candidates.append((sc_web, "screener", {**prof, **scraped}))

    for web, src, meta in candidates:
        if verify and src != "override":
            ok_url, err = verify_corporate_website(web)
            if not ok_url:
                continue
            web = ok_url
        elif src == "override":
            # Manual override is trusted; normalize if reachable, else keep as given.
            ok_url, _err = verify_corporate_website(web)
            if ok_url:
                web = ok_url
        about = (
            safe_str(prof.get("long_description"))
            or safe_str(meta.get("long_description"))
            or None
        )
        save_company_profiles(
            [
                _profile_row(
                    key,
                    market,
                    website=web,
                    about=about,
                    source=src if src != "cache" else (safe_str(prof.get("source")) or src),
                    stored=meta,
                    end_markets=meta.get("end_markets") or prof.get("end_markets"),
                    theme_tags=meta.get("theme_tags") or prof.get("theme_tags"),
                    products=prof.get("products"),
                    ir_url=prof.get("ir_url"),
                    website_status=WEBSITE_STATUS_OK,
                )
            ]
        )
        return web, src

    if use_web_search:
        name = safe_str(company_name) or safe_str(prof.get("name")) or key
        web, src = search_corporate_website(name, ticker=key)
        if web:
            save_company_profiles(
                [
                    _profile_row(
                        key,
                        market,
                        website=web,
                        about=safe_str(prof.get("long_description")) or None,
                        source=src,
                        stored=prof,
                        website_status=WEBSITE_STATUS_OK,
                    )
                ]
            )
            return web, src

    return None, "none"


def find_and_save_website(
    ticker: str,
    market: str | None = None,
    *,
    force: bool = False,
    company_name: str | None = None,
) -> dict:
    """Step 1 only: resolve + verify corporate website and save to DB."""
    key = safe_str(ticker).upper()
    market_key = safe_str(market).upper() or "NSE"
    stored = load_company_profiles_from_db([key]).get(key) or {}
    status = safe_str(stored.get("website_status"))
    existing = sanitize_website(stored.get("website"))

    if status == WEBSITE_STATUS_NOT_FOUND and not force:
        return {
            "ticker": key,
            "market": market_key,
            "ok": False,
            "skipped": True,
            "reason": "marked_not_found",
            "website": None,
            "website_status": WEBSITE_STATUS_NOT_FOUND,
            "fill_source": "cache",
        }

    if existing and not force:
        ok_url, err = verify_corporate_website(existing)
        if ok_url:
            if status != WEBSITE_STATUS_OK:
                save_company_profiles(
                    [
                        _profile_row(
                            key,
                            market_key,
                            website=ok_url,
                            about=safe_str(stored.get("long_description")) or None,
                            source=safe_str(stored.get("source")) or "cache",
                            stored=stored,
                            website_status=WEBSITE_STATUS_OK,
                        )
                    ]
                )
            return {
                "ticker": key,
                "market": market_key,
                "ok": True,
                "skipped": True,
                "reason": "already_have_website",
                "website": ok_url,
                "website_status": WEBSITE_STATUS_OK,
                "fill_source": "cache",
            }
        # Cached URL is bad — fall through and rediscover.

    web, src = resolve_website(
        key,
        market_key,
        stored=stored,
        verify=True,
        company_name=company_name,
        use_web_search=True,
    )
    if not web:
        # Mark so Find websites does not retry until Force refresh.
        save_company_profiles(
            [
                _profile_row(
                    key,
                    market_key,
                    website="",
                    about=safe_str(stored.get("long_description")) or None,
                    source="no_website",
                    stored=stored,
                    website_status=WEBSITE_STATUS_NOT_FOUND,
                )
            ]
        )
        return {
            "ticker": key,
            "market": market_key,
            "ok": False,
            "skipped": False,
            "reason": "no_proper_website",
            "website": None,
            "website_status": WEBSITE_STATUS_NOT_FOUND,
            "fill_source": "none",
        }
    return {
        "ticker": key,
        "market": market_key,
        "ok": True,
        "skipped": False,
        "reason": "saved_website",
        "website": web,
        "website_status": WEBSITE_STATUS_OK,
        "fill_source": src,
    }


def listings_for_markets(markets: list[str]) -> pd.DataFrame:
    """NSE / NSE SME listing rows from local stocks DB."""
    stocks = load_india_stocks()
    if stocks is None or stocks.empty:
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for m in markets:
        part = apply_market_column_filter(stocks, m)
        if part is not None and not part.empty:
            frames.append(part)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    if "ticker" in out.columns:
        out["ticker"] = out["ticker"].astype(str).str.strip().str.upper()
        out = out.drop_duplicates(subset=["ticker"], keep="first")
    return out


def about_gap_tickers(
    listings: pd.DataFrame,
    *,
    missing_about_only: bool = True,
    missing_website_only: bool = False,
    refresh_existing: bool = False,
) -> pd.DataFrame:
    """Filter listings that still need website discovery and/or About scrape.

    Tickers marked ``website_status=not_found`` are skipped unless Force refresh.
    """
    if listings is None or listings.empty:
        return pd.DataFrame()
    tickers = listings["ticker"].astype(str).str.upper().tolist()
    profiles = load_company_profiles_from_db(tickers)
    rows: list[dict] = []
    for _, row in listings.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        prof = profiles.get(ticker) or {}
        about = safe_str(prof.get("long_description")).strip()
        website = sanitize_website(prof.get("website"))
        source = safe_str(prof.get("source"))
        site_status = safe_str(prof.get("website_status"))
        if (
            not refresh_existing
            and site_status == WEBSITE_STATUS_NOT_FOUND
            and not website
        ):
            continue
        if refresh_existing:
            need = True
        elif missing_website_only:
            need = not website
        elif missing_about_only:
            need = not about
        else:
            need = not about or not website
        if not refresh_existing and source == "website_about" and about and not missing_website_only:
            need = False
        if not need:
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": safe_str(row.get("name")) or ticker,
                "market": safe_str(row.get("market")) or "NSE",
                "sector": safe_str(row.get("sector")),
                "has_about": bool(about),
                "has_website": bool(website),
                "website": website or "",
                "website_status": site_status,
                "source": source,
            }
        )
    return pd.DataFrame(rows)


def website_not_found_rows(listings: pd.DataFrame) -> pd.DataFrame:
    """Listings marked website not_found (skipped until Force refresh)."""
    if listings is None or listings.empty:
        return pd.DataFrame()
    tickers = listings["ticker"].astype(str).str.upper().tolist()
    profiles = load_company_profiles_from_db(tickers)
    official = official_nse_symbols()
    rows: list[dict] = []
    for _, row in listings.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        prof = profiles.get(ticker) or {}
        if safe_str(prof.get("website_status")) != WEBSITE_STATUS_NOT_FOUND:
            continue
        if sanitize_website(prof.get("website")):
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": safe_str(row.get("name")) or ticker,
                "market": safe_str(row.get("market")) or "NSE",
                "sector": safe_str(row.get("sector")),
                "source": safe_str(prof.get("source")) or "no_website",
                "website_status": WEBSITE_STATUS_NOT_FOUND,
                "listed": ticker in official,
            }
        )
    return pd.DataFrame(rows)


def count_website_not_found(listings: pd.DataFrame) -> int:
    """How many listings are marked website not found (no retry until Force refresh)."""
    return len(website_not_found_rows(listings))


def official_nse_symbols() -> set[str]:
    """Symbols from cached NSE mainboard + SME equity CSVs."""
    out: set[str] = set()
    for name in ("nse_equity_l.csv", "nse_sme_equity.csv"):
        path = Path(DATA_DIR) / name
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if "SYMBOL" not in df.columns:
            continue
        out.update(df["SYMBOL"].astype(str).str.strip().str.upper().tolist())
    return out


def purge_non_listed_tickers(tickers: list[str]) -> dict:
    """Remove tickers not on NSE equity/SME CSV from stocks + profile cache."""
    official = official_nse_symbols()
    victims = sorted(
        {
            safe_str(t).upper()
            for t in tickers
            if safe_str(t).upper() and safe_str(t).upper() not in official
        }
    )
    if not victims:
        return {"checked": len(tickers), "removed": 0, "tickers": []}

    init_db()
    with _write_lock:
        with get_connection() as conn:
            for t in victims:
                conn.execute("DELETE FROM company_profile_cache WHERE ticker = ?", (t,))
                conn.execute("DELETE FROM stocks WHERE UPPER(ticker) = ?", (t,))
                try:
                    conn.execute(
                        "DELETE FROM business_group_members WHERE UPPER(ticker) = ?",
                        (t,),
                    )
                except Exception:
                    pass
    return {"checked": len(tickers), "removed": len(victims), "tickers": victims}


def scrape_and_save_about(
    ticker: str,
    market: str | None = None,
    *,
    force: bool = False,
    company_name: str | None = None,
) -> dict:
    """Resolve corporate website if needed, then scrape About text into SQLite."""
    key = safe_str(ticker).upper()
    market_key = safe_str(market).upper() or "NSE"
    stored = load_company_profiles_from_db([key]).get(key) or {}
    status = safe_str(stored.get("website_status"))
    if status == WEBSITE_STATUS_NOT_FOUND and not force and not sanitize_website(stored.get("website")):
        return {
            "ticker": key,
            "market": market_key,
            "ok": False,
            "skipped": True,
            "reason": "marked_not_found",
            "website": None,
            "website_status": WEBSITE_STATUS_NOT_FOUND,
            "chars": 0,
            "fill_source": "cache",
        }

    existing_scraped = safe_str(stored.get("scraped_about")).strip()
    existing_about = existing_scraped or safe_str(stored.get("long_description")).strip()
    if existing_scraped and not force:
        return {
            "ticker": key,
            "market": market_key,
            "ok": True,
            "skipped": True,
            "reason": "already_have_scraped_about",
            "website": sanitize_website(stored.get("website")),
            "chars": len(existing_scraped),
            "fill_source": "cache",
        }
    if (
        existing_about
        and safe_str(stored.get("source")) == "website_about"
        and not force
        and not existing_scraped
    ):
        # Legacy row — promote long_description into scraped_about once.
        save_company_profiles(
            [
                _profile_row(
                    key,
                    market_key,
                    website=sanitize_website(stored.get("website")),
                    about=existing_about,
                    source="website_about",
                    stored=stored,
                    scraped_about=existing_about,
                )
            ]
        )
        return {
            "ticker": key,
            "market": market_key,
            "ok": True,
            "skipped": True,
            "reason": "promoted_legacy_scraped_about",
            "website": sanitize_website(stored.get("website")),
            "chars": len(existing_about),
            "fill_source": "cache",
        }

    # 1) Proper corporate website (verified) — Yahoo → screener → web search.
    website, web_src = resolve_website(
        key,
        market_key,
        stored=stored,
        verify=True,
        company_name=company_name,
        use_web_search=True,
    )
    if not website:
        save_company_profiles(
            [
                _profile_row(
                    key,
                    market_key,
                    website="",
                    about=safe_str(stored.get("long_description")) or None,
                    source="no_website",
                    stored=stored,
                    website_status=WEBSITE_STATUS_NOT_FOUND,
                )
            ]
        )
        return {
            "ticker": key,
            "market": market_key,
            "ok": False,
            "skipped": False,
            "reason": "no_proper_website",
            "website": None,
            "website_status": WEBSITE_STATUS_NOT_FOUND,
            "chars": 0,
            "fill_source": "none",
        }

    stored = load_company_profiles_from_db([key]).get(key) or stored
    existing_about = safe_str(stored.get("long_description")).strip()

    # 2) Corporate site scrape — About text only (no themes / products / IR).
    result = scrape_website_about(website, max_pages=WEB_ABOUT_MAX_PAGES)
    about_text = safe_str(result.text).strip() or None
    if not about_text:
        return {
            "ticker": key,
            "market": market_key,
            "ok": False,
            "skipped": False,
            "reason": result.error or "no_about_text",
            "website": website,
            "source_url": result.source_url,
            "score": result.score,
            "chars": 0,
            "fill_source": web_src,
        }

    save_company_profiles(
        [
            _profile_row(
                key,
                market_key,
                website=website,
                about=about_text,
                source="website_about",
                stored=stored,
                products="",
                end_markets="",
                ir_url="",
                theme_tags="",
                website_status=WEBSITE_STATUS_OK,
                scraped_about=about_text,
            )
        ]
    )
    return {
        "ticker": key,
        "market": market_key,
        "ok": True,
        "skipped": False,
        "reason": "saved",
        "website": website,
        "website_status": WEBSITE_STATUS_OK,
        "source_url": result.source_url or website,
        "page_kind": result.page_kind,
        "score": result.score,
        "chars": len(about_text),
        "preview": about_text[:220],
        "fill_source": f"website+{web_src}" if web_src != "cache" else "website",
    }


def _unpack_job(job) -> tuple[str, str, str | None]:
    if len(job) >= 3:
        return job[0], job[1], job[2]
    return job[0], job[1], None


def run_about_batch(
    jobs: list,
    *,
    force: bool = False,
    max_workers: int = 1,
    website_only: bool = False,
    progress_callback=None,
) -> list[dict]:
    """
    Scrape a list of (ticker, market[, name]) jobs.

    website_only=True → find/verify corporate URLs only (no About scrape).
    Default max_workers=1 — corporate sites + delay; bump carefully.
    """
    if not jobs:
        return []
    workers = max(1, int(max_workers))
    total = len(jobs)
    results: list[dict] = []
    worker = find_and_save_website if website_only else scrape_and_save_about

    def _run_one(job):
        ticker, market, name = _unpack_job(job)
        return worker(ticker, market, force=force, company_name=name)

    if workers == 1:
        for i, job in enumerate(jobs, start=1):
            row = _run_one(job)
            results.append(row)
            if progress_callback:
                progress_callback(i, total, row)
        return results

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_run_one, job): job for job in jobs}
        for fut in as_completed(futures):
            row = fut.result()
            results.append(row)
            done += 1
            if progress_callback:
                progress_callback(done, total, row)
    order = {
        safe_str(_unpack_job(job)[0]).upper(): i for i, job in enumerate(jobs)
    }
    results.sort(key=lambda r: order.get(safe_str(r.get("ticker")).upper(), 10_000))
    return results


def batch_stats(results: list[dict]) -> dict[str, int]:
    saved = sum(
        1
        for r in results
        if r.get("ok")
        and not r.get("skipped")
        and r.get("reason") in {"saved", "saved_website"}
    )
    skipped = sum(1 for r in results if r.get("skipped"))
    failed = sum(1 for r in results if not r.get("ok") and not r.get("skipped"))
    not_found = sum(
        1
        for r in results
        if safe_str(r.get("website_status")) == WEBSITE_STATUS_NOT_FOUND
        or safe_str(r.get("reason")) in {"no_proper_website", "marked_not_found"}
    )
    return {
        "total": len(results),
        "saved": saved,
        "skipped": skipped,
        "failed": failed,
        "not_found": not_found,
        "delay_s": WEB_ABOUT_REQUEST_DELAY,
    }
