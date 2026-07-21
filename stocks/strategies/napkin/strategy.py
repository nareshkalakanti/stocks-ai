"""LotusDew Napkin Investing — near-term vs terminal value PE check."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.core.config import (
    NAPKIN_ASSUMED_GROWTH_PCT,
    NAPKIN_HORIZON_YEARS,
    NAPKIN_NEAR_WEIGHT,
)


def resolve_pe(row: pd.Series) -> float | None:
    """Prefer forward PE, else trailing."""
    for col in ("forward_pe", "pe_ratio"):
        val = pd.to_numeric(row.get(col), errors="coerce")
        if val is not None and not pd.isna(val) and float(val) > 0:
            return float(val)
    snap = row.get("snapshot")
    if isinstance(snap, dict):
        for key in ("forward_pe", "pe_ratio", "pe"):
            val = pd.to_numeric(snap.get(key), errors="coerce")
            if val is not None and not pd.isna(val) and float(val) > 0:
                return float(val)
    return None


def resolve_growth_pct(row: pd.Series) -> float | None:
    """Observed growth proxy: EPS YoY → sales → NP → snapshot CAGR."""
    for col in ("eps_yoy", "sales_yoy", "np_yoy"):
        val = pd.to_numeric(row.get(col), errors="coerce")
        if val is not None and not pd.isna(val):
            return float(val)
    snap = row.get("snapshot")
    if isinstance(snap, dict):
        val = pd.to_numeric(snap.get("cagr"), errors="coerce")
        if val is not None and not pd.isna(val):
            # Snapshot CAGR is often a fraction (0.12); accept either form.
            g = float(val)
            return g * 100.0 if abs(g) <= 1.5 else g
    return None


def near_term_pe(pe: float, *, near_weight: float | None = None) -> float:
    """PE multiple attributed to the near-term (non-perpetuity) window."""
    w = NAPKIN_NEAR_WEIGHT if near_weight is None else float(near_weight)
    w = float(np.clip(w, 0.05, 0.95))
    return float(pe) * w


def required_cagr_pct(
    pe: float,
    *,
    near_weight: float | None = None,
    horizon_years: int | None = None,
) -> float | None:
    """
    Earnings CAGR baked into the price for the near-term slice.

    Banerjee napkin: near_pe = near_weight × PE;
    required CAGR ≈ near_pe^(1/N) − 1 over N years
    (e.g. PE 34.5 → near 10.4 → ~60% for N=5).
    """
    n = NAPKIN_HORIZON_YEARS if horizon_years is None else int(horizon_years)
    if n <= 0 or pe is None or pe <= 0:
        return None
    near = near_term_pe(pe, near_weight=near_weight)
    if near <= 0:
        return None
    return round((near ** (1.0 / n) - 1.0) * 100.0, 1)


def fair_pe_from_growth(
    growth_pct: float,
    *,
    near_weight: float | None = None,
    horizon_years: int | None = None,
) -> float | None:
    """Invert napkin: growth → fair near PE → fair full PE."""
    n = NAPKIN_HORIZON_YEARS if horizon_years is None else int(horizon_years)
    w = NAPKIN_NEAR_WEIGHT if near_weight is None else float(near_weight)
    w = float(np.clip(w, 0.05, 0.95))
    if n <= 0:
        return None
    g = float(growth_pct) / 100.0
    if g <= -0.99:
        return None
    near = (1.0 + g) ** n
    return round(near / w, 1)


def _napkin_score(growth_pct: float, required_pct: float) -> float:
    """
    Coverage of required CAGR by observed/assumed growth.

    1× coverage → 50, 2× → 100. Below required growth scores under 50.
    """
    if required_pct <= 0:
        return 100.0 if growth_pct > 0 else 0.0
    coverage = float(growth_pct) / float(required_pct)
    return float(np.clip(50.0 * coverage, 0.0, 100.0))


def score_napkin(
    df: pd.DataFrame,
    *,
    near_weight: float | None = None,
    horizon_years: int | None = None,
    assumed_growth_pct: float | None = None,
) -> pd.DataFrame:
    """
    Score names on LotusDew napkin valuation.

    Keeps rows with a usable PE. Growth defaults to config assumed market
    growth when YoY/CAGR is missing (article uses ~15% as the India baseline).
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    assumed = (
        NAPKIN_ASSUMED_GROWTH_PCT
        if assumed_growth_pct is None
        else float(assumed_growth_pct)
    )
    w = NAPKIN_NEAR_WEIGHT if near_weight is None else float(near_weight)
    n = NAPKIN_HORIZON_YEARS if horizon_years is None else int(horizon_years)

    out = df.copy()
    pes: list[float | None] = []
    nears: list[float | None] = []
    reqs: list[float | None] = []
    growths: list[float | None] = []
    growth_sources: list[str] = []
    gaps: list[float | None] = []
    fairs: list[float | None] = []
    scores: list[float | None] = []

    for _, row in out.iterrows():
        pe = resolve_pe(row)
        pes.append(pe)
        if pe is None:
            nears.append(None)
            reqs.append(None)
            growths.append(None)
            growth_sources.append("")
            gaps.append(None)
            fairs.append(None)
            scores.append(None)
            continue

        near = round(near_term_pe(pe, near_weight=w), 1)
        req = required_cagr_pct(pe, near_weight=w, horizon_years=n)
        observed = resolve_growth_pct(row)
        if observed is None:
            growth = assumed
            src = "assumed"
        else:
            growth = observed
            src = "observed"

        fair = fair_pe_from_growth(growth, near_weight=w, horizon_years=n)
        gap = None if req is None else round(float(growth) - float(req), 1)
        score = None if req is None else round(_napkin_score(growth, req), 1)

        nears.append(near)
        reqs.append(req)
        growths.append(round(float(growth), 1))
        growth_sources.append(src)
        gaps.append(gap)
        fairs.append(fair)
        scores.append(score)

    out["napkin_pe"] = pes
    out["napkin_near_pe"] = nears
    out["napkin_required_cagr"] = reqs
    out["napkin_growth"] = growths
    out["napkin_growth_source"] = growth_sources
    out["napkin_gap"] = gaps
    out["napkin_fair_pe"] = fairs
    out["pead_score"] = scores
    out = out[out["pead_score"].notna()].copy()
    if out.empty:
        return out
    return out.sort_values(
        ["pead_score", "napkin_gap"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def format_napkin_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("ticker", "ticker"),
        ("name", "name"),
        ("pead_score", "napkin_score"),
        ("napkin_pe", "pe"),
        ("napkin_near_pe", "near_term_pe"),
        ("napkin_required_cagr", "required_cagr_pct"),
        ("napkin_growth", "growth_pct"),
        ("napkin_growth_source", "growth_source"),
        ("napkin_gap", "growth_minus_required_pp"),
        ("napkin_fair_pe", "fair_pe"),
        ("forward_pe", "forward_pe"),
        ("pe_ratio", "pe_ratio"),
        ("eps_yoy", "eps_yoy"),
        ("sales_yoy", "sales_yoy"),
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


def napkin_caption() -> str:
    w = int(round(NAPKIN_NEAR_WEIGHT * 100))
    t = 100 - w
    return (
        f"**Napkin Investing** (LotusDew): ~**{t}%** of equity value is terminal / "
        f"perpetual; ~**{w}%** is the near-term **{NAPKIN_HORIZON_YEARS}Y** slice. "
        f"Required earnings CAGR ≈ (PE×{NAPKIN_NEAR_WEIGHT:.2f})"
        f"^(1/{NAPKIN_HORIZON_YEARS})−1 — compare to YoY / assumed "
        f"**{NAPKIN_ASSUMED_GROWTH_PCT:.0f}%** market growth. "
        "Back-of-envelope only · not a DCF."
    )


__all__ = [
    "fair_pe_from_growth",
    "format_napkin_export_df",
    "napkin_caption",
    "near_term_pe",
    "required_cagr_pct",
    "resolve_growth_pct",
    "resolve_pe",
    "score_napkin",
]
