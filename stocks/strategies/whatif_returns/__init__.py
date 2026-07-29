"""What-if returns strategy package."""

from stocks.strategies.whatif_returns.service import (
    RETURN_HORIZONS,
    load_signal_universe,
    portfolio_whatif_summary,
    run_whatif_returns_scan,
    top_performers,
)

__all__ = [
    "RETURN_HORIZONS",
    "load_signal_universe",
    "portfolio_whatif_summary",
    "run_whatif_returns_scan",
    "top_performers",
]
