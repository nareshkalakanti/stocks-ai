"""Factor investing Quant scan — Chen pipeline composite ranking."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from stocks.core.database import _utc_now, get_connection, init_db
from stocks.core.text_utils import safe_str
from stocks.strategies.factor.construction import (
    DEFAULT_FORWARD_DAYS,
    run_factor_pipeline,
)
from stocks.strategies.tq_bb.service import (
    _fetch_history,
    _listing_rows,
    _run_parallel_scan,
    _tq_workers,
    is_skippable_symbol,
    prepare_strategy_universe,
    run_tq_worker_count,
)

HISTORY_PERIOD = "3y"
HISTORY_INTERVAL = "1d"
# Cross-section needs breadth; cap keeps Yahoo runtime practical.
_MAX_UNIVERSE = 80


def _ensure_factor_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS factor_scores (
            run_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            market TEXT,
            name TEXT,
            sector TEXT,
            asof_date TEXT,
            price REAL,
            composite REAL,
            mom_21 REAL,
            value_proxy REAL,
            vol_factor REAL,
            sector_rel_mom REAL,
            mom_21_z REAL,
            value_proxy_z REAL,
            vol_factor_z REAL,
            sector_rel_mom_z REAL,
            factor_rank INTEGER,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, ticker)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS factor_validation (
            run_id TEXT PRIMARY KEY,
            train_mean_ic REAL,
            train_icir REAL,
            test_mean_ic REAL,
            test_icir REAL,
            random_baseline_ic REAL,
            n_train_periods INTEGER,
            n_test_periods INTEGER,
            n_tickers INTEGER,
            forward_days INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )


def save_factor_run(
    snapshot: pd.DataFrame,
    stats: dict[str, Any],
    *,
    forward_days: int = DEFAULT_FORWARD_DAYS,
) -> str:
    if snapshot is None or not isinstance(snapshot, pd.DataFrame) or snapshot.empty:
        return ""
    init_db()
    run_id = _utc_now().replace(":", "").replace("+", "_")[:20]
    now = _utc_now()

    def _f(row: pd.Series, key: str) -> float | None:
        val = row.get(key)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        if isinstance(val, pd.Series):
            val = val.iloc[0] if len(val) else None
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _i(row: pd.Series, key: str) -> int | None:
        val = _f(row, key)
        return int(val) if val is not None else None

    rows = []
    for _, row in snapshot.iterrows():
        asof = row.get("date")
        if isinstance(asof, pd.Series):
            asof = asof.iloc[0] if len(asof) else None
        rows.append(
            (
                run_id,
                safe_str(row.get("ticker")).upper(),
                safe_str(row.get("market")) or None,
                safe_str(row.get("name")) or None,
                safe_str(row.get("sector")) or None,
                str(asof)[:10] if asof is not None and not pd.isna(asof) else None,
                _f(row, "price"),
                _f(row, "composite"),
                _f(row, "mom_21"),
                _f(row, "value_proxy"),
                _f(row, "vol_factor"),
                _f(row, "sector_rel_mom"),
                _f(row, "mom_21_z"),
                _f(row, "value_proxy_z"),
                _f(row, "vol_factor_z"),
                _f(row, "sector_rel_mom_z"),
                _i(row, "factor_rank"),
                now,
            )
        )
    with get_connection() as conn:
        _ensure_factor_tables(conn)
        conn.executemany(
            """
            INSERT OR REPLACE INTO factor_scores (
                run_id, ticker, market, name, sector, asof_date, price, composite,
                mom_21, value_proxy, vol_factor, sector_rel_mom,
                mom_21_z, value_proxy_z, vol_factor_z, sector_rel_mom_z,
                factor_rank, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO factor_validation (
                run_id, train_mean_ic, train_icir, test_mean_ic, test_icir,
                random_baseline_ic, n_train_periods, n_test_periods,
                n_tickers, forward_days, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                stats.get("train_mean_ic"),
                stats.get("train_icir"),
                stats.get("test_mean_ic"),
                stats.get("test_icir"),
                stats.get("random_baseline_ic"),
                stats.get("n_train_periods"),
                stats.get("n_test_periods"),
                len(snapshot),
                int(forward_days),
                now,
            ),
        )
    return run_id


def _fetch_one(ticker: str, market: str | None) -> dict | None:
    if is_skippable_symbol(ticker):
        return None
    data = _fetch_history(
        ticker, market, period=HISTORY_PERIOD, interval=HISTORY_INTERVAL
    )
    if data is None or not isinstance(data, pd.DataFrame) or data.empty:
        return None
    cols = {str(c).strip().lower() for c in data.columns}
    # MultiIndex from batch download: level-0 names.
    if isinstance(data.columns, pd.MultiIndex):
        cols |= {str(c[0]).strip().lower() for c in data.columns if isinstance(c, tuple)}
    if "close" not in cols:
        return None
    return {"ticker": safe_str(ticker).upper(), "market": market, "hist": data}


def run_factor_scan(
    universe: pd.DataFrame,
    *,
    limit: int | None = None,
    max_workers: int | None = None,
    progress_callback=None,
    should_stop: Callable[[], bool] | None = None,
    forward_days: int = DEFAULT_FORWARD_DAYS,
    keep_top_frac: float = 1.0,
) -> pd.DataFrame:
    """
    Build Chen-style factor panel on the filtered universe, rank by composite.

    Validation stats are attached on ``df.attrs["factor_validation"]``.
    """
    del keep_top_frac  # always return full ranked cross-section
    if universe is None or not isinstance(universe, pd.DataFrame):
        return pd.DataFrame()
    listings = _listing_rows(universe)
    if limit is not None and limit > 0:
        listings = listings[:limit]
    listings = listings[:_MAX_UNIVERSE]
    if not listings:
        return pd.DataFrame()

    meta = {
        safe_str(row.get("ticker")).upper(): {
            "name": safe_str(row.get("name")),
            "market": safe_str(row.get("market")) or None,
            "sector": safe_str(row.get("sector")) or "Unknown",
            "industry": safe_str(row.get("industry")),
            "sub_sector": safe_str(row.get("sub_sector")),
        }
        for _, row in universe.iterrows()
        if safe_str(row.get("ticker"))
    }
    sectors = {t: (m.get("sector") or "Unknown") for t, m in meta.items()}

    jobs = [(ticker, market) for ticker, market in listings]
    fetched = _run_parallel_scan(
        jobs,
        _fetch_one,
        workers=_tq_workers(max_workers, len(jobs)),
        progress_callback=progress_callback,
        should_stop=should_stop,
        accept_result=lambda res: res is not None and res.get("hist") is not None,
    )

    data: dict[str, pd.DataFrame] = {}
    for row in fetched:
        t = safe_str(row.get("ticker")).upper()
        hist = row.get("hist")
        if t and isinstance(hist, pd.DataFrame):
            data[t] = hist

    if len(data) < 5:
        empty = pd.DataFrame()
        empty.attrs["factor_validation"] = {
            "error": "insufficient_history",
            "n_tickers": len(data),
        }
        return empty

    if progress_callback:
        try:
            progress_callback(len(jobs), len(jobs))
        except Exception:
            pass

    latest, _panel, stats = run_factor_pipeline(
        data, sectors=sectors, forward_days=forward_days
    )
    if latest.empty:
        empty = pd.DataFrame()
        empty.attrs["factor_validation"] = stats
        return empty

    # Enrich display fields (keep a slim frame — drop raw OHLCV noise).
    keep_cols = [
        c
        for c in (
            "factor_rank",
            "ticker",
            "date",
            "close",
            "composite",
            "mom_21",
            "mom_63",
            "mom_126",
            "value_proxy",
            "vol_factor",
            "sector_rel_mom",
            "mom_21_z",
            "value_proxy_z",
            "vol_factor_z",
            "sector_rel_mom_z",
            "sector",
        )
        if c in latest.columns
    ]
    out = latest.loc[:, keep_cols].copy()
    close = pd.to_numeric(out["close"], errors="coerce") if "close" in out.columns else None
    out["price"] = close.round(2) if close is not None else None
    out["name"] = out["ticker"].map(lambda t: (meta.get(t) or {}).get("name") or t)
    out["market"] = out["ticker"].map(
        lambda t: (meta.get(t) or {}).get("market") or "NSE"
    )
    out["industry"] = out["ticker"].map(
        lambda t: (meta.get(t) or {}).get("industry") or ""
    )
    out["sub_sector"] = out["ticker"].map(
        lambda t: (meta.get(t) or {}).get("sub_sector") or ""
    )
    sector_series = out["sector"] if "sector" in out.columns else None
    if isinstance(sector_series, pd.DataFrame):
        sector_series = sector_series.iloc[:, 0]
    sector_ok = (
        isinstance(sector_series, pd.Series)
        and sector_series.notna().any()
        and sector_series.astype(str).str.strip().ne("").any()
    )
    if not sector_ok:
        out["sector"] = out["ticker"].map(
            lambda t: (meta.get(t) or {}).get("sector") or "Unknown"
        )
    mom = pd.to_numeric(out["mom_21"], errors="coerce") if "mom_21" in out.columns else None
    out["momentum_pct"] = (mom * 100.0) if mom is not None else None
    out["score"] = (
        pd.to_numeric(out["composite"], errors="coerce")
        if "composite" in out.columns
        else None
    )
    out["signal"] = "FACTOR"
    out["pattern"] = "Factor"
    out["pattern_code"] = "FACTOR"

    def _detail(row: pd.Series) -> str:
        comp = row.get("composite") if isinstance(row, pd.Series) else None
        if comp is None or pd.isna(comp):
            return "factor"
        try:
            return f"Comp {float(comp):+.2f}"
        except (TypeError, ValueError):
            return "factor"

    out["detail"] = out.apply(_detail, axis=1)

    try:
        run_id = save_factor_run(out, stats, forward_days=forward_days)
        stats = dict(stats)
        stats["run_id"] = run_id
    except Exception:
        pass

    out.attrs["factor_validation"] = stats
    return out.reset_index(drop=True)


prepare_factor_universe = prepare_strategy_universe

# Back-compat for detect imports used elsewhere
analyze_factor = _fetch_one

__all__ = [
    "analyze_factor",
    "prepare_factor_universe",
    "run_factor_scan",
    "run_tq_worker_count",
    "save_factor_run",
]
