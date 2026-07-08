from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

from stocks.scans.results_utils import analysis_universe
from stocks.core.database import load_market_cap_from_db, load_metrics_from_db, save_metrics_to_db
from stocks.core.log_service import METRICS_ERROR, PRICE_ERROR, STOCK_NOT_FOUND, log_error
from stocks.market.yfinance_limits import call_throttled

from stocks.core.config import YFINANCE_REQUEST_DELAY


from stocks.core.text_utils import safe_str


def to_yfinance_symbol(ticker: str, market: str | None = None) -> str:
    ticker = safe_str(ticker).upper()
    if ticker.endswith((".NS", ".BO")):
        return ticker

    market_key = safe_str(market).upper()
    if market_key in {"NSE", "NATIONAL STOCK EXCHANGE"}:
        return f"{ticker}.NS"
    if market_key in {"BSE", "BOMBAY STOCK EXCHANGE"}:
        return f"{ticker}.BO"
    return f"{ticker}.NS"


def fetch_current_prices(
    tickers: list[str],
    markets: list[str | None] | None = None,
) -> dict[str, float | None]:
    if not tickers:
        return {}

    markets = markets or [None] * len(tickers)
    symbol_map: dict[str, str] = {}
    for ticker, market in zip(tickers, markets):
        symbol = to_yfinance_symbol(ticker, market)
        symbol_map[ticker] = symbol

    unique_symbols = list(dict.fromkeys(symbol_map.values()))
    prices: dict[str, float | None] = {t: None for t in tickers}

    try:
        data = yf.download(
            unique_symbols,
            period="1d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as exc:
        for ticker, symbol in symbol_map.items():
            log_error(
                PRICE_ERROR,
                "yfinance batch download failed",
                ticker=ticker,
                symbol=symbol,
                error=str(exc),
            )
        return prices

    if data.empty:
        for ticker, symbol in symbol_map.items():
            log_error(
                PRICE_ERROR,
                "No price data returned from yfinance",
                ticker=ticker,
                symbol=symbol,
            )
        return prices

    for ticker, symbol in symbol_map.items():
        try:
            if len(unique_symbols) == 1:
                close = data["Close"].iloc[-1]
            else:
                close = data[symbol]["Close"].iloc[-1]
            if close is not None and not pd.isna(close):
                prices[ticker] = round(float(close), 2)
            else:
                log_error(
                    PRICE_ERROR,
                    "Close price is empty or NaN",
                    ticker=ticker,
                    symbol=symbol,
                )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            log_error(
                PRICE_ERROR,
                "Failed to parse price from yfinance response",
                ticker=ticker,
                symbol=symbol,
                error=str(exc),
            )

    return prices


def _fetch_single_metrics(ticker: str, market: str | None) -> dict:
    symbol = to_yfinance_symbol(ticker, market)
    metrics: dict = {"ticker": ticker, "yf_symbol": symbol}

    def _log(exc: Exception) -> None:
        log_error(
            METRICS_ERROR,
            "Failed to fetch stock metrics",
            ticker=ticker,
            symbol=symbol,
            error=str(exc),
        )

    def _fetch() -> dict:
        yt = yf.Ticker(symbol)
        info = yt.info or {}
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
            if not info.get("shortName") and not info.get("longName"):
                log_error(
                    STOCK_NOT_FOUND,
                    "No company info from yfinance",
                    ticker=ticker,
                    symbol=symbol,
                )

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is not None:
            metrics["price"] = round(float(price), 2)
        else:
            log_error(
                PRICE_ERROR,
                "No current price in yfinance info",
                ticker=ticker,
                symbol=symbol,
            )

        pe = info.get("trailingPE")
        if pe is not None and not pd.isna(pe):
            metrics["pe"] = round(float(pe), 1)

        market_cap = info.get("marketCap")
        if market_cap is not None and not pd.isna(market_cap):
            metrics["market_cap_cr"] = round(float(market_cap) / 1e7, 1)

        sector = info.get("sector")
        if sector:
            metrics["sector"] = safe_str(sector)

        for key, col in (
            ("fiftyTwoWeekHigh", "52w_high"),
            ("fiftyTwoWeekLow", "52w_low"),
        ):
            val = info.get(key)
            if val is not None and not pd.isna(val):
                metrics[col] = round(float(val), 2)

        hist = yt.history(period="1y")
        if len(hist) >= 2:
            ret = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
            metrics["return_1y_pct"] = round(float(ret), 1)
        elif len(hist) == 0:
            log_error(
                STOCK_NOT_FOUND,
                "No price history returned from yfinance",
                ticker=ticker,
                symbol=symbol,
            )
        return metrics

    try:
        result = call_throttled(
            _fetch,
            delay=YFINANCE_REQUEST_DELAY,
            on_error=_log,
        )
        if result is not None:
            metrics.update(result)
    except Exception as exc:
        _log(exc)
    return metrics


def fetch_stock_metrics(
    tickers: list[str],
    markets: list[str | None] | None = None,
    *,
    max_workers: int = 8,
    use_cache: bool = True,
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()

    markets = markets or [None] * len(tickers)
    ticker_market = dict(zip(tickers, markets))

    cached_df = load_metrics_from_db(tickers) if use_cache else pd.DataFrame()
    cached_tickers: set[str] = set()
    if not cached_df.empty:
        cached_tickers = set(cached_df["ticker"].astype(str))

    missing_tickers = [t for t in tickers if t not in cached_tickers]
    fetched_rows: list[dict] = []

    if missing_tickers:
        missing_markets = [ticker_market[t] for t in missing_tickers]
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_fetch_single_metrics, ticker, market): ticker
                for ticker, market in zip(missing_tickers, missing_markets)
            }
            for future in as_completed(futures):
                fetched_rows.append(future.result())

        if fetched_rows:
            fetched_df = pd.DataFrame(fetched_rows)
            save_metrics_to_db(fetched_df, missing_markets)
            if not cached_df.empty:
                return pd.concat([cached_df, fetched_df], ignore_index=True)
            return fetched_df

    return cached_df


def attach_market_data(
    df: pd.DataFrame,
    *,
    max_rows: int = 80,
    use_cache: bool = True,
) -> pd.DataFrame:
    if df.empty or "ticker" not in df.columns:
        return df

    subset = analysis_universe(df, limit=max_rows)
    markets = subset["market"].tolist() if "market" in subset.columns else [None] * len(subset)
    metrics = fetch_stock_metrics(
        subset["ticker"].tolist(),
        markets,
        use_cache=use_cache,
    )
    if metrics.empty:
        return df

    merge_cols = [
        c
        for c in (
            "ticker",
            "price",
            "pe",
            "market_cap_cr",
            "sector",
            "52w_high",
            "52w_low",
            "return_1y_pct",
        )
        if c in metrics.columns
    ]
    merged = df.merge(metrics[merge_cols], on="ticker", how="left")
    if "price" in merged.columns and "current_price" not in merged.columns:
        merged["current_price"] = merged["price"]
    return merged


def attach_prices(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ticker" not in df.columns:
        return df

    markets = df["market"].tolist() if "market" in df.columns else [None] * len(df)
    prices = fetch_current_prices(df["ticker"].tolist(), markets)

    result = df.copy()
    result["current_price"] = result["ticker"].map(prices)
    return result
