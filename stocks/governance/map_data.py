"""Governance Map — multi-board directors enriched for PEAD-style HTML report."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from stocks.core.database import (
    load_company_profiles_from_db,
    load_market_cap_from_db,
    save_market_cap_to_db,
)
from stocks.core.text_utils import safe_str
from stocks.governance.db import get_governance_connection, init_governance_db
from stocks.governance.score import mcap_cap_code, mcap_cap_label, score_director_seats
from stocks.market.company_profile import _WEBSITE_OVERRIDES, merge_company_profile
from stocks.market.screener_profile import fetch_screener_market_cap_cr
from stocks.shared.corp_tags import (
    clear_corp_tags_cache,
    holdings_ticker_set,
    nse_sme_ticker_set,
)
from stocks.shared.links import screener_url, tradingview_url

# Screener backfill per map build (cached after first success).
DEFAULT_PROFILE_HYDRATE = 60
DEFAULT_MCAP_HYDRATE = 40
PROFILE_HYDRATE_WORKERS = 4


def _mcap_map(tickers: list[str]) -> dict[str, float]:
    if not tickers:
        return {}
    df = load_market_cap_from_db(tickers)
    if df.empty or "ticker" not in df.columns:
        return {}
    out: dict[str, float] = {}
    for _, row in df.iterrows():
        key = safe_str(row.get("ticker")).upper()
        val = row.get("market_cap_cr")
        if not key or val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        try:
            out[key] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def _profile_incomplete(profile: dict | None) -> bool:
    data = profile or {}
    return not safe_str(data.get("long_description")).strip() or not safe_str(
        data.get("website")
    ).strip()


def _apply_profile_overrides(profiles: dict[str, dict]) -> dict[str, dict]:
    out = dict(profiles)
    for ticker, website in _WEBSITE_OVERRIDES.items():
        key = safe_str(ticker).upper()
        row = dict(out.get(key) or {})
        if website and not safe_str(row.get("website")):
            row["website"] = website
            out[key] = row
    return out


def hydrate_missing_profiles(
    ticker_markets: list[tuple[str, str]],
    *,
    max_fetch: int = DEFAULT_PROFILE_HYDRATE,
    workers: int = PROFILE_HYDRATE_WORKERS,
) -> int:
    """Fetch website/about from screener for companies missing either field."""
    if max_fetch <= 0 or not ticker_markets:
        return 0
    # Prefer companies that appear most often on shared-director boards.
    freq: dict[str, int] = {}
    market_by: dict[str, str] = {}
    for ticker, market in ticker_markets:
        key = safe_str(ticker).upper()
        if not key:
            continue
        freq[key] = freq.get(key, 0) + 1
        market_by.setdefault(key, safe_str(market).upper() or "NSE")

    tickers = list(freq.keys())
    profiles = load_company_profiles_from_db(tickers)
    pending: list[tuple[str, str]] = []
    for key, _count in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
        if not _profile_incomplete(profiles.get(key)):
            continue
        pending.append((key, market_by.get(key) or "NSE"))
        if len(pending) >= max_fetch:
            break
    if not pending:
        return 0

    def _one(item: tuple[str, str]) -> bool:
        ticker, market = item
        before = load_company_profiles_from_db([ticker]).get(ticker) or {}
        merged = merge_company_profile({}, ticker, market)
        after_web = safe_str(merged.get("website"))
        after_about = safe_str(merged.get("long_description"))
        if not after_web and not after_about:
            return False
        return _profile_incomplete(before) and (bool(after_web) or bool(after_about))

    filled = 0
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futures = [pool.submit(_one, item) for item in pending]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    filled += 1
            except Exception:
                continue
    return filled


def hydrate_missing_mcaps(
    ticker_markets: list[tuple[str, str]],
    *,
    max_fetch: int = DEFAULT_MCAP_HYDRATE,
    workers: int = PROFILE_HYDRATE_WORKERS,
) -> int:
    """Fetch market cap (₹ Cr) from screener when Yahoo/DB cache has none."""
    if max_fetch <= 0 or not ticker_markets:
        return 0
    freq: dict[str, int] = {}
    market_by: dict[str, str] = {}
    for ticker, market in ticker_markets:
        key = safe_str(ticker).upper()
        if not key:
            continue
        freq[key] = freq.get(key, 0) + 1
        market_by.setdefault(key, safe_str(market).upper() or "NSE")

    known = _mcap_map(list(freq.keys()))
    pending: list[tuple[str, str]] = []
    for key, _count in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
        if key in known:
            continue
        pending.append((key, market_by.get(key) or "NSE"))
        if len(pending) >= max_fetch:
            break
    if not pending:
        return 0

    def _one(item: tuple[str, str]) -> bool:
        ticker, market = item
        try:
            mcap = fetch_screener_market_cap_cr(ticker, market)
        except Exception:
            return False
        if mcap is None or mcap <= 0:
            return False
        try:
            save_market_cap_to_db(ticker, float(mcap), market=market)
        except Exception:
            return False
        return True

    filled = 0
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futures = [pool.submit(_one, item) for item in pending]
        for fut in as_completed(futures):
            try:
                if fut.result():
                    filled += 1
            except Exception:
                continue
    return filled


def missing_profile_tickers(ticker_markets: list[tuple[str, str]]) -> list[str]:
    tickers = sorted(
        {safe_str(t).upper() for t, _ in ticker_markets if safe_str(t)}
    )
    profiles = _apply_profile_overrides(load_company_profiles_from_db(tickers))
    return [t for t in tickers if _profile_incomplete(profiles.get(t))]


def map_company_ticker_markets(*, min_boards: int = 2) -> list[tuple[str, str]]:
    """All (ticker, market) pairs from multi-board seats (duplicates kept for frequency)."""
    seats = _load_multi_board_seats(min_boards=min_boards)
    if seats.empty:
        return []
    out: list[tuple[str, str]] = []
    for _, row in seats.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        out.append((ticker, safe_str(row.get("market")).upper() or "NSE"))
    return out


def _load_multi_board_seats(*, min_boards: int = 2) -> pd.DataFrame:
    init_governance_db()
    min_boards = max(2, int(min_boards))
    with get_governance_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                d.person_id,
                d.din,
                d.name AS director_name,
                s.ticker,
                c.name AS company_name,
                c.market,
                s.designation,
                s.category,
                s.source,
                s.as_of
            FROM directors d
            JOIN board_seats s ON s.person_id = d.person_id
            JOIN companies c ON c.ticker = s.ticker
            WHERE UPPER(c.market) = 'NSE'
              AND d.person_id IN (
                SELECT s2.person_id
                FROM board_seats s2
                JOIN companies c2 ON c2.ticker = s2.ticker
                WHERE UPPER(c2.market) = 'NSE'
                GROUP BY s2.person_id
                HAVING COUNT(DISTINCT s2.ticker) >= ?
            )
            ORDER BY d.name COLLATE NOCASE, c.name COLLATE NOCASE
            """,
            (min_boards,),
        ).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def build_governance_map_rows(
    *,
    min_boards: int = 2,
    hydrate_profiles: bool = True,
    hydrate_max: int = DEFAULT_PROFILE_HYDRATE,
    hydrate_mcaps: bool = True,
    hydrate_mcap_max: int = DEFAULT_MCAP_HYDRATE,
) -> pd.DataFrame:
    """
    One row per director on ``min_boards``+ companies.

    Columns include ``dir_score``, ``companies`` (list of enriched seat dicts),
    plus summary fields for the PEAD-style table.
    """
    seats_df = _load_multi_board_seats(min_boards=min_boards)
    if seats_df.empty:
        return pd.DataFrame()

    ticker_markets = map_company_ticker_markets(min_boards=min_boards)
    if hydrate_profiles and hydrate_max > 0:
        hydrate_missing_profiles(ticker_markets, max_fetch=hydrate_max)
    if hydrate_mcaps and hydrate_mcap_max > 0:
        hydrate_missing_mcaps(ticker_markets, max_fetch=hydrate_mcap_max)

    tickers = sorted(
        {safe_str(t).upper() for t in seats_df["ticker"].tolist() if safe_str(t)}
    )
    mcaps = _mcap_map(tickers)
    profiles = _apply_profile_overrides(load_company_profiles_from_db(tickers))
    clear_corp_tags_cache()
    holding_tickers = holdings_ticker_set()
    sme_tickers = nse_sme_ticker_set()

    rows: list[dict[str, Any]] = []
    for person_id, grp in seats_df.groupby("person_id", sort=False):
        companies: list[dict[str, Any]] = []
        for _, seat in grp.iterrows():
            ticker = safe_str(seat.get("ticker")).upper()
            if not ticker:
                continue
            market = safe_str(seat.get("market")).upper() or "NSE"
            if ticker in sme_tickers:
                market = "NSE SME"
            profile = profiles.get(ticker) or {}
            override = _WEBSITE_OVERRIDES.get(ticker)
            mcap = mcaps.get(ticker)
            website = safe_str(override) or safe_str(profile.get("website")) or None
            about = safe_str(profile.get("long_description")) or None
            companies.append(
                {
                    "ticker": ticker,
                    "name": safe_str(seat.get("company_name")) or ticker,
                    "market": market,
                    "designation": safe_str(seat.get("designation")),
                    "category": safe_str(seat.get("category")) or None,
                    "source": safe_str(seat.get("source")) or None,
                    "as_of": safe_str(seat.get("as_of")) or None,
                    "market_cap_cr": mcap,
                    "cap_code": mcap_cap_code(mcap),
                    "cap_label": mcap_cap_label(mcap),
                    "website": website,
                    "about": about,
                    "is_holding": ticker in holding_tickers,
                    "is_sme": ticker in sme_tickers,
                    "sc": screener_url(ticker, market),
                    "tv": tradingview_url(ticker, market),
                }
            )

        if len({c["ticker"] for c in companies}) < min_boards:
            continue

        din = safe_str(grp.iloc[0].get("din")) or None
        director = safe_str(grp.iloc[0].get("director_name"))
        scored = score_director_seats(
            companies,
            person_id=str(person_id),
            din=din,
        )
        tickers_label = ", ".join(c["ticker"] for c in companies)
        rows.append(
            {
                "person_id": str(person_id),
                "din": din,
                "name": director,
                "director": director,
                "board_count": scored["board_count"],
                "dir_score": scored["dir_score"],
                "din_backed": scored["din_backed"],
                "name_collision": scored["name_collision"],
                "big_n": scored["big_n"],
                "small_n": scored["small_n"],
                "bridge": scored["bridge"],
                "tickers": tickers_label,
                "companies": companies,
                "score_breakdown": scored,
            }
        )

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = out.sort_values(
        by=["dir_score", "board_count", "name"],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    return out


def _mcap_in_band(
    market_cap_cr: float | None,
    *,
    min_cr: float | None,
    max_cr: float | None,
) -> bool:
    if market_cap_cr is None:
        return False
    try:
        cap = float(market_cap_cr)
    except (TypeError, ValueError):
        return False
    if cap != cap or cap <= 0:  # NaN / non-positive
        return False
    if min_cr is not None and cap < float(min_cr):
        return False
    if max_cr is not None and cap >= float(max_cr):
        return False
    return True


def filter_governance_map_by_mcap(
    df: pd.DataFrame,
    *,
    min_cr: float | None = None,
    max_cr: float | None = None,
    min_boards: int = 2,
    keep_unknown: bool = False,
) -> pd.DataFrame:
    """
    Keep directors who still have ``min_boards`` companies inside the mcap band.

    ``max_cr`` is exclusive (same as CAP_TIERS). Unknown mcap seats drop unless
    ``keep_unknown`` is True.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    if min_cr is None and max_cr is None:
        return df

    min_boards = max(2, int(min_boards))
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        companies = row.get("companies") or []
        if not isinstance(companies, list):
            continue
        kept: list[dict[str, Any]] = []
        for company in companies:
            mcap = company.get("market_cap_cr")
            if mcap is None or (
                isinstance(mcap, float) and pd.isna(mcap)
            ):
                if keep_unknown:
                    kept.append(company)
                continue
            if _mcap_in_band(mcap, min_cr=min_cr, max_cr=max_cr):
                kept.append(company)
        if len({safe_str(c.get("ticker")).upper() for c in kept if safe_str(c.get("ticker"))}) < min_boards:
            continue
        scored = score_director_seats(
            kept,
            person_id=safe_str(row.get("person_id")),
            din=safe_str(row.get("din")) or None,
        )
        updated = dict(row)
        updated["companies"] = kept
        updated["tickers"] = ", ".join(c["ticker"] for c in kept)
        updated["board_count"] = scored["board_count"]
        updated["dir_score"] = scored["dir_score"]
        updated["din_backed"] = scored["din_backed"]
        updated["name_collision"] = scored["name_collision"]
        updated["big_n"] = scored["big_n"]
        updated["small_n"] = scored["small_n"]
        updated["bridge"] = scored["bridge"]
        updated["score_breakdown"] = scored
        rows.append(updated)

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = out.sort_values(
        by=["dir_score", "board_count", "name"],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    return out
