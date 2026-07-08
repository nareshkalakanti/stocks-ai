"""Filter distorted Yahoo quarterly EPS / net-profit rows (low base, NP–EPS mismatch)."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import EARNINGS_MAX_EPS_YOY_PCT, EARNINGS_MAX_SHARE_RATIO, EARNINGS_MIN_PRIOR_EPS


def passes_earnings_quality(
    net_profit: pd.Series,
    eps: pd.Series,
    *,
    min_prior_eps: float | None = None,
    max_share_ratio: float | None = None,
    lookback: int = 5,
) -> tuple[bool, str]:
    """
    Reject names where YoY EPS metrics are unreliable on yfinance data.

    1. Prior-year same-quarter EPS must be above a floor (avoids 0.03 → 0.40 spikes).
    2. Implied share count (NP ÷ EPS) must be stable across recent quarters.
    """
    floor = EARNINGS_MIN_PRIOR_EPS if min_prior_eps is None else min_prior_eps
    max_ratio = EARNINGS_MAX_SHARE_RATIO if max_share_ratio is None else max_share_ratio

    ep = eps.dropna().sort_index().astype(float)
    if len(ep) < 5:
        return False, "Need 5+ quarterly EPS points"

    prior_eps = float(ep.iloc[-5])
    if prior_eps < floor:
        return False, f"Prior-year EPS {prior_eps:.2f} < {floor:.2f} (distorted YoY base)"

    np_s = net_profit.reindex(ep.index).astype(float)
    tail = ep.index[-lookback:]
    implied: list[float] = []
    for dt in tail:
        e = float(ep.loc[dt])
        n = np_s.loc[dt]
        if pd.isna(n) or float(n) <= 0 or e <= 0:
            continue
        implied.append(float(n) / e)

    if len(implied) >= 3:
        lo, hi = min(implied), max(implied)
        if lo > 0 and hi / lo > max_ratio:
            return (
                False,
                f"NP/EPS implied shares vary {hi / lo:.1f}× (max {max_ratio:.2f}×)",
            )

    return True, ""


def cap_eps_yoy_pct(yoy_pct: float | None, *, cap: float | None = None) -> float | None:
    """Cap extreme YoY % used for PEG / growth scoring."""
    if yoy_pct is None or (isinstance(yoy_pct, float) and pd.isna(yoy_pct)):
        return None
    limit = EARNINGS_MAX_EPS_YOY_PCT if cap is None else cap
    return round(min(float(yoy_pct), float(limit)), 2)


def cap_growth_qoq_pct(qoq_pct: float | None, *, cap: float | None = None) -> float | None:
    """Cap extreme QoQ % (avoids near-zero-base spikes in percentile scoring)."""
    if qoq_pct is None or (isinstance(qoq_pct, float) and pd.isna(qoq_pct)):
        return None
    limit = abs(float(EARNINGS_MAX_EPS_YOY_PCT if cap is None else cap))
    val = float(qoq_pct)
    return round(max(-limit, min(limit, val)), 2)
