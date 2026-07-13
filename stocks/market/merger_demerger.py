"""Merger / demerger corporate actions — NSE official API."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import requests

from stocks.core.config import MERGER_DEMERGER_CACHE_HOURS, MERGER_DEMERGER_LOOKBACK_YEARS
from stocks.core.database import load_merger_demerger_cache, save_merger_demerger_cache
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.core.text_utils import safe_str
from stocks.market.merger_demerger_supplements import apply_merger_demerger_supplements
from stocks.shared.links import attach_research_links


def _enrich_table(df: pd.DataFrame, *, refresh: bool) -> pd.DataFrame:
    if df.empty:
        return df
    try:
        from stocks.listings.stocks_data import load_india_stocks
        from stocks.market.merger_demerger_enrich import enrich_demerger_dataframe

        stocks = load_india_stocks()
        return enrich_demerger_dataframe(df, stocks, refresh=refresh)
    except Exception as exc:
        log_error(METRICS_ERROR, "Demerger announcement enrich failed", error=str(exc))
        return df

_NSE_HOME = "https://www.nseindia.com/"
_NSE_CORP_URL = "https://www.nseindia.com/api/corporates-corporateActions"
_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT_SEC = 60
_TRADEBRAINS_REF = "https://portal.tradebrains.in/corporateactions/Merger-Demerger"


def tradebrains_merger_url() -> str:
    return _TRADEBRAINS_REF


def normalize_action_type(subject: str | None) -> str:
    raw = safe_str(subject).strip()
    lower = raw.lower().replace("de-merger", "demerger")
    if not lower:
        return "Other"
    has_demerger = "demerger" in lower
    has_merger = "merger" in lower.replace("demerger", "")
    if has_demerger and has_merger:
        return "Merger/Demerger"
    if has_demerger:
        return "Demerger"
    if has_merger:
        return "Merger"
    return raw or "Other"


def is_merger_demerger_subject(subject: str | None) -> bool:
    lower = safe_str(subject).lower().replace("de-merger", "demerger")
    return "merger" in lower or "demerger" in lower


def parse_nse_action_date(raw: str | None) -> date | None:
    text = safe_str(raw).strip()
    if not text or text == "-":
        return None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _nse_session() -> requests.Session:
    session = requests.Session()
    headers = {
        "User-Agent": _USER_AGENT,
        "Referer": _NSE_HOME,
        "Accept": "application/json",
    }
    session.get(_NSE_HOME, headers=headers, timeout=20)
    session.headers.update(headers)
    return session


def fetch_nse_corporate_actions(
    session: requests.Session,
    *,
    from_date: str,
    to_date: str,
) -> list[dict]:
    resp = session.get(
        _NSE_CORP_URL,
        params={"index": "equities", "from_date": from_date, "to_date": to_date},
        timeout=_TIMEOUT_SEC,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        return []
    return data


def _normalize_row(row: dict) -> dict | None:
    subject = safe_str(row.get("subject"))
    if not is_merger_demerger_subject(subject):
        return None
    ex_dt = parse_nse_action_date(row.get("exDate"))
    rec_dt = parse_nse_action_date(row.get("recDate"))
    symbol = safe_str(row.get("symbol")).upper()
    if not symbol:
        return None
    action_type = normalize_action_type(subject)
    return {
        "ticker": symbol,
        "company": safe_str(row.get("comp")) or symbol,
        "action_type": action_type,
        "ex_date": ex_dt.isoformat() if ex_dt else None,
        "record_date": rec_dt.isoformat() if rec_dt else None,
        "subject": subject,
        "isin": safe_str(row.get("isin")) or None,
        "series": safe_str(row.get("series")) or None,
        "source": "NSE",
    }


def fetch_merger_demerger_actions(
    *,
    lookback_years: int | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Fetch merger/demerger actions from NSE for the last N calendar years."""
    years = max(1, lookback_years or MERGER_DEMERGER_LOOKBACK_YEARS)
    end = end_date or date.today()
    start_year = end.year - years

    rows: list[dict] = []
    try:
        session = _nse_session()
        for year in range(start_year, end.year + 1):
            from_d = f"01-01-{year}"
            to_d = f"31-12-{year}" if year < end.year else end.strftime("%d-%m-%Y")
            try:
                batch = fetch_nse_corporate_actions(session, from_date=from_d, to_date=to_d)
            except Exception as exc:
                log_error(
                    METRICS_ERROR,
                    "NSE merger/demerger fetch failed",
                    year=year,
                    error=str(exc),
                )
                continue
            for item in batch:
                norm = _normalize_row(item)
                if norm:
                    rows.append(norm)
    except Exception as exc:
        log_error(METRICS_ERROR, "NSE session failed", error=str(exc))
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(
        subset=["ticker", "ex_date", "record_date", "subject"],
        keep="first",
    )
    df["ex_date"] = pd.to_datetime(df["ex_date"], errors="coerce")
    df["record_date"] = pd.to_datetime(df["record_date"], errors="coerce")
    df = df.sort_values(["ex_date", "company"], ascending=[False, True]).reset_index(drop=True)
    return attach_research_links(df)


def load_merger_demerger_table(
    *,
    refresh: bool = False,
    lookback_years: int | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """Return cached merger/demerger table and optional fetched-at label."""
    years = lookback_years or MERGER_DEMERGER_LOOKBACK_YEARS
    if not refresh:
        cached = load_merger_demerger_cache(max_hours=MERGER_DEMERGER_CACHE_HOURS)
        if cached is not None and not cached.empty:
            label = cached.attrs.get("fetched_at")
            out = cached.drop(columns=["fetched_at"], errors="ignore")
            out = apply_merger_demerger_supplements(out)
            return _enrich_table(out, refresh=False), label

    df = fetch_merger_demerger_actions(lookback_years=years)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if not df.empty:
        save_merger_demerger_cache(df, fetched_at=fetched_at, lookback_years=years)
    out = apply_merger_demerger_supplements(attach_research_links(df))
    return _enrich_table(out, refresh=refresh), fetched_at if not df.empty else None
