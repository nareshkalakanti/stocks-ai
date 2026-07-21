"""Distressed / surveillance turnaround — best among the vulnerable."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stocks.core.config import (
    DISTRESS_ASSUMED_DRAWDOWN_MIN,
    DISTRESS_MCAP_SWEET_MAX_CR,
)
from stocks.market.nse_surveillance import load_distress_seed_tickers


def _num(row: pd.Series, *keys: str) -> float | None:
    for key in keys:
        val = pd.to_numeric(row.get(key), errors="coerce")
        if val is not None and not pd.isna(val):
            return float(val)
    snap = row.get("snapshot")
    if isinstance(snap, dict):
        for key in keys:
            val = pd.to_numeric(snap.get(key), errors="coerce")
            if val is not None and not pd.isna(val):
                return float(val)
    return None


def _drawdown_from_high_pct(row: pd.Series) -> float | None:
    price = _num(row, "price")
    high = _num(row, "w52_high")
    if price is None or high is None or high <= 0:
        return None
    return round((price / high - 1.0) * 100.0, 1)


def _bounce_from_low_pct(row: pd.Series) -> float | None:
    price = _num(row, "price")
    low = _num(row, "w52_low")
    if price is None or low is None or low <= 0:
        return None
    return round((price / low - 1.0) * 100.0, 1)


def _stage_penalty(surv_type: str, surv_stage: str) -> float:
    """Deeper GSM stages are harder turnarounds; early ASM is more tradable."""
    text = f"{surv_type} {surv_stage}".upper()
    if "SEED" in text or "MONITOR" in text:
        return 0.0
    if "GSM" in text:
        if "IV" in text or "STAGE 4" in text or "STAGE IV" in text:
            return 18.0
        if "III" in text or "STAGE 3" in text or "STAGE III" in text:
            return 12.0
        if "II" in text or "STAGE 2" in text or "STAGE II" in text:
            return 6.0
        return 4.0
    if "ASM" in text:
        if "IV" in text or "4" in text:
            return 10.0
        if "III" in text or "3" in text:
            return 6.0
        return 0.0
    return 2.0


def _distress_signals(row: pd.Series) -> list[str]:
    flags: list[str] = []
    eps = _num(row, "eps_yoy")
    sales = _num(row, "sales_yoy")
    np_y = _num(row, "np_yoy")
    pe = _num(row, "forward_pe", "pe_ratio", "pe")
    dd = _drawdown_from_high_pct(row)
    if eps is not None and eps < 0:
        flags.append("neg_eps_yoy")
    if np_y is not None and np_y < 0:
        flags.append("neg_np_yoy")
    if pe is not None and (pe >= 80 or pe >= 900):
        flags.append("stressed_pe")
    if dd is not None and dd <= -abs(DISTRESS_ASSUMED_DRAWDOWN_MIN):
        flags.append("drawdown")
    if sales is not None and sales < -15:
        flags.append("sales_pressure")
    surv = safe_surv(row)
    if surv and surv != "SEED":
        flags.append("surveillance")
    return flags


def safe_surv(row: pd.Series) -> str:
    return str(row.get("surv_type") or "").strip().upper()


def score_distress_turnaround(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rank surveillance / seed names for 1Y recovery / multibagger monitoring.

    Reverse-engineered from LotusDew-style distressed surveillance baskets and
    the seed set (ATAM, BPL, DGCONTENT, GPTINFRA, HMT, LOKESHMACH, MIRCELECTR,
    TEAMGTY):

    - Universe = exchange surveillance ∪ seed monitors
    - Prefer earnings/price stress with early recovery tells
      (sales holding up vs EPS, bounce off lows, positive recent returns)
    - Soft preference for smaller caps; penalise deep GSM stages
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    seed = set(load_distress_seed_tickers())
    out = df.copy()
    scores: list[float | None] = []
    drawdowns: list[float | None] = []
    bounces: list[float | None] = []
    signal_lists: list[str] = []
    reasons: list[str] = []

    for _, row in out.iterrows():
        ticker = str(row.get("ticker") or "").upper()
        is_seed = ticker in seed
        flags = _distress_signals(row)
        dd = _drawdown_from_high_pct(row)
        bounce = _bounce_from_low_pct(row)
        eps = _num(row, "eps_yoy")
        sales = _num(row, "sales_yoy")
        returns = _num(row, "returns_pct")
        pe = _num(row, "forward_pe", "pe_ratio", "pe")
        pb = _num(row, "price_to_book", "pb")
        mcap = _num(row, "market_cap_cr")
        surv_type = safe_surv(row)
        surv_stage = str(row.get("surv_stage") or "")

        drawdowns.append(dd)
        bounces.append(bounce)
        signal_lists.append(",".join(flags))

        # Gate: seed always kept; others need distress or surveillance flag.
        if not is_seed and not flags:
            scores.append(None)
            reasons.append("no_distress")
            continue

        score = 30.0 if is_seed else 22.0

        # Drawdown sweet spot (deep but not obliterated).
        if dd is not None:
            if -70 <= dd <= -20:
                score += 18.0
            elif -85 <= dd < -70:
                score += 10.0
            elif -20 < dd <= -10:
                score += 6.0

        # Bounce off lows = recovery tape.
        if bounce is not None:
            if bounce >= 80:
                score += 22.0
            elif bounce >= 40:
                score += 16.0
            elif bounce >= 15:
                score += 10.0
            elif bounce >= 5:
                score += 5.0

        # Operating turnaround: sales better than EPS collapse.
        if sales is not None and eps is not None and sales > eps + 10:
            score += 18.0
        elif sales is not None and sales >= 0:
            score += 10.0
        elif sales is not None and sales > -15:
            score += 5.0

        # Price already turning (post-result / recent returns).
        if returns is not None:
            if returns >= 40:
                score += 22.0
            elif returns >= 10:
                score += 12.0
            elif returns >= 0:
                score += 5.0
            elif returns <= -25:
                score -= 6.0

        # Stressed PE from depressed earnings can mean asymmetric recovery.
        if pe is not None:
            if pe >= 900:
                score += 6.0
            elif pe >= 80:
                score += 4.0
            elif 0 < pe <= 18:
                score += 8.0  # cheap survivor (GPTINFRA-like)

        if pb is not None and 0 < pb <= 3.5:
            score += 6.0

        if mcap is not None:
            if mcap <= DISTRESS_MCAP_SWEET_MAX_CR:
                score += 8.0
            elif mcap <= 2000:
                score += 4.0
            elif mcap >= 10000:
                score -= 4.0

        score -= _stage_penalty(surv_type, surv_stage)
        score = float(np.clip(score, 0.0, 100.0))
        scores.append(round(score, 1))

        bits = []
        if is_seed:
            bits.append("seed")
        if surv_type and surv_type != "SEED":
            bits.append(surv_type.lower())
        if dd is not None:
            bits.append(f"dd{dd:.0f}")
        if sales is not None and eps is not None and sales > eps:
            bits.append("sales>eps")
        reasons.append("|".join(bits) or "watch")

    out["drawdown_pct"] = drawdowns
    out["bounce_pct"] = bounces
    out["distress_flags"] = signal_lists
    out["distress_reason"] = reasons
    out["pead_score"] = scores
    out = out[out["pead_score"].notna()].copy()
    if out.empty:
        return out
    return out.sort_values(
        ["pead_score", "bounce_pct"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)


def format_distress_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("ticker", "ticker"),
        ("name", "name"),
        ("pead_score", "distress_score"),
        ("surv_type", "surv_type"),
        ("surv_stage", "surv_stage"),
        ("distress_flags", "distress_flags"),
        ("distress_reason", "reason"),
        ("drawdown_pct", "drawdown_pct"),
        ("bounce_pct", "bounce_from_low_pct"),
        ("forward_pe", "forward_pe"),
        ("pe_ratio", "pe_ratio"),
        ("eps_yoy", "eps_yoy"),
        ("sales_yoy", "sales_yoy"),
        ("returns_pct", "returns_pct"),
        ("market_cap_cr", "market_cap_cr"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def distress_caption() -> str:
    seeds = ", ".join(load_distress_seed_tickers()[:8])
    return (
        "**Distressed Turnaround** (experimental): screens exchange **ASM/GSM** names "
        "(Pocketful/NSE when available) plus **distress-like** PEAD-cache proxies — "
        "best among the vulnerable via earnings stress + early turnaround tells "
        "(sales holding vs EPS, bounce off lows, stressed PE). "
        f"Seed monitors: {seeds}. For tracking only — not advice."
    )


__all__ = [
    "distress_caption",
    "format_distress_export_df",
    "score_distress_turnaround",
]
