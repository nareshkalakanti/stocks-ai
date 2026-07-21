"""Growth strategy — quantitative filters from annual yfinance statements."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import (
    GROWTH_MAX_DEBT_EQUITY,
    GROWTH_MIN_CHECKS,
    GROWTH_MIN_OPERATING_MARGIN,
    GROWTH_MIN_PROFIT_CAGR,
    GROWTH_MIN_ROE,
    GROWTH_MIN_SALES_CAGR,
)
from stocks.strategies.earnings.strategy import EBIDT_FIELDS, NET_INCOME_FIELDS
from stocks.strategies.valuation_formula.strategy import (
    EQUITY_FIELDS,
    REVENUE_FIELDS,
    _first_row,
)

COST_OF_REVENUE_FIELDS = (
    "Cost Of Revenue",
    "Reconciled Cost Of Revenue",
    "Cost Of Goods Sold",
)

GROSS_PROFIT_FIELDS = (
    "Gross Profit",
)

TOTAL_ASSETS_FIELDS = (
    "Total Assets",
)

CAGR_YEARS = 3


def _latest_prior(series: pd.Series | None) -> tuple[float | None, float | None]:
    if series is None or series.empty:
        return None, None
    s = series.dropna().astype(float).sort_index(ascending=False)
    if len(s) < 2:
        return (float(s.iloc[0]), None) if len(s) == 1 else (None, None)
    return float(s.iloc[0]), float(s.iloc[1])


def _cagr_pct(series: pd.Series | None, *, years: int = CAGR_YEARS) -> float | None:
    """CAGR from newest vs N years prior (needs years+1 annual points)."""
    if series is None or series.empty:
        return None
    s = series.dropna().astype(float).sort_index(ascending=False)
    if len(s) < years + 1:
        return None
    latest = float(s.iloc[0])
    prior = float(s.iloc[years])
    if latest <= 0 or prior <= 0:
        return None
    return round(((latest / prior) ** (1 / years) - 1) * 100, 2)


def sales_growth_yoy(financials: pd.DataFrame | None) -> float | None:
    """(Current sales − previous sales) / previous sales × 100."""
    rev = _first_row(financials, REVENUE_FIELDS)
    curr, prev = _latest_prior(rev)
    if curr is None or prev is None or prev == 0:
        return None
    return round((curr - prev) / prev * 100, 2)


def sales_cagr(financials: pd.DataFrame | None, *, years: int = CAGR_YEARS) -> float | None:
    return _cagr_pct(_first_row(financials, REVENUE_FIELDS), years=years)


def profit_cagr(financials: pd.DataFrame | None, *, years: int = CAGR_YEARS) -> float | None:
    return _cagr_pct(_first_row(financials, NET_INCOME_FIELDS), years=years)


def gross_profit_margin(financials: pd.DataFrame | None) -> float | None:
    """(Revenue − COGS) / Revenue × 100, or Gross Profit / Revenue."""
    rev = _first_row(financials, REVENUE_FIELDS)
    if rev is None or rev.empty:
        return None
    revenue = float(rev.sort_index(ascending=False).iloc[0])
    if revenue == 0:
        return None

    gp = _first_row(financials, GROSS_PROFIT_FIELDS)
    if gp is not None and not gp.empty:
        gross = float(gp.sort_index(ascending=False).iloc[0])
        return round(gross / revenue * 100, 2)

    cogs = _first_row(financials, COST_OF_REVENUE_FIELDS)
    if cogs is None or cogs.empty:
        return None
    cost = float(cogs.sort_index(ascending=False).iloc[0])
    return round((revenue - cost) / revenue * 100, 2)


def net_profit_margin(financials: pd.DataFrame | None) -> float | None:
    """Net Income / Revenue × 100."""
    rev = _first_row(financials, REVENUE_FIELDS)
    ni = _first_row(financials, NET_INCOME_FIELDS)
    if rev is None or ni is None or rev.empty or ni.empty:
        return None
    revenue = float(rev.sort_index(ascending=False).iloc[0])
    net = float(ni.sort_index(ascending=False).iloc[0])
    if revenue == 0:
        return None
    return round(net / revenue * 100, 2)


def operating_margin(financials: pd.DataFrame | None) -> float | None:
    """Operating Income / Revenue × 100."""
    rev = _first_row(financials, REVENUE_FIELDS)
    op = _first_row(financials, EBIDT_FIELDS)
    if rev is None or op is None or rev.empty or op.empty:
        return None
    revenue = float(rev.sort_index(ascending=False).iloc[0])
    operating = float(op.sort_index(ascending=False).iloc[0])
    if revenue == 0:
        return None
    return round(operating / revenue * 100, 2)


def return_on_assets(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
) -> float | None:
    """Net Income / Average Total Assets × 100."""
    ni = _first_row(financials, NET_INCOME_FIELDS)
    assets = _first_row(balance_sheet, TOTAL_ASSETS_FIELDS)
    if ni is None or assets is None or ni.empty or assets.empty:
        return None
    net = float(ni.sort_index(ascending=False).iloc[0])
    a = assets.dropna().astype(float).sort_index(ascending=False)
    if a.empty:
        return None
    if len(a) >= 2:
        avg_assets = (float(a.iloc[0]) + float(a.iloc[1])) / 2.0
    else:
        avg_assets = float(a.iloc[0])
    if avg_assets == 0:
        return None
    return round(net / avg_assets * 100, 2)


def return_on_equity(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
) -> float | None:
    """Net Income / Average Shareholders' Equity × 100."""
    ni = _first_row(financials, NET_INCOME_FIELDS)
    equity = _first_row(balance_sheet, EQUITY_FIELDS)
    if ni is None or equity is None or ni.empty or equity.empty:
        return None
    net = float(ni.sort_index(ascending=False).iloc[0])
    eq = equity.dropna().astype(float).sort_index(ascending=False)
    if eq.empty:
        return None
    if len(eq) >= 2:
        avg_equity = (float(eq.iloc[0]) + float(eq.iloc[1])) / 2.0
    else:
        avg_equity = float(eq.iloc[0])
    if avg_equity == 0:
        return None
    return round(net / avg_equity * 100, 2)


def debt_to_equity_ratio(info: dict | None) -> float | None:
    """Yahoo debtToEquity is Total Debt/Equity × 100 — return true ratio."""
    info = info or {}
    raw = info.get("debtToEquity")
    if raw is None or pd.isna(raw):
        return None
    val = float(raw)
    # Yahoo reports D/E × 100 (e.g. 79.5 → 0.80).
    if abs(val) > 10:
        val = val / 100.0
    return round(val, 2)


def pe_vs_industry(info: dict | None) -> tuple[float | None, float | None, bool | None]:
    """
    Trailing PE vs industry PE when Yahoo provides both.

    Returns (trailing_pe, industry_pe, pe_ok) where pe_ok is True when
    trailing PE is at or below industry PE.
    """
    info = info or {}
    pe = info.get("trailingPE")
    ind_pe = info.get("industryPE") or info.get("industryTrailingPE")
    pe_f = float(pe) if pe is not None and not pd.isna(pe) else None
    ind_f = float(ind_pe) if ind_pe is not None and not pd.isna(ind_pe) else None
    if pe_f is not None:
        pe_f = round(pe_f, 1)
    if ind_f is not None:
        ind_f = round(ind_f, 1)
    pe_ok: bool | None = None
    if pe_f is not None and ind_f is not None and ind_f > 0:
        pe_ok = pe_f <= ind_f
    return pe_f, ind_f, pe_ok


def compute_growth_metrics(
    financials: pd.DataFrame | None,
    balance_sheet: pd.DataFrame | None,
    info: dict | None,
) -> dict:
    """Compute all growth-screen metrics from statements + info."""
    info = info or {}
    pe, industry_pe, pe_ok = pe_vs_industry(info)

    sales_g = sales_growth_yoy(financials)
    if sales_g is None:
        rg = info.get("revenueGrowth")
        if rg is not None and not pd.isna(rg):
            sales_g = round(float(rg) * 100, 2)

    gpm = gross_profit_margin(financials)
    if gpm is None:
        gm = info.get("grossMargins")
        if gm is not None and not pd.isna(gm):
            gpm = round(float(gm) * 100, 2)

    npm = net_profit_margin(financials)
    if npm is None:
        pm = info.get("profitMargins")
        if pm is not None and not pd.isna(pm):
            npm = round(float(pm) * 100, 2)

    opm = operating_margin(financials)
    if opm is None:
        om = info.get("operatingMargins")
        if om is not None and not pd.isna(om):
            opm = round(float(om) * 100, 2)

    roa = return_on_assets(financials, balance_sheet)
    if roa is None:
        raw = info.get("returnOnAssets")
        if raw is not None and not pd.isna(raw):
            roa = round(float(raw) * 100, 2)

    roe = return_on_equity(financials, balance_sheet)
    if roe is None:
        raw = info.get("returnOnEquity")
        if raw is not None and not pd.isna(raw):
            roe = round(float(raw) * 100, 2)

    return {
        "sales_growth": sales_g,
        "sales_cagr": sales_cagr(financials),
        "profit_cagr": profit_cagr(financials),
        "gross_margin": gpm,
        "net_margin": npm,
        "operating_margin": opm,
        "roa": roa,
        "roe": roe,
        "debt_to_equity": debt_to_equity_ratio(info),
        "pe_ratio": pe,
        "industry_pe": industry_pe,
        "pe_ok": pe_ok,
    }


def _check_pass(label: str, ok: bool, passed: list[str], failed: list[str]) -> None:
    if ok:
        passed.append(label)
    else:
        failed.append(label)


def score_growth(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply quantitative growth filters and rank by checks passed.

    Pass rules (defaults from config / slide):
    - Debt/Equity ≤ 2
    - Sales CAGR ≥ 15%
    - Profit CAGR ≥ 15%
    - Operating margin ≥ 15%
    - ROE ≥ 15%
    - PE ≤ industry PE when industry PE is available (soft — skipped if missing)
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    out = df.copy()
    scores: list[float | None] = []
    check_labels: list[str] = []
    check_pass: list[int] = []
    check_total: list[int] = []

    for _, row in out.iterrows():
        passed: list[str] = []
        failed: list[str] = []

        dte = pd.to_numeric(row.get("debt_to_equity"), errors="coerce")
        _check_pass(
            "D/E",
            dte is not None and not pd.isna(dte) and float(dte) <= GROWTH_MAX_DEBT_EQUITY,
            passed,
            failed,
        )

        sales = pd.to_numeric(row.get("sales_cagr"), errors="coerce")
        _check_pass(
            "Sales CAGR",
            sales is not None and not pd.isna(sales) and float(sales) >= GROWTH_MIN_SALES_CAGR,
            passed,
            failed,
        )

        profit = pd.to_numeric(row.get("profit_cagr"), errors="coerce")
        _check_pass(
            "Profit CAGR",
            profit is not None
            and not pd.isna(profit)
            and float(profit) >= GROWTH_MIN_PROFIT_CAGR,
            passed,
            failed,
        )

        opm = pd.to_numeric(row.get("operating_margin"), errors="coerce")
        _check_pass(
            "Op. margin",
            opm is not None
            and not pd.isna(opm)
            and float(opm) >= GROWTH_MIN_OPERATING_MARGIN,
            passed,
            failed,
        )

        roe = pd.to_numeric(row.get("roe"), errors="coerce")
        _check_pass(
            "ROE",
            roe is not None and not pd.isna(roe) and float(roe) >= GROWTH_MIN_ROE,
            passed,
            failed,
        )

        pe_ok = row.get("pe_ok")
        if pe_ok is True:
            passed.append("PE vs ind.")
        elif pe_ok is False:
            failed.append("PE vs ind.")
        # None → industry PE missing; skip (do not fail)

        n_pass = len(passed)
        n_total = n_pass + len(failed)
        check_pass.append(n_pass)
        check_total.append(n_total)
        check_labels.append(f"{n_pass}/{n_total}")

        if n_pass < GROWTH_MIN_CHECKS or n_total == 0:
            scores.append(None)
        else:
            # Prefer more checks + higher sales CAGR.
            sales_f = float(sales) if sales is not None and not pd.isna(sales) else 0.0
            scores.append(round(n_pass / n_total * 100 + min(sales_f, 50) * 0.2, 1))

    out["growth_checks"] = check_labels
    out["growth_checks_pass"] = check_pass
    out["growth_checks_total"] = check_total
    out["growth_score"] = scores

    out = out[out["growth_score"].notna()].copy()
    if out.empty:
        return out
    return out.sort_values(
        ["growth_checks_pass", "growth_score", "sales_cagr", "roe"],
        ascending=[False, False, False, False],
        na_position="last",
    ).reset_index(drop=True)


def format_growth_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("ticker", "ticker"),
        ("name", "name"),
        ("growth_score", "growth_score"),
        ("growth_checks", "quant_checks"),
        ("sales_growth", "sales_growth_yoy"),
        ("sales_cagr", "sales_cagr_3y"),
        ("profit_cagr", "profit_cagr_3y"),
        ("gross_margin", "gross_margin"),
        ("net_margin", "net_margin"),
        ("operating_margin", "operating_margin"),
        ("roa", "roa"),
        ("roe", "roe"),
        ("debt_to_equity", "debt_to_equity"),
        ("pe_ratio", "pe"),
        ("industry_pe", "industry_pe"),
        ("market_cap_cr", "market_cap_cr"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def growth_caption() -> str:
    return (
        f"Growth screen — quantitative filters first: "
        f"**D/E ≤ {GROWTH_MAX_DEBT_EQUITY:g}**, "
        f"**Sales/Profit CAGR ≥ {GROWTH_MIN_SALES_CAGR:g}%**, "
        f"**Op. margin ≥ {GROWTH_MIN_OPERATING_MARGIN:g}%**, "
        f"**ROE ≥ {GROWTH_MIN_ROE:g}%**, PE vs industry when available. "
        "Also shows sales growth, gross/net margin, and ROA from annual statements. "
        "Qualitative factors (PMI, ease of business, govt schemes) need manual review."
    )


__all__ = [
    "compute_growth_metrics",
    "debt_to_equity_ratio",
    "format_growth_export_df",
    "gross_profit_margin",
    "growth_caption",
    "net_profit_margin",
    "operating_margin",
    "pe_vs_industry",
    "profit_cagr",
    "return_on_assets",
    "return_on_equity",
    "sales_cagr",
    "sales_growth_yoy",
    "score_growth",
]
