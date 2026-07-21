"""PEG-aware PEAD — positive surprise + PEG gate + PEAD-style confirmation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.core.config import (
    NAPKIN_ASSUMED_GROWTH_PCT,
    PEAD_FACTOR_PEG_GROWTH_FLOOR,
    PEAD_PEG_MAX,
    PEAD_PEG_MAX_FORWARD_PE,
    PEAD_PEG_REQUIRE_POSITIVE,
)
from stocks.strategies.napkin.strategy import near_term_pe, required_cagr_pct, resolve_pe
from stocks.strategies.pead2.strategy import Pead2ScoreWeights, score_pead2_ff
from stocks.strategies.positive_surprise.strategy import (
    _peg_component,
    compute_peg,
    seasonal_surprise_growth,
)


def peg_aware_score_weights() -> Pead2ScoreWeights:
    """~40% surprise · ~25% PEG · ~35% confirmation; napkin is readout-only."""
    return Pead2ScoreWeights(
        returns=12.0,
        sales_yoy=12.0,
        sales_qoq=6.0,
        np_yoy=14.0,
        np_qoq=8.0,
        eps_yoy=14.0,
        eps_qoq=4.0,
        ebidt_yoy=4.0,
        ebidt_qoq=2.0,
        forward_pe=3.0,
        peg=22.0,
        cf_profit=2.0,
    )


def attach_peg_aware_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Attach surprise, PEG, peg_score, and napkin secondary readouts."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    out = df.copy()
    floor = PEAD_FACTOR_PEG_GROWTH_FLOOR
    assumed = float(NAPKIN_ASSUMED_GROWTH_PCT)

    surprise: list[float | None] = []
    pegs: list[float | None] = []
    peg_scores: list[float | None] = []
    napkin_pes: list[float | None] = []
    napkin_nears: list[float | None] = []
    napkin_reqs: list[float | None] = []
    napkin_growths: list[float | None] = []
    napkin_gaps: list[float | None] = []

    for _, row in out.iterrows():
        growth = seasonal_surprise_growth(row)
        fpe = pd.to_numeric(row.get("forward_pe"), errors="coerce")
        fpe_f = float(fpe) if fpe is not None and not pd.isna(fpe) else None
        peg = compute_peg(fpe_f, growth, growth_floor=floor)
        peg_sc = _peg_component(peg)

        pe = resolve_pe(row)
        near = round(near_term_pe(pe), 1) if pe is not None else None
        req = required_cagr_pct(pe) if pe is not None else None
        n_growth = growth if growth is not None else assumed
        gap = None if req is None else round(float(n_growth) - float(req), 1)

        surprise.append(None if growth is None else round(float(growth), 2))
        pegs.append(peg)
        peg_scores.append(None if peg_sc is None else round(float(peg_sc), 1))
        napkin_pes.append(None if pe is None else round(float(pe), 1))
        napkin_nears.append(near)
        napkin_reqs.append(req)
        napkin_growths.append(None if n_growth is None else round(float(n_growth), 1))
        napkin_gaps.append(gap)

    out["surprise_growth"] = surprise
    out["peg"] = pegs
    out["peg_score"] = peg_scores
    out["napkin_pe"] = napkin_pes
    out["napkin_near_pe"] = napkin_nears
    out["napkin_required_cagr"] = napkin_reqs
    out["napkin_growth"] = napkin_growths
    out["napkin_gap"] = napkin_gaps
    return out


def apply_peg_aware_gate(
    df: pd.DataFrame,
    *,
    peg_max: float | None = None,
    require_positive: bool | None = None,
    max_forward_pe: float | None = None,
) -> pd.DataFrame:
    """Positive surprise + real Fwd PE + PEG at/under ceiling."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    ceiling = PEAD_PEG_MAX if peg_max is None else float(peg_max)
    need_pos = PEAD_PEG_REQUIRE_POSITIVE if require_positive is None else bool(require_positive)
    fpe_cap = PEAD_PEG_MAX_FORWARD_PE if max_forward_pe is None else float(max_forward_pe)

    out = df.copy()
    if "pead_score" not in out.columns:
        return out

    growth = (
        pd.to_numeric(out["surprise_growth"], errors="coerce")
        if "surprise_growth" in out.columns
        else pd.Series(np.nan, index=out.index)
    )
    peg = (
        pd.to_numeric(out["peg"], errors="coerce")
        if "peg" in out.columns
        else pd.Series(np.nan, index=out.index)
    )
    fpe = (
        pd.to_numeric(out["forward_pe"], errors="coerce")
        if "forward_pe" in out.columns
        else pd.Series(np.nan, index=out.index)
    )

    ok = peg.notna() & (peg > 0) & (peg <= ceiling)
    if need_pos:
        ok = ok & growth.notna() & (growth > 0)
    ok = ok & fpe.notna() & (fpe > 0) & (fpe < fpe_cap) & (fpe < 500)

    out.loc[~ok.fillna(False), "pead_score"] = np.nan
    out["peg_pass"] = ok.fillna(False)
    return out


def score_peg_aware(df: pd.DataFrame) -> pd.DataFrame:
    """Score and filter candidates for the PEG-aware PEAD strategy."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    work = attach_peg_aware_fields(df)
    scored = score_pead2_ff(work, weights=peg_aware_score_weights())
    scored = apply_peg_aware_gate(scored)
    scored = scored[scored["pead_score"].notna()].copy()
    if scored.empty:
        return scored
    return scored.sort_values("pead_score", ascending=False).reset_index(drop=True)


def format_peg_aware_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("ticker", "ticker"),
        ("name", "name"),
        ("pead_score", "peg_aware_score"),
        ("surprise_growth", "surprise_yoy"),
        ("peg", "peg"),
        ("forward_pe", "forward_pe"),
        ("returns_pct", "returns_pct"),
        ("napkin_near_pe", "napkin_near_pe"),
        ("napkin_required_cagr", "napkin_required_cagr"),
        ("napkin_gap", "napkin_gap"),
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


def peg_aware_caption() -> str:
    return (
        "PEG-aware: **positive seasonality-adjusted surprise** + **PEG ≤ 2** + "
        "confirmation (returns / QoQ / CF). Napkin Near PE / Req CAGR / Gap are "
        "**readouts only**. Sector & cap agnostic · typical hold **2–4 months**."
    )


__all__ = [
    "apply_peg_aware_gate",
    "attach_peg_aware_fields",
    "format_peg_aware_export_df",
    "peg_aware_caption",
    "peg_aware_score_weights",
    "score_peg_aware",
]
