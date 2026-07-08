"""Technical indicators for TQ and Bollinger Bands strategies."""

from __future__ import annotations

import time

import pandas as pd
import yfinance as yf

from stocks.market.indicators_utils import flatten_ohlcv_columns, normalize_price_index, prepare_weekly_ohlcv

_NIFTY_CACHE: tuple[float, pd.DataFrame] | None = None
_NIFTY500_CACHE: tuple[float, pd.DataFrame, str] | None = None
_NIFTY_CACHE_SECONDS = 3600


def calculate_bollinger_bands(data, period=50, width=2):
    sma = data["Close"].rolling(window=period).mean()
    std = data["Close"].rolling(window=period).std()
    upper_band = sma + (width * std)
    lower_band = sma - (width * std)
    return upper_band, sma, lower_band


def calculate_rsi(data, period=21):
    delta = data["Close"].diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.rolling(window=period, min_periods=period).mean()
    avg_loss = losses.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_atr(data, period=10):
    high = data["High"]
    low = data["Low"]
    close = data["Close"]
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calculate_supertrend(data, atr_period=10, factor=3):
    atr = calculate_atr(data, atr_period)
    hl2 = (data["High"] + data["Low"]) / 2
    basic_upper = hl2 + (factor * atr)
    basic_lower = hl2 - (factor * atr)
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    for i in range(1, len(data)):
        if (
            pd.isna(final_upper.iloc[i - 1])
            or basic_upper.iloc[i] < final_upper.iloc[i - 1]
            or data["Close"].iloc[i - 1] > final_upper.iloc[i - 1]
        ):
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]
        if (
            pd.isna(final_lower.iloc[i - 1])
            or basic_lower.iloc[i] > final_lower.iloc[i - 1]
            or data["Close"].iloc[i - 1] < final_lower.iloc[i - 1]
        ):
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]
    supertrend = pd.Series(index=data.index, dtype=float)
    direction = pd.Series(index=data.index, dtype=int)
    supertrend.iloc[0] = final_upper.iloc[0]
    direction.iloc[0] = -1
    for i in range(1, len(data)):
        if data["Close"].iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif data["Close"].iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
        if direction.iloc[i] == 1:
            supertrend.iloc[i] = final_lower.iloc[i]
        else:
            supertrend.iloc[i] = final_upper.iloc[i]
    return supertrend, direction


def calculate_adx(data, period=13):
    high = data["High"]
    low = data["Low"]
    close = data["Close"]
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    dm_plus = high - high.shift(1)
    dm_minus = low.shift(1) - low
    dm_plus = dm_plus.where((dm_plus > dm_minus) & (dm_plus > 0), 0)
    dm_minus = dm_minus.where((dm_minus > dm_plus) & (dm_minus > 0), 0)
    tr_smooth = tr.rolling(window=period).sum()
    dm_plus_smooth = dm_plus.rolling(window=period).sum()
    dm_minus_smooth = dm_minus.rolling(window=period).sum()
    di_plus = 100 * (dm_plus_smooth / tr_smooth)
    di_minus = 100 * (dm_minus_smooth / tr_smooth)
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
    adx = dx.rolling(window=period).mean()
    return adx, di_plus, di_minus


def calculate_relative_strength(stock_data, nifty_data, period):
    stock_price = stock_data["Close"]
    nifty_price = nifty_data["Close"]
    price_ratio = stock_price / nifty_price
    price_ratio_period_ago = price_ratio.shift(period)
    relative_strength = pd.Series(index=price_ratio.index, dtype=float)
    for i in range(len(price_ratio)):
        if (
            i >= period
            and not pd.isna(price_ratio.iloc[i])
            and not pd.isna(price_ratio_period_ago.iloc[i])
        ):
            if price_ratio_period_ago.iloc[i] != 0:
                relative_strength.iloc[i] = (
                    price_ratio.iloc[i] / price_ratio_period_ago.iloc[i]
                ) - 1
            else:
                relative_strength.iloc[i] = 0
        else:
            relative_strength.iloc[i] = pd.NA
    return relative_strength


def align_weekly_with_nifty(stock_df: pd.DataFrame, nifty_df: pd.DataFrame, min_weeks: int = 65):
    stock = prepare_weekly_ohlcv(stock_df)
    nifty = prepare_weekly_ohlcv(nifty_df)
    common_dates = stock.index.intersection(nifty.index)
    if len(common_dates) < min_weeks:
        return None, None
    return stock.loc[common_dates], nifty.loc[common_dates]


def get_nifty_data() -> pd.DataFrame:
    global _NIFTY_CACHE
    now = time.time()
    if _NIFTY_CACHE and now - _NIFTY_CACHE[0] < _NIFTY_CACHE_SECONDS:
        return _NIFTY_CACHE[1].copy()

    periods = ["2y", "1y", "6mo"]
    for attempt in range(3):
        for period in periods:
            try:
                df = yf.Ticker("^NSEI").history(period=period, interval="1wk")
                if isinstance(df, pd.DataFrame) and not df.empty:
                    prepared = prepare_weekly_ohlcv(df)
                    _NIFTY_CACHE = (time.time(), prepared)
                    return prepared.copy()
            except Exception:
                pass
            try:
                df = yf.download(
                    tickers="^NSEI",
                    period=period,
                    interval="1wk",
                    progress=False,
                    auto_adjust=True,
                )
                if isinstance(df, pd.DataFrame) and not df.empty:
                    prepared = prepare_weekly_ohlcv(flatten_ohlcv_columns(df))
                    _NIFTY_CACHE = (time.time(), prepared)
                    return prepared.copy()
            except Exception:
                pass
        time.sleep(1 + attempt)
    return pd.DataFrame()


def _fetch_index_weekly(symbols: list[str], period: str = "max") -> pd.DataFrame:
    for symbol in symbols:
        for attempt in range(2):
            try:
                df = yf.Ticker(symbol).history(period=period, interval="1wk", auto_adjust=True)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return prepare_weekly_ohlcv(df)
            except Exception:
                pass
            try:
                df = yf.download(
                    tickers=symbol,
                    period=period,
                    interval="1wk",
                    progress=False,
                    auto_adjust=True,
                )
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return prepare_weekly_ohlcv(flatten_ohlcv_columns(df))
            except Exception:
                pass
            time.sleep(0.5 + attempt)
    return pd.DataFrame()


def get_nifty500_data() -> tuple[pd.DataFrame, str]:
    """NIFTY 500 weekly series for Turtle relative-strength benchmark."""
    global _NIFTY500_CACHE
    now = time.time()
    if _NIFTY500_CACHE and now - _NIFTY500_CACHE[0] < _NIFTY_CACHE_SECONDS:
        return _NIFTY500_CACHE[1].copy(), _NIFTY500_CACHE[2]

    for symbol, label in (
        ("^CRSLDX", "NIFTY 500 (^CRSLDX)"),
        ("MONIFTY500.NS", "NIFTY 500 ETF"),
        ("^NSEI", "NIFTY 50 proxy"),
    ):
        prepared = _fetch_index_weekly([symbol], period="max")
        if not prepared.empty:
            _NIFTY500_CACHE = (time.time(), prepared, label)
            return prepared.copy(), label
    return pd.DataFrame(), "NIFTY 500"
