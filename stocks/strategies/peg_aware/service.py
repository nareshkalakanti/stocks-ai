"""PEG-aware PEAD scan — PEAD 2 fundamentals, separate scoring."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.strategies.pead2.service import prepare_pead_universe, run_pead2_scan
from stocks.strategies.pead2.strategy import (
    attach_strategy_breakout_signals,
    enrich_pead_candidates,
)
from stocks.strategies.peg_aware.strategy import score_peg_aware


def run_peg_aware_scan(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    min_mcap_cr: float | None = None,
) -> dict:
    """Fetch PEAD 2 fundamentals, then score with PEG-aware PEAD logic."""
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

    scored = score_peg_aware(candidates)
    scored = enrich_pead_candidates(scored)
    scored = attach_strategy_breakout_signals(scored)

    prev = result.get("candidates_previous")
    prev_scored = pd.DataFrame()
    if isinstance(prev, pd.DataFrame) and not prev.empty:
        prev_scored = score_peg_aware(prev)
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
    "run_peg_aware_scan",
]
