"""Distressed turnaround — scan orchestration on surveillance ∪ seed universe."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from stocks.market.nse_surveillance import surveillance_universe_frame
from stocks.strategies.distress.strategy import score_distress_turnaround
from stocks.strategies.pead2.service import prepare_pead_universe, run_pead2_scan
from stocks.strategies.pead2.strategy import (
    attach_strategy_breakout_signals,
    enrich_pead_candidates,
)


def prepare_distress_universe(
    stocks: pd.DataFrame,
    *,
    cap_tier_id: str = "all",
    force_refresh_surveillance: bool = False,
) -> tuple[pd.DataFrame, int, int]:
    """Intersect listings with NSE surveillance + distress seed, then apply cap tier."""
    surv = surveillance_universe_frame(
        stocks,
        force_refresh=force_refresh_surveillance,
        include_seed=True,
    )
    if surv.empty:
        return surv, 0, 0
    meta_cols = [c for c in ("surv_type", "surv_stage", "source") if c in surv.columns]
    meta = surv[["ticker", *meta_cols]].drop_duplicates("ticker") if meta_cols else pd.DataFrame()
    universe, cap_excluded, mcap_excluded = prepare_pead_universe(
        surv, cap_tier_id=cap_tier_id
    )
    if not meta.empty and not universe.empty:
        universe = universe.merge(meta, on="ticker", how="left")
    return universe, cap_excluded, mcap_excluded


def run_distress_scan(
    universe: pd.DataFrame,
    *,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    min_mcap_cr: float | None = None,
) -> dict:
    """Fetch PEAD2 fundamentals for surveillance/seed names, then distress-score."""
    meta_cols = [c for c in ("surv_type", "surv_stage", "source") if c in universe.columns]
    meta = (
        universe[["ticker", *meta_cols]].drop_duplicates("ticker")
        if meta_cols and "ticker" in universe.columns
        else pd.DataFrame()
    )

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

    if not meta.empty:
        candidates = candidates.merge(meta, on="ticker", how="left", suffixes=("", "_meta"))
        for col in meta_cols:
            meta_col = f"{col}_meta"
            if meta_col in candidates.columns:
                candidates[col] = candidates[col].fillna(candidates[meta_col])
                candidates = candidates.drop(columns=[meta_col])

    scored = score_distress_turnaround(candidates)
    scored = enrich_pead_candidates(scored)
    scored = attach_strategy_breakout_signals(scored)

    # Always surface seed monitors even when PEAD fundamentals are thin.
    if "ticker" in universe.columns:
        from stocks.market.nse_surveillance import load_distress_seed_tickers

        seed = set(load_distress_seed_tickers())
        have = set(scored["ticker"].astype(str).str.upper()) if not scored.empty else set()
        missing = [t for t in seed if t not in have]
        if missing:
            extras = universe[universe["ticker"].astype(str).str.upper().isin(missing)].copy()
            if not extras.empty:
                extras = score_distress_turnaround(extras)
                if not extras.empty:
                    scored = pd.concat([scored, extras], ignore_index=True)
                    scored = scored.sort_values(
                        ["pead_score", "ticker"],
                        ascending=[False, True],
                        na_position="last",
                    ).reset_index(drop=True)

    prev = result.get("candidates_previous")
    prev_scored = pd.DataFrame()
    if isinstance(prev, pd.DataFrame) and not prev.empty:
        if not meta.empty:
            prev = prev.merge(meta, on="ticker", how="left", suffixes=("", "_meta"))
            for col in meta_cols:
                meta_col = f"{col}_meta"
                if meta_col in prev.columns:
                    prev[col] = prev[col].fillna(prev[meta_col])
                    prev = prev.drop(columns=[meta_col])
        prev_scored = score_distress_turnaround(prev)
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
    "prepare_distress_universe",
    "prepare_pead_universe",
    "run_distress_scan",
]
