"""Shared OHLCV normalization helpers for strategy indicators."""

from __future__ import annotations

import pandas as pd


def normalize_price_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out.index))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    out.index = idx.normalize()
    return out


def flatten_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    return out


def drop_incomplete_month(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the forming monthly bar so RSI uses last completed month only."""
    if df is None or len(df) < 2:
        return df
    last_ts = pd.Timestamp(df.index[-1])
    now = pd.Timestamp.now(tz=last_ts.tz) if last_ts.tzinfo else pd.Timestamp.now()
    if last_ts.year == now.year and last_ts.month == now.month:
        return df.iloc[:-1].copy()
    return df


def prepare_weekly_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = flatten_ohlcv_columns(normalize_price_index(df))
    weeks = out.index.to_period("W-MON")
    out = out.groupby(weeks, group_keys=False).last()
    out.index = out.index.to_timestamp(how="end")
    return out


def prepare_daily_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize daily OHLCV; drop today's incomplete bar when present."""
    if df is None or df.empty:
        return df
    out = flatten_ohlcv_columns(normalize_price_index(df))
    if len(out) < 2:
        return out
    last_ts = pd.Timestamp(out.index[-1])
    now = pd.Timestamp.now(tz=last_ts.tz) if last_ts.tzinfo else pd.Timestamp.now()
    if last_ts.normalize() == now.normalize():
        return out.iloc[:-1].copy()
    return out
