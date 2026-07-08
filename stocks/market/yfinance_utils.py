"""Shared yfinance helpers: log noise suppression and auth reset."""

from __future__ import annotations

import logging
import warnings

_NOISE_FILTERS_INSTALLED = False


def install_yfinance_noise_filters() -> None:
    """Suppress noisy yfinance / HTTP warnings during bulk scans."""
    global _NOISE_FILTERS_INSTALLED
    if _NOISE_FILTERS_INSTALLED:
        return
    _NOISE_FILTERS_INSTALLED = True

    for name in (
        "yfinance",
        "urllib3",
        "peewee",
        "requests",
        "charset_normalizer",
        "curl_cffi",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    warnings.filterwarnings(
        "ignore",
        message=".*Ticker\\.earnings.*",
        category=DeprecationWarning,
    )
    warnings.filterwarnings("ignore", message=".*possibly delisted.*")
    warnings.filterwarnings("ignore", module="yfinance.*")


def reset_yfinance_auth() -> None:
    """Clear cached Yahoo cookie/crumb so the next request re-authenticates."""
    try:
        from yfinance.data import YfData

        data = YfData()
        with data._cookie_lock:
            data._crumb = None
            data._cookie = None
    except Exception:
        pass
