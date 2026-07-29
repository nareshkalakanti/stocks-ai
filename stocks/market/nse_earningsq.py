"""NSE live financial-result announcements for EarningsQ (equities only)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.market.nse_result_dates import (
    _TIMEOUT_SEC,
    _session_for_thread,
    parse_nse_announcement_timestamp,
    parse_period_end_from_text,
)

_ANNOUNCE_URL = "https://www.nseindia.com/api/corporate-announcements"
_FIN_RESULTS_URL = "https://www.nseindia.com/api/corporates-financial-results"

# Stricter than PEAD date helper — EarningsQ wants result prints, not every board meeting.
_STRICT_MARKERS = (
    "financial result updates",
    "integrated filing- financial",
    "unaudited financial results",
    "audited financial results",
    "financial results",
    "unaudited standalone and consolidated financial results",
    "unaudited consolidated financial results",
    "unaudited standalone financial results",
)


def is_earningsq_result_announcement(item: dict) -> bool:
    desc = safe_str(item.get("desc")).lower()
    body = " ".join(
        safe_str(item.get(key))
        for key in ("desc", "subject", "attchmntText")
    ).lower()
    if not body:
        return False
    # Noise categories — only keep if the *desc* itself is a results filing.
    noise_desc = (
        "press release",
        "copy of newspaper",
        "analysts/institutional",
        "investor meet",
        "con. call",
        "general updates",
        "updates",
    )
    if any(n == desc or desc.startswith(n) for n in noise_desc):
        return any(
            m in desc
            for m in (
                "financial result",
                "financial results",
                "integrated filing",
            )
        )
    if any(m in body for m in _STRICT_MARKERS):
        return True
    if "outcome of board meeting" in body and (
        "financial result" in body or "period ended" in body or "quarter ended" in body
    ):
        return True
    return False


def _parse_broadcast_full(item: dict) -> pd.Timestamp | None:
    """Keep time-of-day (IST wall clock as naive timestamp)."""
    for raw in (item.get("an_dt"), item.get("exchdisstime"), item.get("sort_date")):
        text = safe_str(raw).strip()
        if not text:
            continue
        for fmt in (
            "%d-%b-%Y %H:%M:%S",
            "%d-%B-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%Y %H:%M",
            "%d-%b-%Y",
        ):
            try:
                return pd.Timestamp(datetime.strptime(text, fmt))
            except ValueError:
                continue
        try:
            return pd.Timestamp(text)
        except (ValueError, TypeError):
            continue
    return parse_nse_announcement_timestamp(
        item.get("an_dt"), sort_date=item.get("sort_date")
    )


def normalize_earningsq_announcement(item: dict) -> dict | None:
    if not isinstance(item, dict) or not is_earningsq_result_announcement(item):
        return None
    symbol = safe_str(item.get("symbol")).upper()
    if not symbol:
        return None
    broadcast = _parse_broadcast_full(item)
    if broadcast is None:
        return None
    text = " ".join(
        safe_str(item.get(key)) for key in ("desc", "subject", "attchmntText")
    )
    period_end = parse_period_end_from_text(text)
    return {
        "ticker": symbol,
        "name": safe_str(item.get("sm_name")) or symbol,
        "market": "NSE",
        "broadcast_at": broadcast.strftime("%Y-%m-%d %H:%M:%S"),
        "broadcast_date": broadcast.strftime("%Y-%m-%d"),
        "period_end": period_end.strftime("%Y-%m-%d") if period_end is not None else None,
        "desc": safe_str(item.get("desc")) or None,
        "attachment_text": safe_str(item.get("attchmntText")) or None,
        "attachment_url": safe_str(item.get("attchmntFile")) or None,
        "isin": safe_str(item.get("sm_isin")) or None,
        "source": "nse_announcement",
    }


def fetch_nse_earnings_announcements(
    *,
    lookback_days: int = 7,
) -> list[dict]:
    """
    NSE equities corporate announcements in ``lookback_days``, filtered to
    financial-result prints. Newest first. Deduped per ticker (latest wins).
    """
    end = datetime.now()
    start = end - timedelta(days=max(1, int(lookback_days)))
    session = _session_for_thread()
    try:
        resp = session.get(
            _ANNOUNCE_URL,
            params={
                "index": "equities",
                "from_date": start.strftime("%d-%m-%Y"),
                "to_date": end.strftime("%d-%m-%Y"),
            },
            timeout=_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception:
        return []

    if not isinstance(items, list):
        return []

    rows: list[dict] = []
    for item in items:
        row = normalize_earningsq_announcement(item)
        if row:
            rows.append(row)

    rows.sort(key=lambda r: r["broadcast_at"], reverse=True)
    latest: dict[str, dict] = {}
    for row in rows:
        t = row["ticker"]
        if t not in latest:
            latest[t] = row
    return sorted(latest.values(), key=lambda r: r["broadcast_at"], reverse=True)


def fetch_nse_financial_results_meta(*, period: str = "Quarterly") -> list[dict]:
    """
    NSE corporates-financial-results metadata (often lags live announcements).

    Useful as a secondary NSE-only catalogue; metrics still come from PEAD/Yahoo.
    """
    session = _session_for_thread()
    try:
        resp = session.get(
            _FIN_RESULTS_URL,
            params={"index": "equities", "period": period},
            timeout=60,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception:
        return []
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        symbol = safe_str(item.get("symbol")).upper()
        if not symbol:
            continue
        broadcast = _parse_broadcast_full(
            {
                "an_dt": item.get("broadCastDate") or item.get("exchdisstime"),
                "sort_date": None,
            }
        )
        if broadcast is None:
            continue
        consol = safe_str(item.get("consolidated"))
        out.append(
            {
                "ticker": symbol,
                "name": safe_str(item.get("companyName")) or symbol,
                "market": "NSE",
                "broadcast_at": broadcast.strftime("%Y-%m-%d %H:%M:%S"),
                "broadcast_date": broadcast.strftime("%Y-%m-%d"),
                "period_end": safe_str(item.get("toDate")) or None,
                "period_start": safe_str(item.get("fromDate")) or None,
                "relating_to": safe_str(item.get("relatingTo")) or None,
                "consolidated": consol or None,
                "audited": safe_str(item.get("audited")) or None,
                "xbrl": safe_str(item.get("xbrl")) or None,
                "isin": safe_str(item.get("isin")) or None,
                "source": "nse_financial_results",
            }
        )
    out.sort(key=lambda r: r["broadcast_at"], reverse=True)
    return out


__all__ = [
    "fetch_nse_earnings_announcements",
    "fetch_nse_financial_results_meta",
    "is_earningsq_result_announcement",
    "normalize_earningsq_announcement",
]
