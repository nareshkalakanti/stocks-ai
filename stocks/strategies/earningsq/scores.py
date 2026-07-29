"""EarningsQ score heuristics — reverse-engineered against screenshot fixtures."""

from __future__ import annotations

from typing import Any

import pandas as pd

from stocks.core.text_utils import safe_str


def _f(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _cap(val: float | None, *, lo: float = -200.0, hi: float = 400.0) -> float | None:
    if val is None:
        return None
    return max(lo, min(hi, float(val)))


def compute_surprise_score(
    *,
    sales_yoy: float | None = None,
    sales_qoq: float | None = None,
    np_yoy: float | None = None,
    np_qoq: float | None = None,
    eps_yoy: float | None = None,
    eps_qoq: float | None = None,
    opm_yoy_pp: float | None = None,
    opm_qoq_pp: float | None = None,
) -> float | None:
    """
    Lightweight surprise score from growth prints.

    Tuned so fixture rows with strong NP/EPS YoY land near EarningsQ-like magnitudes
    (often ~0.5–3 for modest beats, higher when multiple legs are strong).
    """
    parts: list[tuple[float, float]] = []  # (weight, capped_pct)
    for w, raw in (
        (0.10, sales_yoy),
        (0.05, sales_qoq),
        (0.30, np_yoy),
        (0.15, np_qoq),
        (0.25, eps_yoy),
        (0.10, eps_qoq),
        (0.03, opm_yoy_pp),
        (0.02, opm_qoq_pp),
    ):
        v = _cap(_f(raw))
        if v is None:
            continue
        parts.append((w, v))
    if not parts:
        return None
    wsum = sum(w for w, _ in parts)
    if wsum <= 0:
        return None
    # Scale % growth into a compact score (EarningsQ-style single digits / low teens).
    blended = sum(w * v for w, v in parts) / wsum
    score = blended / 50.0
    return round(max(-5.0, min(25.0, score)), 2)


def compute_return_score(
    *,
    ret_1d: float | None = None,
    ret_1w: float | None = None,
    ret_qtd: float | None = None,
) -> float | None:
    """
    Return score from post-result price moves (percentage points).

    Prefer 1D, blend in 1W / QTD when present.
    """
    d1 = _f(ret_1d)
    w1 = _f(ret_1w)
    qtd = _f(ret_qtd)
    parts: list[tuple[float, float]] = []
    if d1 is not None:
        parts.append((0.55, d1))
    if w1 is not None:
        parts.append((0.30, w1))
    if qtd is not None:
        parts.append((0.15, qtd))
    if not parts:
        return None
    wsum = sum(w for w, _ in parts)
    score = sum(w * v for w, v in parts) / wsum
    return round(max(-40.0, min(80.0, score)), 2)


def market_hours_bucket(broadcast_ts: pd.Timestamp | None) -> str:
    """NSE cash session buckets in IST wall time."""
    if broadcast_ts is None or pd.isna(broadcast_ts):
        return ""
    ts = pd.Timestamp(broadcast_ts)
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert("Asia/Kolkata").tz_localize(None)
    minutes = int(ts.hour) * 60 + int(ts.minute)
    open_m, close_m = 9 * 60 + 15, 15 * 60 + 30
    if minutes < open_m:
        return "BEFORE"
    if minutes <= close_m:
        return "DURING"
    return "AFTER"


def filing_type_label(text: str | None, *, consolidated_flag: str | None = None) -> str:
    blob = f"{safe_str(consolidated_flag)} {safe_str(text)}".lower()
    if "non-consolidated" in blob or "standalone" in blob:
        return "Standalone"
    if "consolidated" in blob:
        return "Consolidated"
    return "Consolidated" if "consolidated" in safe_str(text).lower() else "—"


def blend_rank(
    *,
    surprise_score: float | None = None,
    return_score: float | None = None,
    ret_1d: float | None = None,
) -> float:
    """Single rank used to surface 'good' prints (surprise + market reaction)."""
    s = _f(surprise_score) or 0.0
    r = _f(return_score) or 0.0
    d1 = _f(ret_1d) or 0.0
    return round(s * 0.55 + r * 0.35 + d1 * 0.10, 3)


def quality_tag(
    *,
    surprise_score: float | None = None,
    return_score: float | None = None,
    ret_1d: float | None = None,
    np_yoy: float | None = None,
    eps_yoy: float | None = None,
    rev_yoy: float | None = None,
) -> str:
    """
    Friendly badge for the UI.

    - strong: surprise beat + earnings growth + sales not collapsing
    - fade: high surprise but price weak (treat carefully)
    - watch: mixed / incomplete
    - soft: positive but mild
    """
    s = _f(surprise_score)
    r = _f(return_score)
    d1 = _f(ret_1d)
    np_y = _f(np_yoy)
    eps_y = _f(eps_yoy)
    rev_y = _f(rev_yoy)

    if s is not None and s > 1.0 and d1 is not None and d1 < 0:
        return "fade"
    if (
        s is not None
        and s > 0.5
        and np_y is not None
        and np_y > 0
        and eps_y is not None
        and eps_y > 0
        and (rev_y is None or rev_y > -15)
        and (r is None or r >= 0)
    ):
        return "strong"
    if s is not None and s > 0:
        return "soft"
    return "watch"


def annotate_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Add quality_tag + blend_rank columns for sorting / UI badges."""
    if df is None or df.empty:
        return df
    out = df.copy()
    tags: list[str] = []
    ranks: list[float] = []
    for _, row in out.iterrows():
        tags.append(
            quality_tag(
                surprise_score=row.get("surprise_score"),
                return_score=row.get("return_score"),
                ret_1d=row.get("ret_1d"),
                np_yoy=row.get("np_yoy"),
                eps_yoy=row.get("eps_yoy"),
                rev_yoy=row.get("rev_yoy"),
            )
        )
        ranks.append(
            blend_rank(
                surprise_score=row.get("surprise_score"),
                return_score=row.get("return_score"),
                ret_1d=row.get("ret_1d"),
            )
        )
    out["quality_tag"] = tags
    out["blend_rank"] = ranks
    return out


__all__ = [
    "annotate_quality",
    "blend_rank",
    "compute_return_score",
    "compute_surprise_score",
    "filing_type_label",
    "market_hours_bucket",
    "quality_tag",
]
