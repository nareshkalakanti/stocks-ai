"""Adapt PEAD 1 (Earnings Explosion) scan rows for the shared PEAD dashboard UI."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.strategies.pead2.strategy import attach_strategy_breakout_signals


def pead1_candidates_for_dashboard(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize PEAD 1 scan output for ``build_pead2_dashboard_html(variant='pead1')``.

    Keeps PEAD 1 scoring/fields (rev/op/EPS jumps, gap, vol) and maps ``score`` → ``pead_score``
    so the shared report chrome (expand, TQ/BB, search) works unchanged.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    if "pead_score" not in out.columns:
        if "score" in out.columns:
            out["pead_score"] = pd.to_numeric(out["score"], errors="coerce")
        else:
            out["pead_score"] = pd.NA

    if "result_date" not in out.columns or out["result_date"].isna().all():
        if "quarter_end" in out.columns:
            out["result_date"] = out["quarter_end"]

    if "calculation_date" not in out.columns:
        out["calculation_date"] = datetime.now(timezone.utc).isoformat()

    # Friendly signal label for the table
    if "signal" in out.columns:
        out["pead1_signal"] = out["signal"].map(
            {
                "EARNINGS_BUY": "BUY",
                "EARNINGS_FUNDAMENTAL": "FUND",
            }
        ).fillna(out["signal"].astype(str))
    else:
        out["pead1_signal"] = ""

    out = attach_strategy_breakout_signals(out)
    return out.reset_index(drop=True)


def pead1_needs_expand_enrich(df: pd.DataFrame) -> bool:
    """True when any row is missing PEAD 2–style quarterly panel or price snapshot."""
    if df is None or df.empty:
        return False
    has_q_col = "quarters" in df.columns
    has_s_col = "snapshot" in df.columns
    if not has_q_col or not has_s_col:
        return True
    for _, row in df.iterrows():
        q = row.get("quarters")
        s = row.get("snapshot")
        if not (isinstance(q, dict) and q.get("labels")):
            return True
        if not (isinstance(s, dict) and s.get("price") is not None):
            return True
    return False


def enrich_pead1_expand_panels(
    df: pd.DataFrame,
    *,
    max_workers: int | None = None,
) -> pd.DataFrame:
    """Attach price snapshot + quarterly panel (same expand UX as PEAD 2).

    Scan already builds these when possible; this only backfills missing rows.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    from stocks.strategies.pead2.strategy import enrich_pead_candidates
    from stocks.strategies.tq_bb.panel import enrich_strategy_dataframe

    out = df.copy()
    if not pead1_needs_expand_enrich(out):
        return enrich_pead_candidates(out)

    missing_idx: list = []
    for i, row in out.iterrows():
        q = row.get("quarters") if "quarters" in out.columns else None
        s = row.get("snapshot") if "snapshot" in out.columns else None
        if not (
            isinstance(q, dict)
            and q.get("labels")
            and isinstance(s, dict)
            and s.get("price") is not None
        ):
            missing_idx.append(i)

    if not missing_idx:
        return enrich_pead_candidates(out)

    filled = enrich_strategy_dataframe(
        out.loc[missing_idx],
        max_workers=max_workers,
    )
    for col in ("quarters", "snapshot"):
        if col in filled.columns:
            if col not in out.columns:
                out[col] = None
            for idx in filled.index:
                out.at[idx, col] = filled.at[idx, col]
    return enrich_pead_candidates(out)


def pead1_export_df(df: pd.DataFrame) -> pd.DataFrame:
    """CSV-friendly PEAD 1 columns."""
    cols = [
        "ticker",
        "name",
        "market",
        "sector",
        "signal",
        "pead_score",
        "score",
        "result_date",
        "quarter_end",
        "rev_jump",
        "op_jump",
        "eps_jump",
        "pe_ratio",
        "forward_pe",
        "opm_pct",
        "opm_room_pp",
        "gap_pct",
        "vol_ratio",
        "market_cap_cr",
        "has_tq",
        "has_bb",
    ]
    work = pead1_candidates_for_dashboard(df)
    if work.empty:
        return pd.DataFrame(columns=cols)
    present = [c for c in cols if c in work.columns]
    return work[present].copy()
