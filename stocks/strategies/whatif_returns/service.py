"""What-if returns — YTD (invest at year-start → now) plus rolling month %."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from stocks.core.database import get_connection, init_db
from stocks.core.text_utils import safe_str
from stocks.strategies.tq_bb.service import (
    _fetch_history,
    _tq_workers,
    is_skippable_symbol,
)

YTD_COL = "ret_ytd"
YTD_LABEL = "YTD"

# Calendar months lookback → column id / label
RETURN_HORIZONS: tuple[tuple[str, int, str], ...] = (
    ("ret_1m", 1, "1M"),
    ("ret_2m", 2, "2M"),
    ("ret_3m", 3, "3M"),
    ("ret_6m", 6, "6M"),
    ("ret_9m", 9, "9M"),
    ("ret_12m", 12, "12M"),
    ("ret_24m", 24, "24M"),
)

HISTORY_PERIOD = "5y"
HISTORY_INTERVAL = "1d"
MIN_BARS = 40


def _market_matches(row_market: str, filter_market: str) -> bool:
    mk = safe_str(row_market).upper()
    filt = safe_str(filter_market).upper()
    if not filt or filt in {"ALL", "NSE + SME"}:
        # NSE family / All → keep NSE + NSE SME
        if filt == "NSE + SME":
            return mk in {"NSE", "NSE SME"}
        return True
    if filt == "NSE":
        return mk == "NSE"
    return mk == filt


def load_signal_universe(
    *,
    source: str = "tq_bb",
    market: str | None = None,
) -> pd.DataFrame:
    """
    Build a ticker universe for what-if returns.

    ``source``:
      - ``tq_bb`` — cached Strategy TQ + BB signals
      - ``tq`` — TQ only
      - ``bb`` — BB only (prefer NEW_BREAKOUT)
      - ``bb_new`` — BB NEW_BREAKOUT only
      - ``holdings`` — portfolio holdings
    """
    src = safe_str(source).lower() or "tq_bb"
    market_key = safe_str(market).upper()

    if src == "holdings":
        from stocks.shared.portfolio import load_holdings

        df = load_holdings(seed_if_empty=True)
        if df is None or df.empty:
            return pd.DataFrame(columns=["ticker", "name", "market", "source_tag"])
        out = df.copy()
        out["ticker"] = out["ticker"].map(lambda x: safe_str(x).upper())
        if "name" not in out.columns:
            out["name"] = out["ticker"]
        if "market" not in out.columns:
            out["market"] = "NSE"
        out["source_tag"] = "Holding"
        out = out.dropna(subset=["ticker"]).drop_duplicates(subset=["ticker"])
        if market_key:
            out = out[
                out["market"].map(lambda m: _market_matches(m, market_key))
            ]
        return out[["ticker", "name", "market", "source_tag"]].reset_index(drop=True)

    init_db()
    rows: list[dict] = []
    with get_connection() as conn:
        if src in {"tq_bb", "tq"}:
            for r in conn.execute(
                """
                SELECT ticker, market, crossover_type AS detail, timeframe
                FROM strategy_tq_signals
                ORDER BY score DESC
                """
            ):
                rows.append(
                    {
                        "ticker": safe_str(r["ticker"]).upper(),
                        "market": safe_str(r["market"]) or "NSE",
                        "name": safe_str(r["ticker"]).upper(),
                        "source_tag": f"TQ · {safe_str(r['detail']) or r['timeframe']}",
                    }
                )
        if src in {"tq_bb", "bb", "bb_new"}:
            sql = """
                SELECT ticker, market, signal AS detail, timeframe
                FROM strategy_bb_signals
            """
            if src == "bb_new":
                sql += " WHERE signal = 'NEW_BREAKOUT'"
            sql += """
                ORDER BY
                  CASE signal WHEN 'NEW_BREAKOUT' THEN 0 ELSE 1 END,
                  ticker
            """
            for r in conn.execute(sql):
                rows.append(
                    {
                        "ticker": safe_str(r["ticker"]).upper(),
                        "market": safe_str(r["market"]) or "NSE",
                        "name": safe_str(r["ticker"]).upper(),
                        "source_tag": (
                            "BB NEW"
                            if safe_str(r["detail"]) == "NEW_BREAKOUT"
                            else f"BB · {safe_str(r['detail'])}"
                        ),
                    }
                )

    if not rows:
        return pd.DataFrame(columns=["ticker", "name", "market", "source_tag"])

    out = pd.DataFrame(rows)
    # Prefer first tag when ticker appears in both TQ and BB.
    out = out.drop_duplicates(subset=["ticker"], keep="first")
    if market_key:
        out = out[
            out["market"].map(lambda m: _market_matches(m, market_key))
        ]
    return out.reset_index(drop=True)


def _close_on_or_before(hist: pd.DataFrame, target: pd.Timestamp) -> float | None:
    if hist is None or hist.empty:
        return None
    px = hist.sort_index().copy()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    target = pd.Timestamp(target).tz_localize(None).normalize()
    before = px[px.index <= target]
    if before.empty:
        # fall back to first available bar after (short history)
        after = px[px.index >= target]
        if after.empty:
            return None
        return float(after["Close"].iloc[0])
    return float(before["Close"].iloc[-1])


def _year_start_close(
    hist: pd.DataFrame, as_of: pd.Timestamp
) -> tuple[float | None, pd.Timestamp | None]:
    """First trading Close on/after 1 Jan of ``as_of``'s year (buy at year-start)."""
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None, None
    year_start = pd.Timestamp(year=int(as_of.year), month=1, day=1)
    after = hist.loc[hist.index >= year_start]
    if after.empty:
        return None, None
    ts = after.index[0]
    px = float(after["Close"].iloc[0])
    if px <= 0:
        return None, None
    return px, pd.Timestamp(ts)


def analyze_whatif_returns(
    ticker: str,
    market: str | None = None,
    *,
    name: str | None = None,
    source_tag: str | None = None,
    invest_amount: float = 5000.0,
) -> dict | None:
    """
    YTD: % and ₹ today if ``invest_amount`` was invested at start of year.
    Also rolling 1M–24M lookback % / ₹ for context.
    """
    if is_skippable_symbol(ticker):
        return None
    hist = _fetch_history(
        ticker, market, period=HISTORY_PERIOD, interval=HISTORY_INTERVAL
    )
    if hist is None or len(hist) < MIN_BARS or "Close" not in hist.columns:
        return None

    px = hist.sort_index().copy()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    closes = pd.to_numeric(px["Close"], errors="coerce").dropna()
    if closes.empty:
        return None
    price_now = float(closes.iloc[-1])
    if price_now <= 0:
        return None
    as_of = closes.index[-1]
    # Keep only bars with a usable Close for lookbacks / YTD.
    px = px.loc[closes.index]

    row: dict = {
        "ticker": safe_str(ticker).upper(),
        "name": safe_str(name) or safe_str(ticker).upper(),
        "market": safe_str(market).upper() or "NSE",
        "source_tag": safe_str(source_tag) or "",
        "price_now": round(price_now, 2),
        "as_of": as_of.strftime("%Y-%m-%d"),
    }

    ytd_px, ytd_ts = _year_start_close(px, as_of)
    if ytd_px is not None and ytd_ts is not None:
        ret_ytd = (price_now / ytd_px - 1.0) * 100.0
        row[YTD_COL] = round(ret_ytd, 2)
        row[f"val_{YTD_COL}"] = round(float(invest_amount) * (price_now / ytd_px), 2)
        row["ytd_start"] = ytd_ts.strftime("%Y-%m-%d")
        row["price_ytd_start"] = round(ytd_px, 2)
    else:
        row[YTD_COL] = None
        row[f"val_{YTD_COL}"] = None
        row["ytd_start"] = None
        row["price_ytd_start"] = None

    for col, months, _label in RETURN_HORIZONS:
        target = as_of - pd.DateOffset(months=months)
        then = _close_on_or_before(px, target)
        if then is None or then <= 0:
            row[col] = None
            row[f"val_{col}"] = None
            continue
        ret = (price_now / then - 1.0) * 100.0
        row[col] = round(ret, 2)
        row[f"val_{col}"] = round(float(invest_amount) * (price_now / then), 2)

    return row


def run_whatif_returns_scan(
    universe: pd.DataFrame,
    *,
    invest_amount: float = 5000.0,
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    """Compute multi-horizon returns for each ticker in ``universe``."""
    if universe is None or universe.empty:
        return pd.DataFrame()

    work = universe.drop_duplicates(subset=["ticker"]).copy()
    if limit is not None and limit > 0:
        work = work.head(int(limit))

    jobs: list[tuple[str, str | None, str, str]] = []
    for _, r in work.iterrows():
        ticker = safe_str(r.get("ticker")).upper()
        if not ticker:
            continue
        jobs.append(
            (
                ticker,
                safe_str(r.get("market")).upper() or "NSE",
                safe_str(r.get("name")) or ticker,
                safe_str(r.get("source_tag")),
            )
        )
    if not jobs:
        return pd.DataFrame()

    results: list[dict] = []
    total = len(jobs)
    done = 0
    workers = _tq_workers(max_workers, total)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, total))) as pool:
        futures = {
            pool.submit(
                analyze_whatif_returns,
                ticker,
                market,
                name=name,
                source_tag=tag,
                invest_amount=invest_amount,
            ): ticker
            for ticker, market, name, tag in jobs
        }
        for fut in as_completed(futures):
            if should_stop and should_stop():
                break
            ticker = futures[fut]
            done += 1
            if progress_callback:
                progress_callback(done, total, ticker)
            try:
                res = fut.result()
            except Exception:
                continue
            if res:
                results.append(res)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    # Rank by YTD (start-of-year → now), else 3M.
    if YTD_COL in df.columns and pd.to_numeric(df[YTD_COL], errors="coerce").notna().any():
        sort_col = YTD_COL
    else:
        sort_col = "ret_3m" if "ret_3m" in df.columns else "ret_1m"
    df = df.sort_values(
        by=[sort_col, "ticker"],
        ascending=[False, True],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)
    return df


def _horizon_summary_row(
    df: pd.DataFrame,
    *,
    col: str,
    label: str,
    months: int | None,
    invest_amount: float,
) -> dict:
    val_col = f"val_{col}"
    rets = pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(dtype=float)
    vals = (
        pd.to_numeric(df[val_col], errors="coerce")
        if val_col in df.columns
        else pd.Series(dtype=float)
    )
    valid = rets.notna() & vals.notna()
    k = int(valid.sum())
    if k <= 0:
        return {
            "horizon": label,
            "months": months,
            "names": 0,
            "avg_return_pct": None,
            "median_return_pct": None,
            "invested": float(invest_amount),
            "value_now": None,
            "pnl": None,
            "top_ticker": None,
            "top_return_pct": None,
        }
    # Per-stock val assumes full amount in THAT stock. Equal basket of k:
    # each gets invest_amount/k → value_now = mean(val_i).
    mean_val = float(vals[valid].mean())
    avg_ret = float(rets[valid].mean())
    med_ret = float(rets[valid].median())
    top_idx = rets[valid].idxmax()
    top_row = df.loc[top_idx]
    return {
        "horizon": label,
        "months": months,
        "names": k,
        "avg_return_pct": round(avg_ret, 2),
        "median_return_pct": round(med_ret, 2),
        "invested": float(invest_amount),
        "value_now": round(mean_val, 2),
        "pnl": round(mean_val - float(invest_amount), 2),
        "top_ticker": safe_str(top_row.get("ticker")),
        "top_return_pct": round(float(rets.loc[top_idx]), 2),
    }


def portfolio_whatif_summary(
    df: pd.DataFrame,
    *,
    invest_amount: float = 5000.0,
) -> pd.DataFrame:
    """
    Equal-weight basket summary: YTD first, then rolling lookbacks.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    rows: list[dict] = [
        _horizon_summary_row(
            df,
            col=YTD_COL,
            label=YTD_LABEL,
            months=None,
            invest_amount=invest_amount,
        )
    ]
    for col, months, label in RETURN_HORIZONS:
        rows.append(
            _horizon_summary_row(
                df,
                col=col,
                label=label,
                months=months,
                invest_amount=invest_amount,
            )
        )
    return pd.DataFrame(rows)


def top_performers(
    df: pd.DataFrame,
    *,
    horizon_col: str = "ret_3m",
    n: int = 10,
) -> pd.DataFrame:
    if df is None or df.empty or horizon_col not in df.columns:
        return pd.DataFrame()
    work = df.dropna(subset=[horizon_col]).copy()
    work = work.sort_values(horizon_col, ascending=False).head(int(n))
    return work.reset_index(drop=True)


__all__ = [
    "RETURN_HORIZONS",
    "YTD_COL",
    "YTD_LABEL",
    "analyze_whatif_returns",
    "load_signal_universe",
    "portfolio_whatif_summary",
    "run_whatif_returns_scan",
    "top_performers",
]
