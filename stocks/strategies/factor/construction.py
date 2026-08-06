"""
Factor construction pipeline (Chen-style).

Raw OHLCV → momentum / Fama-style / sector factors → cross-sectional
winsorize + z-score → composite → IC validation → latest snapshot for UI.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from stocks.core.text_utils import safe_str

DEFAULT_FORWARD_DAYS = 5
DEFAULT_LOOKBACK = "3y"

# Composite weights — negative vol (low-vol anomaly).
WEIGHTS = {
    "mom_21_z": 0.35,
    "value_proxy_z": 0.25,
    "vol_factor_z": -0.20,
    "sector_rel_mom_z": 0.20,
}

FACTOR_RAW_COLS = ["mom_21", "value_proxy", "vol_factor", "sector_rel_mom"]


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Flatten MultiIndex columns (yfinance download shape) to simple names."""
    if not isinstance(df.columns, pd.MultiIndex):
        return df
    out = df.copy()
    out.columns = [
        str(c[0]).strip() if isinstance(c, tuple) and len(c) else str(c)
        for c in out.columns
    ]
    return out


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame | None:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    work = _flatten_columns(df)
    # Keep a clean DatetimeIndex for reset_index → date.
    if not isinstance(work.index, pd.DatetimeIndex):
        for cand in ("Date", "date", "Datetime", "datetime"):
            if cand in work.columns:
                work = work.set_index(pd.to_datetime(work[cand], errors="coerce"))
                work = work.drop(columns=[cand], errors="ignore")
                break
    rename = {c: str(c).strip().lower() for c in work.columns}
    work = work.rename(columns=rename)
    # Drop duplicate lowercase names (keep first).
    work = work.loc[:, ~work.columns.duplicated()]
    need = {"open", "high", "low", "close", "volume"}
    if not need.issubset(set(work.columns)):
        return None
    vol = pd.to_numeric(work["volume"], errors="coerce")
    close = pd.to_numeric(work["close"], errors="coerce")
    work = work.assign(volume=vol, close=close)
    work = work.loc[vol.fillna(0) > 0].dropna(subset=["close"])
    if len(work) < 100:
        return None
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in work.columns]
    return work[keep].copy()


def add_momentum_factors(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    out["mom_21"] = close / close.shift(21) - 1
    out["mom_63"] = close / close.shift(63) - 1
    out["mom_126"] = close / close.shift(126) - 1
    out["lag_ret_5"] = close.shift(5) / close.shift(6) - 1
    return out


def add_fama_style_factors(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce")
    daily_ret = close.pct_change()
    out["size_proxy"] = (close * volume).rolling(252).mean()
    out["value_proxy"] = close / close.rolling(252).min() - 1
    out["vol_factor"] = daily_ret.rolling(21).std() * np.sqrt(252)
    return out


def build_panel(
    data: dict[str, pd.DataFrame],
    *,
    sectors: dict[str, str] | None = None,
) -> pd.DataFrame:
    """
    ``data`` maps ticker → OHLCV frame (Close/Volume or close/volume).
    ``sectors`` optional ticker → sector label for sector-relative momentum.
    """
    frames: list[pd.DataFrame] = []
    sector_map = {
        safe_str(k).upper(): (safe_str(v) or "Unknown") for k, v in (sectors or {}).items()
    }

    for ticker, raw in data.items():
        key = safe_str(ticker).upper()
        if not isinstance(raw, pd.DataFrame):
            continue
        df = _normalize_ohlcv(raw)
        if df is None:
            continue
        df = add_momentum_factors(df)
        df = add_fama_style_factors(df)
        # Match Chen script: reset index → date column.
        frame = df.reset_index()
        rename_date = {}
        for c in frame.columns:
            cl = str(c).strip().lower()
            if cl in {"date", "datetime", "index"} or c in ("Date", "Datetime"):
                rename_date[c] = "date"
                break
        if rename_date:
            frame = frame.rename(columns=rename_date)
        elif "date" not in frame.columns:
            # First column after reset_index is the former index.
            first = frame.columns[0]
            frame = frame.rename(columns={first: "date"})
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        # Strip tz without shifting calendar day when possible.
        try:
            if getattr(frame["date"].dt, "tz", None) is not None:
                frame["date"] = frame["date"].dt.tz_localize(None)
        except (TypeError, AttributeError, ValueError):
            frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.tz_localize(
                None
            )
        frame["ticker"] = key
        frame["sector"] = sector_map.get(key) or "Unknown"
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    panel = pd.concat(frames, ignore_index=True, sort=False)
    if panel.columns.duplicated().any():
        panel = panel.loc[:, ~panel.columns.duplicated()].copy()
    panel = panel.dropna(subset=["date", "close"])
    panel["sector_mean_mom"] = panel.groupby(["date", "sector"], sort=False)[
        "mom_21"
    ].transform("mean")
    panel["sector_rel_mom"] = panel["mom_21"] - panel["sector_mean_mom"]
    return panel


def winsorize_array(vals: np.ndarray, n_std: float = 3.0) -> np.ndarray:
    """Winsorize a 1-d float array; always returns ndarray (groupby.transform-safe)."""
    x = np.asarray(vals, dtype=float)
    finite = np.isfinite(x)
    if finite.sum() < 2:
        return x
    m = float(np.nanmean(x))
    sd = float(np.nanstd(x, ddof=1))
    if not np.isfinite(sd) or sd == 0:
        return x
    return np.clip(x, m - n_std * sd, m + n_std * sd)


def zscore_array(vals: np.ndarray) -> np.ndarray:
    """Cross-section z-score; returns ndarray same length as input."""
    x = np.asarray(vals, dtype=float)
    finite = np.isfinite(x)
    if finite.sum() < 2:
        return np.zeros(len(x), dtype=float)
    m = float(np.nanmean(x))
    sd = float(np.nanstd(x, ddof=1))
    if not np.isfinite(sd) or sd == 0:
        return np.zeros(len(x), dtype=float)
    out = (x - m) / sd
    out[~finite] = 0.0
    return out


def winsorize(s: pd.Series, n_std: float = 3.0) -> pd.Series:
    """Series wrapper kept for tests / call sites that expect a Series."""
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    arr = winsorize_array(pd.to_numeric(s, errors="coerce").to_numpy(), n_std=n_std)
    return pd.Series(arr, index=s.index)


def cross_sectional_zscore(panel: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = panel.copy()
    # Duplicate names make groupby[col] return a DataFrame and break transform.
    if out.columns.duplicated().any():
        out = out.loc[:, ~out.columns.duplicated()].copy()
    for col in cols:
        if col not in out.columns:
            continue
        raw = pd.to_numeric(out[col], errors="coerce")
        if isinstance(raw, pd.DataFrame):
            raw = raw.iloc[:, 0]
        out[col] = raw
        # Return ndarrays from transform — avoids pandas concat(Series) bug
        # ('Series' object has no attribute 'columns') on some group shapes.
        out[col] = out.groupby("date", sort=False)[col].transform(
            lambda x: winsorize_array(x.to_numpy(dtype=float, copy=False))
        )
        out[f"{col}_z"] = out.groupby("date", sort=False)[col].transform(
            lambda x: zscore_array(x.to_numpy(dtype=float, copy=False))
        )
    return out


def composite_score(
    panel: pd.DataFrame,
    *,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    out = panel.copy()
    wmap = weights or WEIGHTS
    score = pd.Series(0.0, index=out.index, dtype=float)
    for col, w in wmap.items():
        if col not in out.columns:
            continue
        vals = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
        score = score + vals * float(w)
    out["composite"] = score
    return out


def add_forward_return(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    out = panel.sort_values(["ticker", "date"]).copy()
    out["fwd_ret"] = out.groupby("ticker", sort=False)["close"].transform(
        lambda s: s.shift(-int(horizon)) / s - 1
    )
    return out


def validate_panel(panel: pd.DataFrame) -> dict[str, Any]:
    empty_stats = {
        "train_mean_ic": None,
        "train_icir": None,
        "test_mean_ic": None,
        "test_icir": None,
        "random_baseline_ic": None,
        "n_train_periods": 0,
        "n_test_periods": 0,
    }
    if panel is None or not isinstance(panel, pd.DataFrame) or panel.empty:
        return empty_stats
    if "composite" not in panel.columns or "fwd_ret" not in panel.columns:
        return empty_stats

    work = panel.dropna(subset=["composite", "fwd_ret"])
    if work.empty:
        return empty_stats

    dates = sorted(work["date"].unique())
    split_idx = max(1, int(len(dates) * 0.7))
    train_dates, test_dates = set(dates[:split_idx]), set(dates[split_idx:])

    def compute_ics(sub: pd.DataFrame) -> np.ndarray:
        ics: list[float] = []
        for _date, g in sub.groupby("date"):
            if len(g) < 5:
                continue
            if g["composite"].nunique(dropna=True) < 2:
                continue
            ic, _ = spearmanr(g["composite"], g["fwd_ret"])
            if ic is not None and not np.isnan(ic):
                ics.append(float(ic))
        return np.array(ics, dtype=float)

    train_ics = compute_ics(work[work["date"].isin(train_dates)])
    test_ics = compute_ics(work[work["date"].isin(test_dates)])

    rand_ics: list[float] = []
    rng = np.random.default_rng(42)
    for _date, g in work[work["date"].isin(test_dates)].groupby("date"):
        if len(g) < 5:
            continue
        shuffled = rng.permutation(g["fwd_ret"].to_numpy())
        if g["composite"].nunique(dropna=True) < 2:
            continue
        ic, _ = spearmanr(g["composite"], shuffled)
        if ic is not None and not np.isnan(ic):
            rand_ics.append(float(ic))

    def _mean(a: np.ndarray) -> float | None:
        return float(a.mean()) if len(a) else None

    def _icir(a: np.ndarray) -> float | None:
        if len(a) < 2 or float(a.std()) <= 0:
            return None
        return float(a.mean() / a.std())

    return {
        "train_mean_ic": _mean(train_ics),
        "train_icir": _icir(train_ics),
        "test_mean_ic": _mean(test_ics),
        "test_icir": _icir(test_ics),
        "random_baseline_ic": float(np.mean(rand_ics)) if rand_ics else None,
        "n_train_periods": int(len(train_ics)),
        "n_test_periods": int(len(test_ics)),
    }


def latest_cross_section(panel: pd.DataFrame) -> pd.DataFrame:
    """One row per ticker on the most recent bar with a composite."""
    if (
        panel is None
        or not isinstance(panel, pd.DataFrame)
        or panel.empty
        or "composite" not in panel.columns
    ):
        return pd.DataFrame()
    work = panel.dropna(subset=["composite", "date"]).copy()
    if work.empty:
        return pd.DataFrame()
    work = work.sort_values(["ticker", "date"])
    latest = work.groupby("ticker", sort=False).tail(1).reset_index(drop=True)
    latest = latest.sort_values("composite", ascending=False, kind="mergesort")
    latest.insert(0, "factor_rank", range(1, len(latest) + 1))
    return latest


def run_factor_pipeline(
    data: dict[str, pd.DataFrame],
    *,
    sectors: dict[str, str] | None = None,
    forward_days: int = DEFAULT_FORWARD_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """
    Full pipeline. Returns ``(latest_snapshot, full_panel, validation_stats)``.
    """
    clean = {
        safe_str(t).upper(): df
        for t, df in (data or {}).items()
        if safe_str(t) and isinstance(df, pd.DataFrame) and not df.empty
    }
    panel = build_panel(clean, sectors=sectors)
    if panel.empty:
        return pd.DataFrame(), panel, validate_panel(panel)

    panel = cross_sectional_zscore(panel, FACTOR_RAW_COLS)
    panel = composite_score(panel)
    panel = add_forward_return(panel, forward_days)
    stats = validate_panel(panel)
    latest = latest_cross_section(panel)
    return latest, panel, stats
