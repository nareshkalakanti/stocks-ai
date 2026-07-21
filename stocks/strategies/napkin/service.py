"""Napkin Investing — scan orchestration on top of PEAD2 fundamentals."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.strategies.napkin.strategy import score_napkin
from stocks.strategies.pead2.service import prepare_pead_universe, run_pead2_scan
from stocks.strategies.pead2.strategy import (
    attach_strategy_breakout_signals,
    enrich_pead_candidates,
)


def run_napkin_scan(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    min_mcap_cr: float | None = None,
) -> dict:
    """Fetch PEAD2 fundamentals, then re-rank with LotusDew napkin valuation."""
    result = run_pead2_scan(
        universe,
        max_workers=max_workers,
        progress_callback=progress_callback,
        min_mcap_cr=min_mcap_cr,
        check_breakouts=True,
    )
    candidates = result.get("candidates")
    if not isinstance(candidates, pd.DataFrame) or candidates.empty:
        return {
            **result,
            "candidates": pd.DataFrame(),
            "candidates_previous": pd.DataFrame(),
            "hits": 0,
        }

    scored = score_napkin(candidates)
    scored = enrich_pead_candidates(scored)
    scored = attach_strategy_breakout_signals(scored)

    prev = result.get("candidates_previous")
    prev_scored = pd.DataFrame()
    if isinstance(prev, pd.DataFrame) and not prev.empty:
        prev_scored = score_napkin(prev)
        if not prev_scored.empty:
            prev_scored = attach_strategy_breakout_signals(
                enrich_pead_candidates(prev_scored)
            )

    return {
        **result,
        "candidates": scored,
        "candidates_previous": prev_scored,
        "hits": len(scored),
        "hits_previous": len(prev_scored),
    }


__all__ = [
    "prepare_pead_universe",
    "run_napkin_scan",
]
