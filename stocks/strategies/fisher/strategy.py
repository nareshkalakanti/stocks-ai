"""Philip Fisher 15-point multibagger scorecard (quantitative proxies + scuttlebutt gaps)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.core.config import (
    FISHER_MCAP_MAX_CR,
    FISHER_MIN_CF_PROFIT,
    FISHER_MIN_CHECKS,
    FISHER_MIN_SALES_YOY,
    FISHER_PE_MAX,
    FISHER_PE_MIN,
)


def _num(row: pd.Series, *keys: str) -> float | None:
    for key in keys:
        val = pd.to_numeric(row.get(key), errors="coerce")
        if val is not None and not pd.isna(val):
            return float(val)
    return None


def _clamp_score(x: float, *, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _growth_component(val: float | None, *, floor: float = 0.0, cap: float = 50.0) -> float | None:
    if val is None or pd.isna(val):
        return None
    if float(val) <= floor:
        return 0.0
    return _clamp_score(float(val) / cap * 100.0)


def _cf_component(val: float | None) -> float | None:
    if val is None or pd.isna(val):
        return None
    if float(val) <= 0:
        return 0.0
    return _clamp_score(float(val) / 1.2 * 100.0)


def _fisher_checks(row: pd.Series) -> tuple[list[str], list[str], int, int]:
    """
    Quantitative proxy checks mapped to Fisher's 15 points.

    Returns (passed_labels, failed_labels, pass_count, quant_total).
    Points 7–9, 14–15 need scuttlebutt — not auto-scored.
    """
    passed: list[str] = []
    failed: list[str] = []

    sales = _num(row, "sales_yoy")
    np_y = _num(row, "np_yoy")
    eps = _num(row, "eps_yoy")
    sales_q = _num(row, "sales_qoq")
    ebidt = _num(row, "ebidt_yoy")
    cf = _num(row, "cf_profit")
    fpe = _num(row, "forward_pe")
    mcap = _num(row, "market_cap_cr")
    bust = bool(row.get("sales_bust"))

    # #1 Sales runway
    if sales is not None and sales >= FISHER_MIN_SALES_YOY:
        passed.append("#1 sales runway")
    else:
        failed.append("#1 sales runway")

    # #2/#3 Innovation & R&D — proxy: EBITDA/sales growth holding up
    if ebidt is not None and ebidt > 0 and sales is not None and sales > 0:
        passed.append("#2/#3 growth engine")
    elif sales is not None and sales > 10:
        passed.append("#2/#3 growth engine")
    else:
        failed.append("#2/#3 growth engine")

    # #4 Sales organization — QoQ momentum when YoY positive
    if sales is not None and sales > 0 and sales_q is not None and sales_q > 0:
        passed.append("#4 sales org")
    else:
        failed.append("#4 sales org")

    # #5 Profit margins — profitable growth
    if (np_y is not None and np_y > 0) or (eps is not None and eps > 0):
        passed.append("#5 margins")
    else:
        failed.append("#5 margins")

    # #6 Margin improvement — NP growing at least with sales
    if np_y is not None and sales is not None and np_y >= sales - 5:
        passed.append("#6 margin trend")
    else:
        failed.append("#6 margin trend")

    # #10 Cost / accounting quality — cash vs reported profit
    if cf is not None and cf >= FISHER_MIN_CF_PROFIT:
        passed.append("#10 cash quality")
    else:
        failed.append("#10 cash quality")

    # #12 Long-range outlook — avoid absurd one-quarter optics
    if not bust:
        passed.append("#12 durability")
    else:
        failed.append("#12 durability")

    # #13 Dilution guard — EPS tracks NP (rough proxy)
    if np_y is not None and eps is not None and np_y > 0 and eps > 0:
        if eps >= np_y - 20:
            passed.append("#13 no dilution")
        else:
            failed.append("#13 no dilution")
    elif eps is not None and eps > 0:
        passed.append("#13 no dilution")
    else:
        failed.append("#13 no dilution")

    # Valuation sanity (supports #12 — not overpaying for hype)
    if (
        fpe is not None
        and FISHER_PE_MIN < fpe < FISHER_PE_MAX
        and fpe < 500
    ):
        passed.append("valuation sane")
    else:
        failed.append("valuation sane")

    # Multibagger size band (optional sweet spot)
    if mcap is None or mcap <= FISHER_MCAP_MAX_CR:
        passed.append("size band")
    else:
        failed.append("size band")

    quant_total = len(passed) + len(failed)
    return passed, failed, len(passed), quant_total


def score_fisher(df: pd.DataFrame) -> pd.DataFrame:
    """
    Score candidates on Fisher-style compounding quality.

    Uses PEAD fundamentals as inputs. Qualitative Fisher points (7–9, 11, 14–15)
    are flagged for manual scuttlebutt — not scored automatically.
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    out = df.copy()
    scores: list[float | None] = []
    growth_scores: list[float | None] = []
    margin_scores: list[float | None] = []
    quality_scores: list[float | None] = []
    check_counts: list[int] = []
    check_totals: list[int] = []
    check_labels: list[str] = []
    manual_notes: list[str] = []

    for _, row in out.iterrows():
        passed, failed, pass_n, total_n = _fisher_checks(row)
        sales = _num(row, "sales_yoy")
        np_y = _num(row, "np_yoy")
        eps = _num(row, "eps_yoy")
        cf = _num(row, "cf_profit")

        g_parts = [v for v in (_growth_component(sales), _growth_component(eps)) if v is not None]
        growth = float(np.mean(g_parts)) if g_parts else None

        margin_spread = None
        if np_y is not None and sales is not None:
            margin_spread = _clamp_score(50.0 + (np_y - sales) * 1.5)
        margin = margin_spread

        quality = _cf_component(cf)
        checks_pct = (pass_n / total_n * 100.0) if total_n > 0 else None

        parts: list[tuple[float, float]] = []
        if growth is not None:
            parts.append((growth, 0.30))
        if margin is not None:
            parts.append((margin, 0.25))
        if quality is not None:
            parts.append((quality, 0.25))
        if checks_pct is not None:
            parts.append((checks_pct, 0.20))

        if not parts or pass_n < FISHER_MIN_CHECKS:
            scores.append(None)
        else:
            wsum = sum(w for _, w in parts)
            composite = sum(v * w for v, w in parts) / wsum if wsum > 0 else None
            scores.append(None if composite is None else round(float(composite), 1))

        growth_scores.append(None if growth is None else round(growth, 1))
        margin_scores.append(None if margin is None else round(margin, 1))
        quality_scores.append(None if quality is None else round(quality, 1))
        check_counts.append(pass_n)
        check_totals.append(total_n)
        check_labels.append(f"{pass_n}/{total_n}")
        manual_notes.append(
            "Scuttlebutt: #7 labor · #8 exec · #9 depth · #11 industry edge · #14 candor · #15 integrity"
        )

    out["fisher_growth"] = growth_scores
    out["fisher_margin"] = margin_scores
    out["fisher_quality"] = quality_scores
    out["fisher_checks"] = check_labels
    out["fisher_checks_pass"] = check_counts
    out["fisher_checks_total"] = check_totals
    out["fisher_manual"] = manual_notes
    out["fisher_score"] = scores
    out["pead_score"] = scores

    out = out[out["fisher_score"].notna()].copy()
    if out.empty:
        return out
    return out.sort_values(
        ["fisher_score", "fisher_checks_pass", "sales_yoy"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)


def format_fisher_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("ticker", "ticker"),
        ("name", "name"),
        ("fisher_score", "fisher_score"),
        ("fisher_checks", "quant_checks"),
        ("fisher_growth", "growth_score"),
        ("fisher_margin", "margin_score"),
        ("fisher_quality", "quality_score"),
        ("sales_yoy", "sales_yoy"),
        ("np_yoy", "np_yoy"),
        ("eps_yoy", "eps_yoy"),
        ("cf_profit", "cf_profit"),
        ("forward_pe", "forward_pe"),
        ("market_cap_cr", "market_cap_cr"),
        ("returns_pct", "returns_pct"),
        ("result_date", "result_date"),
        ("sector", "sector"),
        ("fisher_manual", "manual_scuttlebutt"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def fisher_caption() -> str:
    return (
        "Philip Fisher **15-point** multibagger scorecard — **11 quantitative checks** "
        "from quarterly fundamentals (growth runway, margins, cash quality, dilution guard). "
        "Points **7–9, 11, 14–15** need **scuttlebutt** (management, integrity, industry edge). "
        "Long-term hold · not a quarterly drift trade."
    )


__all__ = [
    "fisher_caption",
    "format_fisher_export_df",
    "score_fisher",
]
