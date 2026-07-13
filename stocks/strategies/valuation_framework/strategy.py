"""10-year sales growth · terminal multiple · discount-to-today valuation."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from stocks.strategies.formula_100x.strategy import EBIT_FIELDS, _first_row, _to_inr_cr
from stocks.strategies.pead2.strategy import NET_INCOME_FIELDS
from stocks.strategies.valuation_formula.strategy import REVENUE_FIELDS

DEFAULT_GROWTH_RATES_PCT: tuple[float, ...] = (15.0, 20.0, 25.0, 30.0, 35.0)


@dataclass(frozen=True)
class FrameworkAssumptions:
    base_year: int
    current_sales_cr: float
    market_cap_cr: float
    sales_multiple: float = 5.0
    discount_rate_pct: float = 15.0
    projection_years: int = 10
    growth_rates_pct: tuple[float, ...] = DEFAULT_GROWTH_RATES_PCT


@dataclass(frozen=True)
class GrowthScenario:
    growth_pct: float
    yearly_sales: tuple[float, ...]
    year10_sales_cr: float
    valuation_at_multiple_cr: float
    discounted_value_cr: float
    margin_of_safety_pct: float | None
    undervalued: bool


@dataclass(frozen=True)
class FrameworkResult:
    assumptions: FrameworkAssumptions
    scenarios: tuple[GrowthScenario, ...]
    best_undervalued_growth_pct: float | None = None

    def scenario_at(self, growth_pct: float) -> GrowthScenario | None:
        for row in self.scenarios:
            if abs(row.growth_pct - growth_pct) < 0.01:
                return row
        return None


# Zerodha Varsity Lenskart backtest (₹ Cr) — validation fixture.
LENSKART_PL_ROWS: tuple[dict[str, object], ...] = (
    {"fy": "Mar 2023", "sales": 3788.0, "operating_profit": 264.0, "net_profit": -68.0},
    {"fy": "Mar 2024", "sales": 5428.0, "operating_profit": 674.0, "net_profit": -17.0},
    {"fy": "Mar 2025", "sales": 6653.0, "operating_profit": 976.0, "net_profit": 296.0},
)

LENSKART_ASSUMPTIONS = FrameworkAssumptions(
    base_year=2026,
    current_sales_cr=8647.0,
    market_cap_cr=90979.0,
    sales_multiple=5.0,
    discount_rate_pct=15.0,
    projection_years=10,
)

LENSKART_SALES_15PCT_YEARLY: tuple[float, ...] = (
    9944.0,
    11436.0,
    13151.0,
    15124.0,
    17392.0,
    20001.0,
    23001.0,
    26451.0,
    30419.0,
    34982.0,
)


def _fy_label(ts) -> str:
    try:
        return pd.Timestamp(ts).strftime("%b %Y")
    except (TypeError, ValueError):
        return str(ts)


def annual_profit_and_loss(
    financials: pd.DataFrame | None,
    *,
    max_years: int = 5,
) -> list[dict[str, object]]:
    """Annual sales / operating profit / net profit in ₹ Cr (oldest → newest)."""
    rev = _first_row(financials, REVENUE_FIELDS)
    op = _first_row(financials, EBIT_FIELDS)
    np_s = _first_row(financials, NET_INCOME_FIELDS)
    if rev is None or rev.empty:
        return []

    cols = sorted(rev.index, reverse=True)[:max_years]
    cols = sorted(cols)
    rows: list[dict[str, object]] = []
    for col in cols:
        sales = _to_inr_cr(float(rev[col])) if col in rev.index and not pd.isna(rev[col]) else None
        if sales is None:
            continue
        op_val = None
        if op is not None and col in op.index and not pd.isna(op[col]):
            op_val = _to_inr_cr(float(op[col]))
        np_val = None
        if np_s is not None and col in np_s.index and not pd.isna(np_s[col]):
            np_val = _to_inr_cr(float(np_s[col]))
        rows.append(
            {
                "fy": _fy_label(col),
                "sales": sales,
                "operating_profit": op_val,
                "net_profit": np_val,
            }
        )
    return rows


def project_sales_yearly(
    base_sales_cr: float,
    growth_pct: float,
    *,
    years: int = 10,
) -> list[float]:
    if base_sales_cr <= 0 or years <= 0:
        return []
    g = float(growth_pct) / 100.0
    out: list[float] = []
    sales = float(base_sales_cr)
    for _ in range(years):
        sales *= 1.0 + g
        out.append(round(sales))
    return out


def discounted_terminal_value(
    terminal_value_cr: float,
    discount_rate_pct: float,
    *,
    years: int,
) -> float:
    if terminal_value_cr <= 0 or years <= 0:
        return 0.0
    d = float(discount_rate_pct) / 100.0
    return round(terminal_value_cr / ((1.0 + d) ** years))


def margin_of_safety_pct(discounted_cr: float, market_cap_cr: float) -> float | None:
    if market_cap_cr is None or market_cap_cr <= 0:
        return None
    return round((discounted_cr / market_cap_cr - 1.0) * 100.0, 1)


def evaluate_growth_scenario(
    assumptions: FrameworkAssumptions,
    growth_pct: float,
) -> GrowthScenario:
    yearly = project_sales_yearly(
        assumptions.current_sales_cr,
        growth_pct,
        years=assumptions.projection_years,
    )
    year10 = yearly[-1] if yearly else 0.0
    terminal = round(year10 * assumptions.sales_multiple)
    discounted = discounted_terminal_value(
        terminal,
        assumptions.discount_rate_pct,
        years=assumptions.projection_years,
    )
    mos = margin_of_safety_pct(discounted, assumptions.market_cap_cr)
    return GrowthScenario(
        growth_pct=float(growth_pct),
        yearly_sales=tuple(yearly),
        year10_sales_cr=year10,
        valuation_at_multiple_cr=terminal,
        discounted_value_cr=discounted,
        margin_of_safety_pct=mos,
        undervalued=discounted > assumptions.market_cap_cr,
    )


def run_valuation_framework(assumptions: FrameworkAssumptions) -> FrameworkResult:
    scenarios = tuple(
        evaluate_growth_scenario(assumptions, g) for g in assumptions.growth_rates_pct
    )
    undervalued = [s.growth_pct for s in scenarios if s.undervalued]
    best = max(undervalued) if undervalued else None
    return FrameworkResult(assumptions=assumptions, scenarios=scenarios, best_undervalued_growth_pct=best)


def projection_year_labels(base_year: int, years: int = 10) -> list[int]:
    return [base_year + i for i in range(1, years + 1)]


def sales_trajectory_table(result: FrameworkResult) -> pd.DataFrame:
    """Years × growth-rate sales grid (₹ Cr)."""
    years = projection_year_labels(result.assumptions.base_year, result.assumptions.projection_years)
    data: dict[str, list[float]] = {"Year": years}
    for sc in result.scenarios:
        col = f"{sc.growth_pct:g}%"
        data[col] = list(sc.yearly_sales)
    return pd.DataFrame(data)


def sensitivity_table(result: FrameworkResult) -> pd.DataFrame:
    rows = []
    for sc in result.scenarios:
        rows.append(
            {
                "Sales growth": f"{sc.growth_pct:g}%",
                f"Valuation at {result.assumptions.sales_multiple:g}x (₹ Cr)": sc.valuation_at_multiple_cr,
                "Discounted value (₹ Cr)": sc.discounted_value_cr,
                "Current mkt cap (₹ Cr)": result.assumptions.market_cap_cr,
                "Margin of safety %": sc.margin_of_safety_pct,
                "Undervalued": sc.undervalued,
            }
        )
    return pd.DataFrame(rows)


def lenskart_reference_result() -> FrameworkResult:
    return run_valuation_framework(LENSKART_ASSUMPTIONS)


def passes_undervalued_filter(
    result: FrameworkResult,
    *,
    min_growth_pct: float | None = None,
    require_any_growth: bool = True,
) -> bool:
    scenarios = result.scenarios
    if min_growth_pct is not None:
        sc = result.scenario_at(min_growth_pct)
        return bool(sc and sc.undervalued)
    if require_any_growth:
        return any(s.undervalued for s in scenarios)
    return False


def scan_row_from_result(
    ticker: str,
    name: str,
    result: FrameworkResult,
    *,
    market: str | None = None,
) -> dict[str, object]:
    sc15 = result.scenario_at(15.0)
    sc20 = result.scenario_at(20.0)
    sc25 = result.scenario_at(25.0)
    sc30 = result.scenario_at(30.0)
    sc35 = result.scenario_at(35.0)
    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "sales_cr": result.assumptions.current_sales_cr,
        "market_cap_cr": result.assumptions.market_cap_cr,
        "disc_15_cr": sc15.discounted_value_cr if sc15 else None,
        "disc_20_cr": sc20.discounted_value_cr if sc20 else None,
        "disc_25_cr": sc25.discounted_value_cr if sc25 else None,
        "disc_30_cr": sc30.discounted_value_cr if sc30 else None,
        "disc_35_cr": sc35.discounted_value_cr if sc35 else None,
        "mos_15_pct": sc15.margin_of_safety_pct if sc15 else None,
        "mos_20_pct": sc20.margin_of_safety_pct if sc20 else None,
        "best_undervalued_growth_pct": result.best_undervalued_growth_pct,
        "pass_undervalued": passes_undervalued_filter(result),
        "pass_15pct": bool(sc15 and sc15.undervalued),
        "pass_20pct": bool(sc20 and sc20.undervalued),
        "pass_25pct": bool(sc25 and sc25.undervalued),
        "pass_30pct": bool(sc30 and sc30.undervalued),
        "pass_35pct": bool(sc35 and sc35.undervalued),
    }
