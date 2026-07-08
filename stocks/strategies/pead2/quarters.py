"""Quarterly panel for PEAD expand — Sales, OP, NP, EPS."""

from __future__ import annotations

import pandas as pd

from stocks.strategies.earnings.strategy import streak_up

PEAD2_QUARTER_PANEL = 5

_MONTH_ORDER = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _parse_quarter_label(label: str) -> tuple[int, int] | None:
    """Parse ``Mar 2026`` → (year, month)."""
    parts = str(label or "").strip().split()
    if len(parts) < 2:
        return None
    month = _MONTH_ORDER.get(parts[0][:3].lower())
    try:
        year = int(parts[1])
    except ValueError:
        return None
    if month is None:
        return None
    return year, month


def _panel_is_newest_first(labels: list) -> bool:
    if len(labels) < 2:
        return False
    first = _parse_quarter_label(labels[0])
    last = _parse_quarter_label(labels[-1])
    if not first or not last:
        return False
    return first > last


def yoy_pair_from_panel(
    values: list,
    labels: list | None = None,
) -> tuple[float | None, float | None]:
    """
    Latest vs prior-year quarter values from a 5-column panel.

    ``build_quarter_panel`` uses oldest-first columns; some legacy rows are newest-first.
    """
    if len(values) < 5:
        return None, None
    if labels and len(labels) >= 5 and _panel_is_newest_first(labels):
        latest_raw, prior_raw = values[0], values[4]
    else:
        latest_raw, prior_raw = values[-1], values[0]
    try:
        latest = float(latest_raw) if latest_raw is not None else None
        prior = float(prior_raw) if prior_raw is not None else None
    except (TypeError, ValueError):
        return None, None
    return latest, prior


def _quarter_label(ts: pd.Timestamp) -> str:
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return f"{months[ts.month - 1]} {ts.year}"


def _inr_crore_divisor(values: list[float]) -> float:
    """Divisor to convert yfinance INR amounts (rupees) to Rs. crores."""
    nums = [abs(v) for v in values if v is not None and not pd.isna(v)]
    if not nums:
        return 1.0
    # yfinance reports Indian P&L in rupees; screener shows crores (typically < 1e4 per quarter).
    if max(nums) >= 1e5:
        return 1e7
    return 1.0


def _values_from_series(series: pd.Series, index: pd.Index, *, decimals: int) -> list[float | None]:
    aligned = series.reindex(index)
    raw: list[float | None] = []
    for val in aligned:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            raw.append(None)
        else:
            raw.append(float(val))

    if decimals == 2:
        return [round(v, 2) if v is not None else None for v in raw]

    divisor = _inr_crore_divisor([v for v in raw if v is not None])
    return [round(v / divisor) if v is not None else None for v in raw]


def build_quarter_panel(
    revenue: pd.Series,
    ebit: pd.Series,
    net_profit: pd.Series,
    eps: pd.Series,
    *,
    max_quarters: int = PEAD2_QUARTER_PANEL,
) -> dict | None:
    """Build screener-style quarterly rows for the PEAD expand panel."""
    rev = revenue.dropna().sort_index().astype(float)
    if len(rev) < 2:
        return None

    rev = rev.iloc[-max_quarters:]
    index = rev.index
    labels = [_quarter_label(pd.Timestamp(d)) for d in index]

    rows: list[dict] = [
        {
            "label": "Sales",
            "values": _values_from_series(rev, index, decimals=0),
            "good_up": True,
            "decimals": 0,
        },
        {
            "label": "Operating Profit",
            "values": _values_from_series(ebit, index, decimals=0),
            "good_up": True,
            "decimals": 0,
        },
        {
            "label": "Net Profit",
            "values": _values_from_series(net_profit, index, decimals=0),
            "good_up": True,
            "decimals": 0,
        },
        {
            "label": "EPS in Rs",
            "values": _values_from_series(eps, index, decimals=2),
            "good_up": True,
            "decimals": 2,
        },
    ]

    return {"labels": labels, "rows": rows}


def append_valuation_rows(
    panel: dict | None,
    price: float | None,
) -> dict | None:
    """
    Add Forward EPS, Current PE (TTM), and Forward PE rows per quarter column.

    Uses the same Option A / B logic as the main PEAD table (current price vs each
    quarter's EPS path).
    """
    if not panel or price is None or price <= 0:
        return panel

    eps_row = next(
        (row for row in panel.get("rows") or [] if row.get("label") == "EPS in Rs"),
        None,
    )
    if not eps_row:
        return panel

    eps_values: list = eps_row.get("values") or []
    n = len(eps_values)
    forward_eps_vals: list[float | None] = []
    forward_pe_vals: list[float | None] = []
    current_pe_vals: list[float | None] = []

    for i in range(n):
        eq = eps_values[i]
        if eq is None:
            forward_eps_vals.append(None)
            forward_pe_vals.append(None)
            current_pe_vals.append(None)
            continue

        eq_f = float(eq)
        fwd_eps = round(eq_f * 4.0, 2)
        forward_eps_vals.append(fwd_eps)
        forward_pe_vals.append(round(price / fwd_eps, 1) if fwd_eps != 0 else None)

        start = max(0, i - 3)
        ttm_parts = [float(v) for v in eps_values[start : i + 1] if v is not None]
        if not ttm_parts:
            current_pe_vals.append(None)
            continue
        ttm = sum(ttm_parts)
        current_pe_vals.append(round(price / ttm, 1) if ttm != 0 else None)

    panel = dict(panel)
    panel["rows"] = list(panel.get("rows") or [])
    panel["rows"].extend(
        [
            {
                "label": "Forward EPS",
                "values": forward_eps_vals,
                "good_up": True,
                "decimals": 2,
            },
            {
                "label": "Current PE",
                "values": current_pe_vals,
                "good_up": False,
                "decimals": 1,
            },
            {
                "label": "Forward PE",
                "values": forward_pe_vals,
                "good_up": False,
                "decimals": 1,
            },
        ]
    )
    return panel


def is_sales_bust(
    revenue: pd.Series,
    sales_qoq: float | None,
    *,
    min_streak: int = 2,
    min_qoq_pct: float = 25.0,
) -> tuple[bool, int]:
    """
  Sales bust = consecutive rising sales quarters and/or a large latest QoQ jump.
  Returns (flag, sales_streak).
    """
    rev = revenue.dropna().sort_index().astype(float)
    streak = streak_up(rev) if len(rev) >= 2 else 0
    qoq = float(sales_qoq) if sales_qoq is not None and not pd.isna(sales_qoq) else None
    if streak >= min_streak:
        return True, streak
    if qoq is not None and qoq >= min_qoq_pct:
        return True, streak
    return False, streak
