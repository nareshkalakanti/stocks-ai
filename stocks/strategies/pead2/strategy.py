"""PEAD 2 — scored candidates dashboard (growth · forward PE · post-result returns)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from stocks.strategies.earnings.strategy import EPS_FIELDS, OP_FIELDS, REVENUE_FIELDS, _sorted_series


NET_INCOME_FIELDS = (
    "Net Income",
    "Net Income Common Stockholders",
    "Net Income From Continuing Operation Net Minority Interest",
)

CFO_FIELDS = (
    "Operating Cash Flow",
    "Cash Flow From Continuing Operating Activities",
)


PEAD_HIGH_SCORE_MIN = 40.0

_GROWTH_QOQ_COLUMNS = ("sales_qoq", "np_qoq", "eps_qoq", "ebidt_qoq")

# Column order aligned with pead_results SQL export (stock_symbol … calculation_date).
PEAD_EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("ticker", "stock_symbol"),
    ("name", "stock_name"),
    ("market_cap_cr", "market_cap"),
    ("price", "last_price"),
    ("pe_ratio", "pe_ratio"),
    ("pead_score", "pead_score"),
    ("comfortable_buy_price", "comfort_buy_price"),
    ("sector", "sector"),
    ("sales_yoy", "sales_growth_yoy"),
    ("np_yoy", "net_profit_growth_yoy"),
    ("eps_yoy", "eps_growth_yoy"),
    ("calculation_date", "calculation_date"),
]


def pead_category(score: float | None, *, high_min: float = PEAD_HIGH_SCORE_MIN) -> str:
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return ""
    return "HIGH" if float(score) > high_min else ""


def eps_yoy_from_quarters(quarters: dict | None) -> float | None:
    """YoY EPS % from expand-panel quarter rows when yfinance metric is missing."""
    from stocks.strategies.pead2.quarters import yoy_pair_from_panel

    if not isinstance(quarters, dict):
        return None
    labels = quarters.get("labels") or []
    for row in quarters.get("rows") or []:
        label = str(row.get("label") or "").lower()
        if "eps" not in label:
            continue
        values = row.get("values") or []
        latest_f, prior_f = yoy_pair_from_panel(values, labels if labels else None)
        if latest_f is None or prior_f is None or prior_f == 0:
            return None
        return round(((latest_f / prior_f) - 1.0) * 100.0, 2)
    return None


def enrich_pead_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Fill display/export fields (category, PE, EPS YoY, calc date) for dashboard + CSV."""
    if df.empty:
        return df

    from datetime import datetime, timezone

    out = df.copy()
    now = datetime.now(timezone.utc).isoformat()

    if "calculation_date" not in out.columns:
        out["calculation_date"] = now
    else:
        out["calculation_date"] = out["calculation_date"].fillna(now)

    if "forward_pe" in out.columns or "snapshot" in out.columns:

        def _fill_pe(row: pd.Series) -> float | None:
            for key in ("pe_ratio", "forward_pe"):
                val = row.get(key)
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    return round(float(val), 2)
            snap = row.get("snapshot")
            if isinstance(snap, dict):
                snap_pe = snap.get("pe")
                if snap_pe is not None and not (
                    isinstance(snap_pe, float) and pd.isna(snap_pe)
                ):
                    return round(float(snap_pe), 2)
            return None

        out["pe_ratio"] = out.apply(_fill_pe, axis=1)

    if "eps_yoy" not in out.columns:
        out["eps_yoy"] = np.nan

    def _fill_eps(row: pd.Series) -> float | None:
        val = row.get("eps_yoy")
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            return round(float(val), 2)
        from_q = eps_yoy_from_quarters(row.get("quarters"))
        return from_q

    out["eps_yoy"] = out.apply(_fill_eps, axis=1)

    return out


def attach_strategy_breakout_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Merge latest TQ / BB rows from SQLite (Strategy scan cache)."""
    if df is None or df.empty or "ticker" not in df.columns:
        return df

    from stocks.core.database import load_strategy_breakout_map

    out = df.copy()
    for col, default in (
        ("has_tq", False),
        ("has_bb", False),
        ("tq_score", pd.NA),
        ("tq_crossover", ""),
        ("bb_signal", ""),
        ("bb_timeframe", ""),
    ):
        if col not in out.columns:
            out[col] = default

    tickers = out["ticker"].astype(str).str.strip().str.upper().unique().tolist()
    bmap = load_strategy_breakout_map(tickers)
    if not bmap:
        return out

    for idx, row in out.iterrows():
        ticker = str(row.get("ticker") or "").strip().upper()
        rec = bmap.get(ticker)
        if not rec:
            continue
        tq = rec.get("tq")
        if tq:
            out.at[idx, "has_tq"] = True
            if tq.get("score") is not None:
                out.at[idx, "tq_score"] = float(tq["score"])
            out.at[idx, "tq_crossover"] = str(tq.get("crossover_type") or "")
        bb = rec.get("bb")
        if bb:
            out.at[idx, "has_bb"] = True
            out.at[idx, "bb_signal"] = str(bb.get("signal") or "ABOVE_BAND")
            out.at[idx, "bb_timeframe"] = str(bb.get("timeframe") or "")

    return out


def format_pead_export_df(df: pd.DataFrame) -> pd.DataFrame:
    """PEAD rows with SQL-matching column names and order."""
    aliases = [alias for _, alias in PEAD_EXPORT_COLUMNS]
    if df.empty:
        return pd.DataFrame(columns=aliases)
    work = enrich_pead_candidates(df)
    out: dict[str, pd.Series] = {}
    for src, alias in PEAD_EXPORT_COLUMNS:
        out[alias] = work[src] if src in work.columns else pd.NA
    return pd.DataFrame(out)[aliases]


@dataclass(frozen=True)
class Pead2AbsoluteWeights:
    """FinanciallyFree-style absolute weights (sum = 0.90)."""
    sales_yoy: float = 0.15
    np_yoy: float = 0.20
    sales_qoq: float = 0.10
    np_qoq: float = 0.15
    ebidt_yoy: float = 0.10
    ebidt_qoq: float = 0.05
    forward_pe: float = 0.15

    @property
    def total(self) -> float:
        return (
            self.sales_yoy
            + self.np_yoy
            + self.sales_qoq
            + self.np_qoq
            + self.ebidt_yoy
            + self.ebidt_qoq
            + self.forward_pe
        )


@dataclass(frozen=True)
class Pead2AbsoluteParams:
    growth_cap: float = 100.0
    pe_ideal: float = 15.0
    pe_bad: float = 50.0


@dataclass(frozen=True)
class Pead2ScoreWeights:
    """Universe percentile ranks (FinanciallyFree PEAD dashboard)."""

    returns: float = 14.0
    sales_yoy: float = 12.0
    sales_qoq: float = 11.0
    np_yoy: float = 13.0
    np_qoq: float = 15.0
    eps_yoy: float = 8.0
    eps_qoq: float = 8.0
    ebidt_yoy: float = 8.0
    ebidt_qoq: float = 6.0
    forward_pe: float = 8.0
    cf_profit: float = 2.0

    @property
    def total(self) -> float:
        return (
            self.returns
            + self.sales_yoy
            + self.sales_qoq
            + self.np_yoy
            + self.np_qoq
            + self.eps_yoy
            + self.eps_qoq
            + self.ebidt_yoy
            + self.ebidt_qoq
            + self.forward_pe
            + self.cf_profit
        )

    def metric_specs(self) -> list[tuple[str, float, bool]]:
        """(column, weight, invert_percentile)."""
        return [
            ("returns_pct", self.returns, False),
            ("sales_yoy", self.sales_yoy, False),
            ("sales_qoq", self.sales_qoq, False),
            ("np_yoy", self.np_yoy, False),
            ("np_qoq", self.np_qoq, False),
            ("eps_yoy", self.eps_yoy, False),
            ("eps_qoq", self.eps_qoq, False),
            ("ebidt_yoy", self.ebidt_yoy, False),
            ("ebidt_qoq", self.ebidt_qoq, False),
            ("forward_pe", self.forward_pe, True),
            ("cf_profit", self.cf_profit, False),
        ]


def _series(income: pd.DataFrame, fields: tuple[str, ...]) -> pd.Series | None:
    return _sorted_series(income, fields)


def _pct_change(series: pd.Series, lag: int) -> float | None:
    s = series.dropna().sort_index().astype(float)
    if len(s) <= lag:
        return None
    prev = float(s.iloc[-1 - lag])
    latest = float(s.iloc[-1])
    if prev == 0:
        return None
    return ((latest / prev) - 1.0) * 100.0


def compute_growth_metrics(
    revenue: pd.Series,
    net_profit: pd.Series,
    ebidt: pd.Series,
    eps: pd.Series | None = None,
) -> dict:
    metrics = {
        "sales_yoy": _pct_change(revenue, 4),
        "sales_qoq": _pct_change(revenue, 1),
        "np_yoy": _pct_change(net_profit, 4),
        "np_qoq": _pct_change(net_profit, 1),
        "ebidt_yoy": _pct_change(ebidt, 4),
        "ebidt_qoq": _pct_change(ebidt, 1),
    }
    if eps is not None:
        metrics["eps_yoy"] = _pct_change(eps, 4)
        metrics["eps_qoq"] = _pct_change(eps, 1)
    return metrics


def compute_cf_profit(cfo: pd.Series | None, net_profit: pd.Series) -> float | None:
    if cfo is None:
        return None
    c = cfo.dropna().sort_index().astype(float)
    n = net_profit.dropna().sort_index().astype(float)
    if c.empty or n.empty:
        return None
    ni = float(n.iloc[-1])
    if ni == 0:
        return None
    return round(float(c.iloc[-1]) / ni, 2)


def compute_trailing_pe(
    price: float | None,
    eps: pd.Series,
    info: dict | None = None,
) -> float | None:
    """Option A: price ÷ sum of last 4 quarters' EPS (TTM)."""
    if price is None or price <= 0:
        return None
    if info:
        pe = info.get("trailingPE")
        if pe is not None and not (isinstance(pe, float) and pd.isna(pe)):
            return round(float(pe), 1)
    s = eps.dropna().sort_index().astype(float)
    if s.empty:
        return None
    ttm = float(s.iloc[-4:].sum()) if len(s) >= 4 else float(s.sum())
    if ttm == 0:
        return None
    return round(price / ttm, 1)


def compute_forward_pe(
    price: float | None,
    eps: pd.Series,
    info: dict | None = None,
) -> float | None:
    """Option B: price ÷ (latest quarter EPS × 4), or yfinance forward EPS."""
    if price is None or price <= 0:
        return None
    info = info or {}
    fwd = info.get("forwardPE")
    if fwd is not None and not (isinstance(fwd, float) and pd.isna(fwd)):
        return round(float(fwd), 1)
    fwd_eps = info.get("forwardEps")
    if fwd_eps is not None and not (isinstance(fwd_eps, float) and pd.isna(fwd_eps)):
        fe = float(fwd_eps)
        if fe == 0:
            return None
        return round(price / fe, 1)
    s = eps.dropna().sort_index().astype(float)
    if s.empty:
        return None
    run_rate = float(s.iloc[-1]) * 4.0
    if run_rate == 0:
        return None
    return round(price / run_rate, 1)


def series_through_lag(series: pd.Series, lag: int = 0) -> pd.Series | None:
    """Drop the latest ``lag`` quarters; lag=0 keeps the full series."""
    s = series.dropna().sort_index().astype(float)
    if lag < 0 or lag >= len(s):
        return None
    if lag == 0:
        return s
    return s.iloc[:-lag]


def trading_days_after_result(hist: pd.DataFrame, result_date: pd.Timestamp) -> int:
    """Trading days from first close on/after result date through latest close."""
    if hist is None or hist.empty:
        return 0
    px = hist.sort_index().copy()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    entry_ts = pd.Timestamp(result_date).tz_localize(None).normalize()
    after = px[px.index > entry_ts]
    if after.empty:
        after = px[px.index >= entry_ts]
    if after.empty:
        return 0
    return max(1, len(after))


def compute_daily_ret_pct(
    returns_pct: float | None,
    hist: pd.DataFrame,
    result_date: pd.Timestamp,
) -> float | None:
    if returns_pct is None:
        return None
    days = trading_days_after_result(hist, result_date)
    if days <= 0:
        return 0.0
    return round(float(returns_pct) / days, 3)


def compute_returns_pct(
    hist: pd.DataFrame,
    result_date: pd.Timestamp,
    *,
    drift_days: int = 0,
) -> float | None:
    """
    Post-earnings return from the first trading close after ``result_date``.

    ``drift_days=0``: through the latest available close (open-ended drift).
    ``drift_days>0``: through the N-th trading day after entry when enough
    history exists; otherwise through the latest close (recent results).
    """
    if hist is None or hist.empty:
        return None
    px = hist.sort_index().copy()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    entry_ts = pd.Timestamp(result_date).tz_localize(None).normalize()
    after = px[px.index > entry_ts]
    if after.empty:
        after = px[px.index >= entry_ts]
    if after.empty:
        return None
    entry = float(after.iloc[0]["Close"])
    if entry <= 0:
        return None
    if drift_days > 0 and len(after) >= drift_days:
        exit_price = float(after.iloc[drift_days - 1]["Close"])
    else:
        exit_price = float(after.iloc[-1]["Close"])
    return round((exit_price / entry - 1.0) * 100.0, 2)


def _clamp_score(x: float, *, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _apply_growth_caps(df: pd.DataFrame) -> pd.DataFrame:
    """Cap extreme QoQ metrics on cached rows before percentile scoring."""
    from stocks.strategies.earnings.quality import cap_growth_qoq_pct

    if df.empty:
        return df
    out = df.copy()
    for col in _GROWTH_QOQ_COLUMNS:
        if col not in out.columns:
            continue
        out[col] = out[col].apply(cap_growth_qoq_pct)
    return out


def _absolute_growth_score(val: float | None, *, cap: float) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return _clamp_score(float(val) / cap * 100.0)


def _absolute_pe_score(
    pe: float | None,
    *,
    ideal: float,
    bad: float,
) -> float | None:
    if pe is None or (isinstance(pe, float) and pd.isna(pe)) or float(pe) <= 0:
        return None
    return _clamp_score(100.0 - (float(pe) - ideal) / (bad - ideal) * 100.0)


def _percentile_score(series: pd.Series, *, invert: bool = False) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() < 2:
        return pd.Series(50.0, index=series.index)
    ranked = s.rank(pct=True, method="average") * 100.0
    if invert:
        ranked = 100.0 - ranked
    return ranked


def _score_weighted_percentile(
    df: pd.DataFrame,
    *,
    weights: Pead2ScoreWeights,
) -> tuple[pd.Series, pd.DataFrame]:
    """Weighted universe percentile composite (0–100) + per-metric percentile columns."""
    composite = pd.Series(0.0, index=df.index)
    row_weights = pd.Series(0.0, index=df.index)
    pct_cols: dict[str, pd.Series] = {}

    for col, weight, invert in weights.metric_specs():
        if weight <= 0 or col not in df.columns:
            continue
        raw = pd.to_numeric(df[col], errors="coerce")
        pct = _percentile_score(raw, invert=invert)
        pct_cols[f"_pct_{col}"] = pct
        has_val = raw.notna()
        composite += pct.where(has_val, 0.0) * weight
        row_weights += has_val.astype(float) * weight

    scaled = composite / row_weights.replace(0, np.nan)
    pct_frame = pd.DataFrame(pct_cols, index=df.index)
    return scaled.clip(upper=100), pct_frame


def pead_score_breakdown(
    df: pd.DataFrame,
    *,
    weights: Pead2ScoreWeights | None = None,
) -> pd.DataFrame:
    """Per-ticker metric contributions that sum to ``pead_score`` (percentile mode)."""
    if df.empty:
        return pd.DataFrame(
            columns=["ticker", "metric", "raw", "percentile", "weight", "contribution"]
        )

    w = weights or Pead2ScoreWeights()
    _composite, pct_frame = _score_weighted_percentile(df, weights=w)
    rows: list[dict] = []

    for idx, row in df.iterrows():
        ticker = row.get("ticker", idx)
        row_weight = 0.0
        parts: list[tuple[str, float, float, float]] = []
        for col, weight, _invert in w.metric_specs():
            if weight <= 0 or col not in df.columns:
                continue
            raw = pd.to_numeric(row.get(col), errors="coerce")
            if pd.isna(raw):
                continue
            pct_col = f"_pct_{col}"
            pct_val = float(pct_frame.at[idx, pct_col]) if pct_col in pct_frame.columns else 50.0
            row_weight += weight
            parts.append((col, float(raw), pct_val, weight))

        if row_weight <= 0:
            continue
        for col, raw, pct_val, weight in parts:
            rows.append(
                {
                    "ticker": ticker,
                    "metric": col,
                    "raw": round(raw, 4),
                    "percentile": round(pct_val, 2),
                    "weight": weight,
                    "contribution": round(pct_val * weight / row_weight, 4),
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["ticker", "contribution"], ascending=[True, False]).reset_index(
        drop=True
    )


def score_pead2_absolute(
    df: pd.DataFrame,
    *,
    weights: Pead2AbsoluteWeights | None = None,
    params: Pead2AbsoluteParams | None = None,
) -> pd.DataFrame:
    """Absolute PEAD score (0–100) from growth % caps + forward PE penalty."""
    if df.empty:
        return df

    w = weights or Pead2AbsoluteWeights()
    p = params or Pead2AbsoluteParams()
    out = _apply_growth_caps(df)
    weight_map: dict[str, tuple[float, str]] = {
        "sales_yoy": (w.sales_yoy, "growth"),
        "sales_qoq": (w.sales_qoq, "growth"),
        "np_yoy": (w.np_yoy, "growth"),
        "np_qoq": (w.np_qoq, "growth"),
        "ebidt_yoy": (w.ebidt_yoy, "growth"),
        "ebidt_qoq": (w.ebidt_qoq, "growth"),
        "forward_pe": (w.forward_pe, "pe"),
    }

    composite = pd.Series(0.0, index=out.index)
    row_weights = pd.Series(0.0, index=out.index)
    for col, (weight, kind) in weight_map.items():
        if weight <= 0 or col not in out.columns:
            continue
        raw = pd.to_numeric(out[col], errors="coerce")
        has_val = raw.notna()
        if kind == "growth":
            sub = raw.apply(lambda v: _absolute_growth_score(v, cap=p.growth_cap))
        else:
            sub = raw.apply(
                lambda v: _absolute_pe_score(v, ideal=p.pe_ideal, bad=p.pe_bad)
            )
        composite += sub.where(has_val, 0.0) * weight
        row_weights += has_val.astype(float) * weight

    full_w = w.total
    scaled = composite * (full_w / row_weights.replace(0, np.nan))
    out["pead_score"] = scaled.clip(upper=100).round(1)

    return out.sort_values("pead_score", ascending=False).reset_index(drop=True)


def score_pead2_percentile(
    df: pd.DataFrame,
    *,
    weights: Pead2ScoreWeights | None = None,
) -> pd.DataFrame:
    """Universe percentile PEAD score (0–100) — returns, growth, forward PE, CF/profit."""
    if df.empty:
        return df

    w = weights or Pead2ScoreWeights()
    out = _apply_growth_caps(df)
    scaled, _pct = _score_weighted_percentile(out, weights=w)
    out["pead_score"] = scaled.round(1)
    return out.sort_values("pead_score", ascending=False).reset_index(drop=True)


def score_pead2_candidates(
    df: pd.DataFrame,
    *,
    weights: Pead2AbsoluteWeights | None = None,
    percentile_weights: Pead2ScoreWeights | None = None,
    params: Pead2AbsoluteParams | None = None,
    mode: str | None = None,
) -> pd.DataFrame:
    """Score PEAD candidates — default ``percentile`` (FF dashboard); or ``absolute``."""
    from stocks.core.config import PEAD2_SCORE_MODE

    resolved = (mode or PEAD2_SCORE_MODE or "percentile").strip().lower()
    if resolved == "absolute":
        return score_pead2_absolute(df, weights=weights, params=params)
    return score_pead2_percentile(df, weights=percentile_weights)
