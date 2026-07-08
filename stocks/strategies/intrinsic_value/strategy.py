"""Intrinsic Value ranking — 3Y sales growth, 3Y ROCE avg, P/B (IV Equity Advisors style)."""

from __future__ import annotations

import pandas as pd

from stocks.market.fundamentals_service import compute_roce_metrics
from stocks.strategies.earnings.strategy import EPS_FIELDS
from stocks.strategies.valuation_formula.strategy import REVENUE_FIELDS, _first_row


def sales_growth_3y_cagr(financials: pd.DataFrame | None) -> float | None:
    """3-year revenue CAGR from annual statements (newest vs 3 years prior)."""
    rev = _first_row(financials, REVENUE_FIELDS)
    if rev is None or len(rev) < 4:
        return None
    s = rev.sort_index(ascending=False)
    latest = float(s.iloc[0])
    prior = float(s.iloc[3])
    if latest <= 0 or prior <= 0:
        return None
    return round(((latest / prior) ** (1 / 3) - 1) * 100, 2)


def roce_3y_average(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
) -> float | None:
    """Mean ROCE over the latest three annual periods."""
    if financials is None or financials.empty:
        return None
    if balance_sheet is None or balance_sheet.empty:
        return None
    vals: list[float] = []
    for col in financials.columns[:3]:
        inc_slice = financials[[col]]
        bs_col = col if col in balance_sheet.columns else balance_sheet.columns[0]
        bs_slice = balance_sheet[[bs_col]]
        roce = compute_roce_metrics(inc_slice, bs_slice).get("roce_pct")
        if roce is not None and not pd.isna(roce):
            vals.append(float(roce))
    if not vals:
        return None
    return round(sum(vals) / len(vals), 2)


def price_to_book(info: dict, *, price: float | None = None) -> float | None:
    pb = info.get("priceToBook")
    if pb is not None and not pd.isna(pb) and float(pb) > 0:
        return round(float(pb), 2)
    bv = info.get("bookValue")
    px = price
    if px is None:
        raw = info.get("regularMarketPrice") or info.get("currentPrice")
        px = float(raw) if raw is not None and not pd.isna(raw) else None
    if bv is not None and px is not None and float(bv) > 0:
        return round(float(px) / float(bv), 2)
    return None


def _quarterly_eps(income: pd.DataFrame | None) -> pd.Series | None:
    row = _first_row(income, EPS_FIELDS)
    if row is None or row.empty:
        return None
    s = row.dropna().sort_index().astype(float)
    return s if not s.empty else None


def _pe_from_eps(price: float, eps: float) -> float | None:
    if eps == 0:
        return None
    return round(price / eps, 1)


def pe_ratio_and_forward(
    price: float | None,
    info: dict | None,
    quarterly_income: pd.DataFrame | None,
) -> tuple[float | None, float | None]:
    """
    Trailing PE = price ÷ last 12M EPS (reported).
    Forward PE = price ÷ next-year / run-rate EPS (forecast or latest quarter × 4).
    """
    if price is None or price <= 0:
        return None, None

    pe: float | None = None
    forward: float | None = None
    info = info or {}

    trailing = info.get("trailingPE")
    if trailing is not None and not pd.isna(trailing):
        pe = round(float(trailing), 1)

    fwd = info.get("forwardPE")
    if fwd is not None and not pd.isna(fwd):
        forward = round(float(fwd), 1)

    eps_q = _quarterly_eps(quarterly_income)
    if eps_q is not None:
        if pe is None:
            ttm = float(eps_q.iloc[-4:].sum()) if len(eps_q) >= 4 else float(eps_q.sum())
            pe = _pe_from_eps(price, ttm)
        if forward is None:
            fwd_eps = info.get("forwardEps")
            if fwd_eps is not None and not pd.isna(fwd_eps):
                forward = _pe_from_eps(price, float(fwd_eps))
            else:
                forward = _pe_from_eps(price, float(eps_q.iloc[-1]) * 4.0)

    return pe, forward


def rank_intrinsic_value(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rank within universe: higher growth & ROCE, lower P/B → lower total score (best).

    Total score = growth_rank + roce_rank + pb_rank (screenshot logic).
    """
    if df is None or df.empty:
        return pd.DataFrame()
    need = ("sales_growth_3y", "roce_3y", "pb")
    for col in need:
        if col not in df.columns:
            return pd.DataFrame()
    work = df.copy()
    work = work.drop(
        columns=["rank", "growth_rank", "roce_rank", "pb_rank", "total_score"],
        errors="ignore",
    )
    for col in need:
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=list(need))
    if work.empty:
        return work

    work["growth_rank"] = work["sales_growth_3y"].rank(ascending=False, method="min").astype(int)
    work["roce_rank"] = work["roce_3y"].rank(ascending=False, method="min").astype(int)
    work["pb_rank"] = work["pb"].rank(ascending=True, method="min").astype(int)
    work["total_score"] = work["growth_rank"] + work["roce_rank"] + work["pb_rank"]
    work = work.sort_values(
        ["total_score", "growth_rank", "roce_rank", "pb_rank"],
        ascending=[True, True, True, True],
    )
    work.insert(0, "rank", range(1, len(work) + 1))
    return work.reset_index(drop=True)


def sector_headwind_tailwind(
    ranked: pd.DataFrame,
    *,
    industry_col: str = "sub_sector",
    min_companies: int = 2,
) -> pd.DataFrame:
    """
    Sector tailwind score vs market medians on growth, ROCE, and P/B.

    Positive score → tailwind (sector fundamentals better than market).
    """
    if ranked is None or ranked.empty or industry_col not in ranked.columns:
        return pd.DataFrame()

    market_g = ranked["sales_growth_3y"].median()
    market_r = ranked["roce_3y"].median()
    market_pb = ranked["pb"].median()

    rows: list[dict] = []
    grouped = ranked.groupby(ranked[industry_col].astype(str).str.strip(), dropna=True)
    for sector, grp in grouped:
        if not sector or sector.lower() in ("nan", "none", ""):
            continue
        if len(grp) < min_companies:
            continue
        sg = grp["sales_growth_3y"].median()
        sr = grp["roce_3y"].median()
        sp = grp["pb"].median()

        growth_ratio = (sg / market_g) if market_g and market_g > 0 else 1.0
        roce_ratio = (sr / market_r) if market_r and market_r > 0 else 1.0
        pb_ratio = (market_pb / sp) if sp and sp > 0 and market_pb else 1.0

        composite = (growth_ratio + roce_ratio + pb_ratio) / 3.0
        score = round(composite - 1.0, 4)
        if score >= 0.05:
            indicator = "TAILWIND"
        elif score <= -0.05:
            indicator = "HEADWIND"
        else:
            indicator = "NEUTRAL"

        rows.append(
            {
                "sector": sector,
                "companies": len(grp),
                "score": score,
                "indicator": indicator,
                "median_growth_3y": round(float(sg), 2) if pd.notna(sg) else None,
                "median_roce_3y": round(float(sr), 2) if pd.notna(sr) else None,
                "median_pb": round(float(sp), 2) if pd.notna(sp) else None,
                "avg_total_score": round(float(grp["total_score"].mean()), 1),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
