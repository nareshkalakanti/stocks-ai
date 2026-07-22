"""Daily above-all-EMAs strategy package."""

from stocks.strategies.ema_daily.service import (
    prepare_ema_daily_universe,
    run_ema_daily_scan,
)

__all__ = [
    "prepare_ema_daily_universe",
    "run_ema_daily_scan",
]
