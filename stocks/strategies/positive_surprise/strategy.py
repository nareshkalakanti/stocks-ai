"""Positive Surprise Quant — seasonality-adjusted earnings surprise + PEG."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.core.config import (
    PEAD_FACTOR_PEG_GROWTH_FLOOR,
    PEAD_FACTOR_SUE_WEIGHT,
)


def seasonal_surprise_growth(row: pd.Series) -> float | None:
    """
    Seasonality-adjusted surprise proxy: same-quarter YoY growth.

    Prefer EPS YoY, then sales YoY, then net profit YoY.
    """
    for col in ("eps_yoy", "sales_yoy", "np_yoy"):
        val = pd.to_numeric(row.get(col), errors="coerce")
        if val is not None and not pd.isna(val):
            return float(val)
    return None


def compute_peg(
    forward_pe: float | None,
    growth_pct: float | None,
    *,
    growth_floor: float | None = None,
) -> float | None:
    """PEG = forward PE ÷ growth % (growth floored to avoid zero-base spikes)."""
    floor = PEAD_FACTOR_PEG_GROWTH_FLOOR if growth_floor is None else float(growth_floor)
    if forward_pe is None or growth_pct is None:
        return None
    try:
        pe = float(forward_pe)
        g = float(growth_pct)
    except (TypeError, ValueError):
        return None
    if pe <= 0 or pd.isna(pe) or pd.isna(g):
        return None
    denom = max(g, floor)
    if denom <= 0:
        return None
    return round(pe / denom, 2)


def _surprise_component(growth_pct: float) -> float:
    """Map positive YoY % into 0–100 (cap at 100% YoY)."""
    return float(np.clip(growth_pct, 0.0, 100.0))


def _peg_component(peg: float | None) -> float | None:
    """Lower PEG → higher score. PEG 0.5≈100, PEG 2≈50, PEG ≥4≈0."""
    if peg is None or pd.isna(peg) or peg <= 0:
        return None
    return float(np.clip(100.0 * (1.0 - (float(peg) - 0.5) / 3.5), 0.0, 100.0))


def score_positive_surprise(
    df: pd.DataFrame,
    *,
    sue_weight: float | None = None,
    growth_floor: float | None = None,
    require_positive: bool = True,
) -> pd.DataFrame:
    """
    Score candidates for Positive Surprise Quant.

    - Surprise: seasonality-adjusted YoY growth (EPS → sales → NP)
    - PEG: forward PE / floored growth
    - Composite weighted by ``sue_weight`` (default from config)
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    w = PEAD_FACTOR_SUE_WEIGHT if sue_weight is None else float(sue_weight)
    w = float(np.clip(w, 0.0, 1.0))
    floor = PEAD_FACTOR_PEG_GROWTH_FLOOR if growth_floor is None else float(growth_floor)

    out = df.copy()
    growths: list[float | None] = []
    pegs: list[float | None] = []
    scores: list[float | None] = []

    for _, row in out.iterrows():
        growth = seasonal_surprise_growth(row)
        fpe = pd.to_numeric(row.get("forward_pe"), errors="coerce")
        fpe_f = float(fpe) if fpe is not None and not pd.isna(fpe) else None
        peg = compute_peg(fpe_f, growth, growth_floor=floor)

        growths.append(growth)
        pegs.append(peg)

        if require_positive and (growth is None or growth <= 0):
            scores.append(None)
            continue

        sue = _surprise_component(growth) if growth is not None else None
        peg_sc = _peg_component(peg)
        if sue is None and peg_sc is None:
            scores.append(None)
            continue
        if sue is None:
            scores.append(round(peg_sc, 1))
        elif peg_sc is None:
            scores.append(round(sue, 1))
        else:
            scores.append(round(w * sue + (1.0 - w) * peg_sc, 1))

    out["surprise_growth"] = growths
    out["peg"] = pegs
    out["pead_score"] = scores
    out = out[out["pead_score"].notna()].copy()
    if out.empty:
        return out
    return out.sort_values(
        ["pead_score", "surprise_growth"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def format_psq_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("ticker", "ticker"),
        ("name", "name"),
        ("pead_score", "psq_score"),
        ("surprise_growth", "seasonal_surprise_yoy"),
        ("peg", "peg"),
        ("forward_pe", "forward_pe"),
        ("eps_yoy", "eps_yoy"),
        ("sales_yoy", "sales_yoy"),
        ("np_yoy", "np_yoy"),
        ("returns_pct", "returns_pct"),
        ("result_date", "result_date"),
        ("market_cap_cr", "market_cap_cr"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def psq_caption() -> str:
    return (
        "Positive Surprise Quant rides **seasonality-adjusted** earnings surprise "
        "(same-quarter **YoY** EPS / sales / NP) with a **PEG** overlay "
        "(Fwd PE ÷ growth). Sector & market-cap agnostic · typical hold **2–4 months** · "
        "needs active monitoring."
    )


__all__ = [
    "compute_peg",
    "format_psq_export_df",
    "psq_caption",
    "score_positive_surprise",
    "seasonal_surprise_growth",
]
