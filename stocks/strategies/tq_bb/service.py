"""TQ and Bollinger Bands strategy scanners."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed

import pandas as pd
import yfinance as yf

from stocks.core.config import (
    DEFAULT_CAP_TIER,
    STRATEGY_BB_WORKERS_MAX,
    STRATEGY_BB_WORKERS_MIN,
    STRATEGY_FUTURE_TIMEOUT,
    STRATEGY_MAX_WORKERS,
    STRATEGY_MAX_WORKERS_CAP,
    STRATEGY_YFINANCE_TIMEOUT,
)
from stocks.market.fundamentals_service import filter_listings_by_cap_tier
from stocks.scans.results_utils import analysis_universe
from stocks.market.indicators import (
    align_ohlcv_with_nifty,
    calculate_adx,
    calculate_bollinger_bands,
    calculate_relative_strength,
    calculate_rsi,
    calculate_supertrend,
    get_nifty_data,
    get_nifty_data_daily,
)
from stocks.core.log_service import METRICS_ERROR, log_error
from stocks.market.price_service import to_yfinance_symbol
from stocks.shared.links import attach_research_links
from stocks.core.text_utils import safe_str
from stocks.market.yfinance_limits import call_fast

TQ_TIMEFRAMES = ("daily", "weekly")
BB_TIMEFRAMES = ("daily", "weekly", "monthly", "3months")


def strategy_timeframe_options(strategy_choice: str) -> tuple[str, ...]:
    """Shared scan timeframe dropdown options (TQ supports daily/weekly only)."""
    if safe_str(strategy_choice) == "Bollinger Bands":
        return BB_TIMEFRAMES
    return TQ_TIMEFRAMES

BB_INTERVAL_MAP = {
    "daily": ("1y", "1d"),
    "weekly": ("1y", "1wk"),
    "monthly": ("5y", "1mo"),
    "3months": ("max", "3mo"),
}
TQ_INTERVAL_MAP = {
    "weekly": ("2y", "1wk"),
    "daily": ("2y", "1d"),
}
TQ_MIN_BARS = {
    "weekly": 65,
    "daily": 65,
}


def is_skippable_symbol(ticker: str) -> bool:
    sym = safe_str(ticker).upper()
    if not sym or len(sym) < 2:
        return True
    if "-RE" in sym or sym.endswith("-W"):
        return True
    if sym.startswith("0P"):
        return True
    return False


def _fetch_history(
    ticker: str,
    market: str | None,
    *,
    period: str,
    interval: str,
) -> pd.DataFrame | None:
    """Direct yfinance fetch — no global throttle (matches stock-analysis speed)."""
    symbol = to_yfinance_symbol(ticker, market)

    def _fetch():
        df = yf.Ticker(symbol).history(
            period=period,
            interval=interval,
            timeout=STRATEGY_YFINANCE_TIMEOUT,
        )
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
        return None

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Strategy history fetch failed",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    return call_fast(_fetch, on_error=_log)


def analyze_stock_bb(
    ticker: str,
    market: str | None = None,
    timeframe: str = "weekly",
) -> dict | None:
    if is_skippable_symbol(ticker):
        return None

    period, interval = BB_INTERVAL_MAP.get(timeframe, ("1y", "1wk"))
    data = _fetch_history(ticker, market, period=period, interval=interval)
    if data is None or len(data) < 50:
        return None

    upper, _middle, lower = calculate_bollinger_bands(data)
    latest = data.iloc[-1]
    previous = data.iloc[-2]

    current_price = float(latest["Close"])
    upper_band = float(upper.iloc[-1])
    prev_upper_band = float(upper.iloc[-2])

    if current_price > upper_band:
        signal = "NEW_BREAKOUT" if float(previous["Close"]) <= prev_upper_band else "ABOVE_BAND"
    elif current_price < float(lower.iloc[-1]):
        signal = "BELOW_BAND"
    else:
        signal = "NEUTRAL"

    if signal not in {"NEW_BREAKOUT", "ABOVE_BAND"}:
        return None

    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": round(current_price, 2),
        "upper_band": round(upper_band, 2),
        "signal": signal,
        "date": latest.name.strftime("%Y-%m-%d"),
        "timeframe": timeframe,
    }


def analyze_stock_tq(
    ticker: str,
    market: str | None,
    nifty_data: pd.DataFrame,
    timeframe: str = "weekly",
) -> dict | None:
    if is_skippable_symbol(ticker):
        return None

    tf = safe_str(timeframe).lower() or "weekly"
    period, interval = TQ_INTERVAL_MAP.get(tf, TQ_INTERVAL_MAP["weekly"])
    data = _fetch_history(ticker, market, period=period, interval=interval)
    min_bars = TQ_MIN_BARS.get(tf, 65)
    if data is None or len(data) < min_bars:
        return None

    data, nifty = align_ohlcv_with_nifty(data, nifty_data, timeframe=tf, min_bars=min_bars)
    if data is None or nifty is None:
        return None

    if data["Close"].isna().sum() > len(data) * 0.1:
        return None

    rsi = calculate_rsi(data, period=21)
    supertrend, _direction = calculate_supertrend(data, atr_period=10, factor=3)
    adx, di_plus, di_minus = calculate_adx(data, period=13)
    price_ma_13 = data["Close"].rolling(window=13).mean()
    volume_ma_13 = data["Volume"].rolling(window=13).mean()
    long_term_rs = calculate_relative_strength(data, nifty, 52)
    short_term_rs = calculate_relative_strength(data, nifty, 13)

    latest = data.iloc[-1]
    current_price = latest["Close"]
    current_volume = latest["Volume"]
    current_rsi = rsi.iloc[-1]
    current_supertrend = supertrend.iloc[-1]
    current_adx = adx.iloc[-1]
    current_di_plus = di_plus.iloc[-1]
    current_di_minus = di_minus.iloc[-1]
    current_price_ma_13 = price_ma_13.iloc[-1]
    current_volume_ma_13 = volume_ma_13.iloc[-1]
    current_long_term_rs = long_term_rs.iloc[-1]
    current_short_term_rs = short_term_rs.iloc[-1]

    if pd.isna(current_rsi) or current_rsi <= 55:
        return None
    if pd.isna(current_supertrend) or current_price <= current_supertrend:
        return None
    if pd.isna(current_adx) or current_adx <= 20:
        return None
    if (
        pd.isna(current_di_plus)
        or pd.isna(current_di_minus)
        or current_di_plus <= current_di_minus
    ):
        return None
    if pd.isna(current_price_ma_13) or current_price <= current_price_ma_13:
        return None
    if pd.isna(current_volume_ma_13) or current_volume <= current_volume_ma_13:
        return None
    if pd.isna(current_long_term_rs) or current_long_term_rs <= 0:
        return None
    if pd.isna(current_short_term_rs) or current_short_term_rs <= 0:
        return None

    prev_long_term_rs = long_term_rs.iloc[-2] if len(long_term_rs) > 1 else 0
    prev_short_term_rs = short_term_rs.iloc[-2] if len(short_term_rs) > 1 else 0

    long_label = "52P" if tf == "daily" else "52W"
    short_label = "13P" if tf == "daily" else "13W"

    long_term_crossover = (
        prev_long_term_rs < -0.15 and current_long_term_rs > 0.005
    ) or (prev_long_term_rs < 0 and current_long_term_rs > 0.02)
    short_term_crossover = (
        prev_short_term_rs < -0.005 and current_short_term_rs > 0.005
    ) or (prev_short_term_rs < 0.01 and current_short_term_rs > 0.02)

    if long_term_crossover and short_term_crossover:
        crossover_type = f"Both {long_label} & {short_label}"
        crossover_score = 3
    elif long_term_crossover:
        crossover_type = f"{long_label} Only"
        crossover_score = 2
    elif short_term_crossover:
        crossover_type = f"{short_label} Only"
        crossover_score = 1
    else:
        crossover_type = "No Crossover"
        crossover_score = 0

    rsi_score = min(25, max(0, (current_rsi - 55) * 2.5))
    adx_score = min(25, max(0, (current_adx - 20) * 1.25))
    dmi_spread = current_di_plus - current_di_minus
    dmi_score = min(25, max(0, dmi_spread * 2))
    rs_score = min(25, max(0, (current_long_term_rs + current_short_term_rs) * 1000))
    total_score = rsi_score + adx_score + dmi_score + rs_score

    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": round(float(current_price), 2),
        "rsi": round(float(current_rsi), 2),
        "supertrend": round(float(current_supertrend), 2),
        "adx": round(float(current_adx), 2),
        "di_plus": round(float(current_di_plus), 2),
        "di_minus": round(float(current_di_minus), 2),
        "long_term_rs": round(float(current_long_term_rs), 4),
        "short_term_rs": round(float(current_short_term_rs), 4),
        "crossover_type": crossover_type,
        "crossover_score": crossover_score,
        "signal": "TQ_SIGNAL",
        "score": round(total_score, 2),
        "date": latest.name.strftime("%Y-%m-%d"),
        "timeframe": tf,
    }


def _listing_rows(universe: pd.DataFrame) -> list[tuple[str, str | None]]:
    rows: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    markets = (
        universe["market"].tolist() if "market" in universe.columns else [None] * len(universe)
    )
    for ticker, market in zip(universe["ticker"], markets):
        sym = safe_str(ticker).upper()
        if not sym or sym in seen or is_skippable_symbol(sym):
            continue
        seen.add(sym)
        rows.append((sym, safe_str(market) or None))
    return rows


def _meta_lookup(universe: pd.DataFrame) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for _, row in universe.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        lookup[ticker] = {
            "name": safe_str(row.get("name")),
            "market": safe_str(row.get("market")) or None,
            "sector": safe_str(row.get("sector")),
            "industry": safe_str(row.get("industry")),
            "sub_sector": safe_str(row.get("sub_sector")),
        }
    return lookup


def _enrich_results(results: list[dict], meta: dict[str, dict]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()
    rows = []
    for item in results:
        ticker = safe_str(item.get("ticker")).upper()
        info = meta.get(ticker, {})
        rows.append(
            {
                **item,
                "name": info.get("name", ""),
                "market": item.get("market") or info.get("market"),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", item.get("industry", "")),
                "sub_sector": info.get("sub_sector", item.get("sub_sector", "")),
            }
        )
    return attach_research_links(pd.DataFrame(rows))


def _tq_workers(max_workers: int | None, total: int) -> int:
    """Match stock-analysis TQ: min(Conc, ticker count)."""
    workers = STRATEGY_MAX_WORKERS if max_workers is None else int(max_workers)
    workers = max(1, min(workers, STRATEGY_MAX_WORKERS_CAP, total))
    return workers


def _bb_workers(total: int) -> int:
    """Match stock-analysis BB: min(16, max(4, n)) — Conc does not cap BB pool."""
    return max(1, min(STRATEGY_BB_WORKERS_MAX, max(STRATEGY_BB_WORKERS_MIN, total)))


def _shutdown_pool(pool: ThreadPoolExecutor, futures: dict) -> None:
    for future in futures:
        future.cancel()
    pool.shutdown(wait=False, cancel_futures=True)


def _run_parallel_scan(
    jobs: list[tuple],
    analyze_fn: Callable,
    *,
    workers: int,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
    accept_result: Callable[[dict | None], bool] | None = None,
) -> list[dict]:
    if not jobs:
        return []

    total = len(jobs)
    done = 0
    results: list[dict] = []
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = {pool.submit(analyze_fn, *job): job for job in jobs}
    result_timeout = STRATEGY_FUTURE_TIMEOUT if STRATEGY_FUTURE_TIMEOUT > 0 else None

    try:
        for future in as_completed(futures):
            if should_stop and should_stop():
                break
            try:
                res = future.result(timeout=result_timeout)
                if res is not None and (accept_result is None or accept_result(res)):
                    results.append(res)
            except TimeoutError:
                future.cancel()
            except Exception:
                pass
            done += 1
            if progress_callback:
                progress_callback(done, total)
    except KeyboardInterrupt:
        raise
    finally:
        _shutdown_pool(pool, futures)

    return results


def prepare_strategy_universe(
    stocks: pd.DataFrame,
    *,
    cap_tier_id: str = DEFAULT_CAP_TIER,
) -> tuple[pd.DataFrame, int, int]:
    """Build scan universe; cap tier is optional (default All caps = no mcap floor)."""
    universe = analysis_universe(stocks, limit=0)
    cap_excluded = 0

    tier_id = cap_tier_id if cap_tier_id not in ("", None) else "all"
    if tier_id not in ("all",):
        _listings, universe, cap_excluded, _missing = filter_listings_by_cap_tier(
            stocks,
            tier_id,
        )

    return universe, cap_excluded, 0


def run_bb_strategy(
    universe: pd.DataFrame,
    *,
    timeframe: str = "weekly",
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    del max_workers  # BB pool size follows stock-analysis (4–16), not Conc
    listings = _listing_rows(universe)
    if limit is not None and limit > 0:
        listings = listings[:limit]

    if not listings:
        return pd.DataFrame()

    meta = _meta_lookup(universe)
    jobs = [(ticker, market, timeframe) for ticker, market in listings]
    results = _run_parallel_scan(
        jobs,
        analyze_stock_bb,
        workers=_bb_workers(len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
    )

    df = _enrich_results(results, meta)
    if df.empty:
        return df

    df["_signal_priority"] = df["signal"].map(lambda x: 0 if x == "NEW_BREAKOUT" else 1)
    df = df.sort_values(["_signal_priority", "price"], ascending=[True, False])
    return df.drop(columns=["_signal_priority"]).reset_index(drop=True)


def run_bb_worker_count(job_count: int) -> int:
    return _bb_workers(job_count)


def run_tq_worker_count(max_workers: int | None, job_count: int) -> int:
    return _tq_workers(max_workers, job_count)


def run_tq_strategy(
    universe: pd.DataFrame,
    *,
    timeframe: str = "weekly",
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    listings = _listing_rows(universe)
    if limit is not None and limit > 0:
        listings = listings[:limit]

    if not listings:
        return pd.DataFrame()

    tf = safe_str(timeframe).lower() or "weekly"
    nifty_data = get_nifty_data_daily() if tf == "daily" else get_nifty_data()
    if nifty_data.empty:
        return pd.DataFrame()

    meta = _meta_lookup(universe)
    jobs = [(ticker, market, nifty_data, tf) for ticker, market in listings]
    results = _run_parallel_scan(
        jobs,
        analyze_stock_tq,
        workers=_tq_workers(max_workers, len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
        accept_result=lambda res: res.get("signal") == "TQ_SIGNAL",
    )

    df = _enrich_results(results, meta)
    if df.empty:
        return df

    df = df[df["crossover_type"] != "No Crossover"].copy()
    if df.empty:
        return df

    long_key = "52P" if tf == "daily" else "52W"
    short_key = "13P" if tf == "daily" else "13W"
    priority = {
        f"Both {long_key} & {short_key}": 0,
        f"{long_key} Only": 1,
        f"{short_key} Only": 2,
    }
    df["_crossover_priority"] = df["crossover_type"].map(priority).fillna(3)
    df = df.sort_values(["_crossover_priority", "score"], ascending=[True, False])
    return df.drop(columns=["_crossover_priority"]).reset_index(drop=True)
