"""Shared yfinance rate-limit handling.

Two modes (matches stock-analysis vs fundamentals trade-off):

- **Throttled** — proactive delay before each request + backoff on HTTP 429/401.
  Used by Fundamentals and cap-tier market-cap fetches.

- **Fast** — no proactive delay; short backoff retries on 429/401 with a global
  in-flight cap so parallel strategy workers don't invalidate Yahoo's crumb.
  Used by Strategy TQ/BB (parallel history fetches, speed over pacing).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TypeVar

from stocks.market.yfinance_utils import reset_yfinance_auth

T = TypeVar("T")

_rate_lock = threading.Lock()
_last_request_at = 0.0

FUNDAMENTALS_RETRY_DELAYS = (2.0, 5.0, 10.0, 20.0)
STRATEGY_RETRY_DELAYS = (1.0, 2.0, 5.0)
YAHOO_AUTH_RETRY_DELAYS = (2.0, 5.0, 10.0, 20.0)

_inflight_limit = 4
_inflight = threading.Semaphore(_inflight_limit)


def configure_yfinance_limits(*, max_inflight: int) -> None:
    """Apply runtime limits from config (called once at import from config.py)."""
    global _inflight_limit, _inflight
    limit = max(1, int(max_inflight))
    if limit == _inflight_limit:
        return
    _inflight_limit = limit
    _inflight = threading.Semaphore(limit)


def is_rate_limited(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "too many requests" in text or "rate limit" in text


def is_yahoo_auth_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "401" in text
        or "invalid crumb" in text
        or "unauthorized" in text
        or "unable to access this feature" in text
    )


def is_yahoo_retryable(exc: BaseException) -> bool:
    return is_rate_limited(exc) or is_yahoo_auth_error(exc)


def _retry_delay(
    exc: BaseException,
    attempt: int,
    *,
    retry_delays: tuple[float, ...],
    auth_delays: tuple[float, ...],
) -> float | None:
    if is_yahoo_auth_error(exc):
        if attempt < len(auth_delays):
            return auth_delays[attempt]
        return None
    if is_rate_limited(exc):
        if attempt < len(retry_delays):
            return retry_delays[attempt]
        return None
    return None


def throttle_before_request(delay: float) -> None:
    """Global pacing — serializes minimum spacing between yfinance calls."""
    if delay <= 0:
        return
    global _last_request_at
    with _rate_lock:
        now = time.monotonic()
        wait = delay - (now - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _run_yfinance_call(fn: Callable[[], T]) -> T:
    with _inflight:
        return fn()


def call_throttled(
    fn: Callable[[], T],
    *,
    delay: float,
    retry_delays: tuple[float, ...] = FUNDAMENTALS_RETRY_DELAYS,
    auth_delays: tuple[float, ...] = YAHOO_AUTH_RETRY_DELAYS,
    on_error: Callable[[Exception], None] | None = None,
) -> T | None:
    """Fundamentals-style: wait before each attempt, long backoff on 429/401."""
    last_exc: Exception | None = None
    max_attempts = max(len(retry_delays), len(auth_delays)) + 1
    for attempt in range(max_attempts):
        try:
            throttle_before_request(delay)
            return _run_yfinance_call(fn)
        except Exception as exc:
            last_exc = exc
            wait = _retry_delay(
                exc,
                attempt,
                retry_delays=retry_delays,
                auth_delays=auth_delays,
            )
            if wait is not None:
                if is_yahoo_auth_error(exc):
                    reset_yfinance_auth()
                time.sleep(wait)
                continue
            if on_error and not is_yahoo_retryable(exc):
                on_error(exc)
            break
    if on_error and last_exc and is_yahoo_retryable(last_exc):
        on_error(last_exc)
    return None


def call_fast(
    fn: Callable[[], T],
    *,
    retry_delays: tuple[float, ...] = STRATEGY_RETRY_DELAYS,
    auth_delays: tuple[float, ...] = YAHOO_AUTH_RETRY_DELAYS,
    on_error: Callable[[Exception], None] | None = None,
) -> T | None:
    """Strategy-style: in-flight cap + retry on 429/401 (no proactive delay)."""
    last_exc: Exception | None = None
    max_attempts = max(len(retry_delays), len(auth_delays)) + 1
    for attempt in range(max_attempts):
        try:
            return _run_yfinance_call(fn)
        except Exception as exc:
            last_exc = exc
            wait = _retry_delay(
                exc,
                attempt,
                retry_delays=retry_delays,
                auth_delays=auth_delays,
            )
            if wait is not None:
                if is_yahoo_auth_error(exc):
                    reset_yfinance_auth()
                time.sleep(wait)
                continue
            if on_error and not is_yahoo_retryable(exc):
                on_error(exc)
            break
    if on_error and last_exc and is_yahoo_retryable(last_exc):
        on_error(last_exc)
    return None
