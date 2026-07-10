import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from stocks.core.config import (
    DATA_DIR,
    DB_PATH,
    FUNDAMENTALS_CACHE_HOURS,
    MARKET_CAP_CACHE_HOURS,
    METRICS_CACHE_HOURS,
    REPORTS_CACHE_HOURS,
    STOCKS_CACHE_HOURS,
)
from stocks.core.text_utils import safe_str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_fresh(fetched_at: str | None, max_hours: int) -> bool:
    ts = _parse_ts(fetched_at)
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts < timedelta(hours=max_hours)


@contextmanager
def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS stocks (
                ticker TEXT NOT NULL,
                name TEXT,
                market TEXT,
                sector TEXT,
                industry TEXT,
                sub_sector TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (ticker, market)
            );

            CREATE TABLE IF NOT EXISTS stock_metrics (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                yf_symbol TEXT,
                price REAL,
                pe REAL,
                market_cap_cr REAL,
                w52_high REAL,
                w52_low REAL,
                return_1y_pct REAL,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT NOT NULL UNIQUE,
                market TEXT,
                sector TEXT,
                model TEXT,
                include_fundamentals INTEGER,
                top_n INTEGER,
                results_json TEXT NOT NULL,
                raw_response TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_stock_metrics_fetched
                ON stock_metrics(fetched_at);
            CREATE INDEX IF NOT EXISTS idx_research_reports_created
                ON research_reports(created_at);

            CREATE TABLE IF NOT EXISTS fundamentals_cache (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                yf_symbol TEXT,
                roce_pct REAL,
                ev_ebitda REAL,
                debt_to_equity REAL,
                current_ratio REAL,
                book_value REAL,
                price REAL,
                market_cap_cr REAL,
                fetched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_fundamentals_cache_fetched
                ON fundamentals_cache(fetched_at);

            CREATE TABLE IF NOT EXISTS pead_earnings (
                ticker TEXT NOT NULL,
                quarter_end TEXT NOT NULL,
                result_date TEXT,
                eps REAL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (ticker, quarter_end)
            );

            CREATE TABLE IF NOT EXISTS pead_prices (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                close REAL,
                PRIMARY KEY (ticker, date)
            );

            CREATE INDEX IF NOT EXISTS idx_pead_earnings_ticker
                ON pead_earnings(ticker);
            CREATE INDEX IF NOT EXISTS idx_pead_prices_ticker
                ON pead_prices(ticker);

            CREATE TABLE IF NOT EXISTS holdings (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                name TEXT,
                sector TEXT,
                sub_sector TEXT,
                qty REAL,
                avg_price REAL,
                snapshot_price REAL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pead2_cache (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pead2_cache_fetched
                ON pead2_cache(fetched_at);

            CREATE TABLE IF NOT EXISTS stock_notes (
                ticker TEXT PRIMARY KEY,
                business TEXT,
                market_position TEXT,
                triggers_json TEXT,
                source TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS valuepickr_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS superstar_portfolios_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                cache_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS intrinsic_value_cache (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                name TEXT,
                price REAL,
                market_cap_cr REAL,
                sales_growth_3y REAL,
                roce_3y REAL,
                pb REAL,
                fetched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_intrinsic_value_cache_fetched
                ON intrinsic_value_cache(fetched_at);

            CREATE TABLE IF NOT EXISTS headwind_scan_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                cache_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS headwind_scan_cache_v2 (
                scan_market TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                cache_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS valuepickr_opportunities (
                topic_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                slug TEXT,
                ticker TEXT,
                company TEXT,
                market TEXT,
                sector TEXT,
                subcategory TEXT,
                smart_rank REAL,
                rank INTEGER,
                replies INTEGER,
                views INTEGER,
                likes INTEGER,
                listed INTEGER NOT NULL DEFAULT 0,
                demerger INTEGER NOT NULL DEFAULT 0,
                spin_off INTEGER NOT NULL DEFAULT 0,
                special_situation INTEGER NOT NULL DEFAULT 0,
                last_posted_at TEXT,
                created_at TEXT,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS valuepickr_analyses (
                topic_id INTEGER PRIMARY KEY,
                url TEXT NOT NULL,
                title TEXT,
                company TEXT,
                analysis_md TEXT NOT NULL,
                strengths_json TEXT,
                sentiment_json TEXT,
                summary_2025_json TEXT,
                posts_count INTEGER,
                analyzed_through TEXT,
                fetched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_vp_opp_ticker
                ON valuepickr_opportunities(ticker);
            CREATE INDEX IF NOT EXISTS idx_vp_opp_fetched
                ON valuepickr_opportunities(fetched_at);

            CREATE TABLE IF NOT EXISTS superstar_symbol_cache (
                norm_name TEXT PRIMARY KEY,
                symbol TEXT,
                exchange TEXT,
                screener_slug TEXT,
                resolver_version INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS superstar_holdings (
                investor TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL DEFAULT 'NSE',
                company_name TEXT,
                holding_percent REAL,
                change_qtr REAL,
                change_type TEXT,
                holding_value_cr REAL,
                price REAL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (investor, symbol, exchange)
            );

            CREATE INDEX IF NOT EXISTS idx_superstar_holdings_symbol
                ON superstar_holdings(symbol);
            CREATE INDEX IF NOT EXISTS idx_superstar_holdings_fetched
                ON superstar_holdings(fetched_at);

            CREATE TABLE IF NOT EXISTS strategy_tq_signals (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                score REAL,
                crossover_type TEXT,
                crossover_score INTEGER,
                signal_date TEXT,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_bb_signals (
                ticker TEXT NOT NULL,
                market TEXT,
                signal TEXT NOT NULL,
                timeframe TEXT NOT NULL DEFAULT 'weekly',
                price REAL,
                upper_band REAL,
                signal_date TEXT,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (ticker, timeframe)
            );

            CREATE INDEX IF NOT EXISTS idx_strategy_bb_ticker
                ON strategy_bb_signals(ticker);

            CREATE TABLE IF NOT EXISTS business_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                token TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS business_group_members (
                group_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'NSE',
                name TEXT,
                demerger INTEGER NOT NULL DEFAULT 0,
                spin_off INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (group_id, ticker, market),
                FOREIGN KEY (group_id) REFERENCES business_groups(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_business_group_members_ticker
                ON business_group_members(ticker);

            CREATE TABLE IF NOT EXISTS company_profile_cache (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                website TEXT,
                long_description TEXT,
                company_sector TEXT,
                company_industry TEXT,
                headquarters TEXT,
                employees INTEGER,
                source TEXT,
                fetched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_company_profile_cache_fetched
                ON company_profile_cache(fetched_at);
            """
        )
        _ensure_stocks_columns(conn)
        _ensure_holdings_columns(conn)
        _ensure_stock_metrics_columns(conn)
        _ensure_business_group_members_columns(conn)
        _ensure_intrinsic_value_cache_columns(conn)
        _migrate_headwind_scan_cache(conn)


def _migrate_headwind_scan_cache(conn) -> None:
    """Copy legacy single-row cache into per-exchange v2 table."""
    try:
        row = conn.execute(
            """
            SELECT payload_json, fetched_at, cache_version
            FROM headwind_scan_cache
            WHERE id = 1
            """
        ).fetchone()
    except sqlite3.OperationalError:
        return
    if row is None:
        return
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        payload = {}
    scan_market = safe_str(payload.get("scan_market")).upper() or "ALL"
    exists = conn.execute(
        "SELECT 1 FROM headwind_scan_cache_v2 WHERE scan_market = ? LIMIT 1",
        (scan_market,),
    ).fetchone()
    if exists:
        return
    conn.execute(
        """
        INSERT OR IGNORE INTO headwind_scan_cache_v2 (
            scan_market, payload_json, fetched_at, cache_version
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            scan_market,
            row["payload_json"],
            row["fetched_at"],
            int(row["cache_version"] or HEADWIND_SCAN_CACHE_VERSION),
        ),
    )


def _ensure_intrinsic_value_cache_columns(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(intrinsic_value_cache)")}
    if "pe_ratio" not in cols:
        conn.execute("ALTER TABLE intrinsic_value_cache ADD COLUMN pe_ratio REAL")
    if "forward_pe" not in cols:
        conn.execute("ALTER TABLE intrinsic_value_cache ADD COLUMN forward_pe REAL")


def _ensure_business_group_members_columns(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(business_group_members)")}
    if "demerger" not in cols:
        conn.execute(
            "ALTER TABLE business_group_members ADD COLUMN demerger INTEGER NOT NULL DEFAULT 0"
        )
    if "spin_off" not in cols:
        conn.execute(
            "ALTER TABLE business_group_members ADD COLUMN spin_off INTEGER NOT NULL DEFAULT 0"
        )


def _ensure_stock_metrics_columns(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(stock_metrics)")}
    if "sector" not in cols:
        conn.execute("ALTER TABLE stock_metrics ADD COLUMN sector TEXT")


def _ensure_holdings_columns(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(holdings)")}
    if "industry" not in cols:
        conn.execute("ALTER TABLE holdings ADD COLUMN industry TEXT")


def _ensure_stocks_columns(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(stocks)")}
    for col, ddl in (
        ("industry", "ALTER TABLE stocks ADD COLUMN industry TEXT"),
        ("sub_sector", "ALTER TABLE stocks ADD COLUMN sub_sector TEXT"),
    ):
        if col not in cols:
            conn.execute(ddl)


def db_stats() -> dict[str, int]:
    init_db()
    with get_connection() as conn:
        stocks = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        metrics = conn.execute("SELECT COUNT(*) FROM stock_metrics").fetchone()[0]
        mcap_rows = conn.execute(
            """
            SELECT COUNT(DISTINCT ticker) FROM (
                SELECT ticker FROM stock_metrics WHERE market_cap_cr IS NOT NULL
                UNION
                SELECT ticker FROM fundamentals_cache WHERE market_cap_cr IS NOT NULL
            )
            """
        ).fetchone()[0]
        fundamentals = conn.execute("SELECT COUNT(*) FROM fundamentals_cache").fetchone()[0]
        pead_eps = conn.execute("SELECT COUNT(*) FROM pead_earnings").fetchone()[0]
        pead_px = conn.execute("SELECT COUNT(*) FROM pead_prices").fetchone()[0]
        reports = conn.execute("SELECT COUNT(*) FROM research_reports").fetchone()[0]
        holdings = conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
        business_groups = conn.execute("SELECT COUNT(*) FROM business_groups").fetchone()[0]
        business_group_members = conn.execute(
            "SELECT COUNT(*) FROM business_group_members"
        ).fetchone()[0]
    return {
        "stocks": stocks,
        "metrics": metrics,
        "market_cap": mcap_rows,
        "fundamentals": fundamentals,
        "pead_earnings": pead_eps,
        "pead_prices": pead_px,
        "reports": reports,
        "holdings": holdings,
        "business_groups": business_groups,
        "business_group_members": business_group_members,
    }


def stocks_cache_fresh() -> bool:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT MAX(updated_at) AS ts FROM stocks").fetchone()
    return _is_fresh(row["ts"] if row else None, STOCKS_CACHE_HOURS)


def _normalize_stock_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in ("ticker", "name", "market", "sector", "industry", "sub_sector", "reason"):
        if col in out.columns:
            out[col] = out[col].fillna("").astype(str).replace("nan", "")
    return out


def load_stocks_from_db() -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        _ensure_stocks_columns(conn)
        rows = conn.execute(
            """
            SELECT ticker, name, market, sector, industry, sub_sector
            FROM stocks ORDER BY ticker
            """
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return _normalize_stock_frame(pd.DataFrame([dict(r) for r in rows]))


def save_stocks_to_db(stocks: pd.DataFrame) -> int:
    init_db()
    now = _utc_now()
    frame = stocks.copy()
    if "industry" not in frame.columns:
        frame["industry"] = ""
    if "sub_sector" not in frame.columns:
        frame["sub_sector"] = ""
    records = frame[
        ["ticker", "name", "market", "sector", "industry", "sub_sector"]
    ].drop_duplicates(subset=["ticker", "market"])
    with get_connection() as conn:
        _ensure_stocks_columns(conn)
        conn.execute("DELETE FROM stocks")
        conn.executemany(
            """
            INSERT INTO stocks (
                ticker, name, market, sector, industry, sub_sector, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r.ticker,
                    r.name,
                    r.market,
                    r.sector,
                    r.industry,
                    r.sub_sector,
                    now,
                )
                for r in records.itertuples(index=False)
            ],
        )
    return len(records)


def load_metrics_from_db(tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    init_db()
    placeholders = ",".join("?" * len(tickers))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, market, yf_symbol, price, pe, market_cap_cr, sector,
                   w52_high AS "52w_high", w52_low AS "52w_low",
                   return_1y_pct, fetched_at
            FROM stock_metrics
            WHERE ticker IN ({placeholders})
            """,
            tickers,
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    fresh = df["fetched_at"].apply(lambda ts: _is_fresh(ts, METRICS_CACHE_HOURS))
    df = df[fresh].drop(columns=["fetched_at"], errors="ignore")
    # Null market_cap rows are failed fetches — treat as uncached so we retry.
    if "market_cap_cr" in df.columns:
        df = df[df["market_cap_cr"].notna()]
    return df


def load_market_cap_from_db(tickers: list[str] | None = None) -> pd.DataFrame:
    """Load market_cap_cr from SQLite (fundamentals_cache + stock_metrics, longest TTL)."""
    init_db()
    params: tuple = ()
    where = "WHERE market_cap_cr IS NOT NULL"
    if tickers:
        placeholders = ",".join("?" * len(tickers))
        where = f"WHERE ticker IN ({placeholders}) AND market_cap_cr IS NOT NULL"
        params = tuple(tickers)

    frames: list[pd.DataFrame] = []
    with get_connection() as conn:
        for table in ("fundamentals_cache", "stock_metrics"):
            rows = conn.execute(
                f"""
                SELECT ticker, market, market_cap_cr, fetched_at
                FROM {table}
                {where}
                """,
                params,
            ).fetchall()
            if rows:
                frames.append(pd.DataFrame([dict(r) for r in rows]))

    if not frames:
        return pd.DataFrame(columns=["ticker", "market_cap_cr"])

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("fetched_at").drop_duplicates("ticker", keep="last")
    fresh = combined["fetched_at"].apply(lambda ts: _is_fresh(ts, MARKET_CAP_CACHE_HOURS))
    cols = ["ticker", "market_cap_cr"]
    if "market" in combined.columns:
        cols.append("market")
    return combined.loc[fresh, cols].reset_index(drop=True)


def save_market_cap_to_db(
    ticker: str,
    market_cap_cr: float,
    *,
    market: str | None = None,
    yf_symbol: str | None = None,
    price: float | None = None,
) -> None:
    """Persist market cap from any scan (Earnings, Fundamentals, etc.) for reuse."""
    init_db()
    now = _utc_now()
    ticker = str(ticker).strip().upper()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO stock_metrics (
                ticker, market, yf_symbol, price, pe, market_cap_cr,
                w52_high, w52_low, return_1y_pct, fetched_at
            ) VALUES (?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=COALESCE(excluded.market, stock_metrics.market),
                yf_symbol=COALESCE(excluded.yf_symbol, stock_metrics.yf_symbol),
                price=COALESCE(excluded.price, stock_metrics.price),
                market_cap_cr=excluded.market_cap_cr,
                fetched_at=excluded.fetched_at
            """,
            (ticker, market, yf_symbol, price, market_cap_cr, now),
        )
        conn.execute(
            """
            UPDATE fundamentals_cache
            SET market_cap_cr = ?, fetched_at = ?
            WHERE ticker = ?
            """,
            (market_cap_cr, now, ticker),
        )


def save_metrics_to_db(metrics: pd.DataFrame, markets: list[str | None]) -> None:
    if metrics.empty:
        return
    init_db()
    now = _utc_now()
    market_map = dict(zip(metrics["ticker"], markets))
    rows = []
    for _, row in metrics.iterrows():
        ticker = row["ticker"]
        cap = row.get("market_cap_cr")
        if cap is None or (isinstance(cap, float) and pd.isna(cap)):
            continue
        rows.append(
            (
                ticker,
                market_map.get(ticker),
                row.get("yf_symbol"),
                row.get("price"),
                row.get("pe"),
                cap,
                row.get("sector"),
                row.get("52w_high"),
                row.get("52w_low"),
                row.get("return_1y_pct"),
                now,
            )
        )
    if not rows:
        return
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO stock_metrics (
                ticker, market, yf_symbol, price, pe, market_cap_cr, sector,
                w52_high, w52_low, return_1y_pct, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market,
                yf_symbol=excluded.yf_symbol,
                price=excluded.price,
                pe=excluded.pe,
                market_cap_cr=excluded.market_cap_cr,
                sector=COALESCE(excluded.sector, stock_metrics.sector),
                w52_high=excluded.w52_high,
                w52_low=excluded.w52_low,
                return_1y_pct=excluded.return_1y_pct,
                fetched_at=excluded.fetched_at
            """,
            rows,
        )


def load_fundamentals_cache(tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    init_db()
    placeholders = ",".join("?" * len(tickers))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, market, yf_symbol, roce_pct, ev_ebitda, debt_to_equity,
                   current_ratio, book_value, price, market_cap_cr, fetched_at
            FROM fundamentals_cache
            WHERE ticker IN ({placeholders})
            """,
            tickers,
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    fresh = df["fetched_at"].apply(lambda ts: _is_fresh(ts, FUNDAMENTALS_CACHE_HOURS))
    return df[fresh].drop(columns=["fetched_at"], errors="ignore")


def save_fundamentals_cache(metrics: pd.DataFrame, markets: list[str | None]) -> None:
    if metrics.empty:
        return
    init_db()
    now = _utc_now()
    market_map = dict(zip(metrics["ticker"], markets))
    rows = []
    for _, row in metrics.iterrows():
        ticker = row["ticker"]
        rows.append(
            (
                ticker,
                market_map.get(ticker),
                row.get("yf_symbol"),
                row.get("roce_pct"),
                row.get("ev_ebitda"),
                row.get("debt_to_equity"),
                row.get("current_ratio"),
                row.get("book_value"),
                row.get("price"),
                row.get("market_cap_cr"),
                now,
            )
        )
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO fundamentals_cache (
                ticker, market, yf_symbol, roce_pct, ev_ebitda, debt_to_equity,
                current_ratio, book_value, price, market_cap_cr, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market,
                yf_symbol=excluded.yf_symbol,
                roce_pct=excluded.roce_pct,
                ev_ebitda=excluded.ev_ebitda,
                debt_to_equity=excluded.debt_to_equity,
                current_ratio=excluded.current_ratio,
                book_value=excluded.book_value,
                price=excluded.price,
                market_cap_cr=excluded.market_cap_cr,
                fetched_at=excluded.fetched_at
            """,
            rows,
        )


def report_cache_key(
    market: str,
    sector: str,
    model: str,
    include_fundamentals: bool,
    top_n: int,
    *,
    include_sentiment: bool = False,
    sentiment_model: str = "",
    universe_limit: int = 80,
    analysis_mode: str = "picks",
    cap_tier: str = "all",
) -> str:
    payload = json.dumps(
        {
            "market": market,
            "sector": sector,
            "model": model,
            "include_fundamentals": include_fundamentals,
            "include_sentiment": include_sentiment,
            "sentiment_model": sentiment_model,
            "top_n": top_n,
            "universe_limit": universe_limit,
            "analysis_mode": analysis_mode,
            "cap_tier": cap_tier,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def load_report(cache_key: str) -> dict[str, Any] | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT results_json, raw_response, created_at, market, sector, model
            FROM research_reports WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
    if row is None:
        return None
    if not _is_fresh(row["created_at"], REPORTS_CACHE_HOURS):
        return None
    return {
        "results": _normalize_stock_frame(pd.DataFrame(json.loads(row["results_json"]))),
        "raw_response": row["raw_response"] or "",
        "created_at": row["created_at"],
        "market": row["market"],
        "sector": row["sector"],
        "model": row["model"],
    }


def save_report(
    cache_key: str,
    market: str,
    sector: str,
    model: str,
    include_fundamentals: bool,
    top_n: int,
    results: pd.DataFrame,
    raw_response: str,
) -> None:
    init_db()
    now = _utc_now()
    results_json = results.to_json(orient="records")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO research_reports (
                cache_key, market, sector, model, include_fundamentals,
                top_n, results_json, raw_response, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                results_json=excluded.results_json,
                raw_response=excluded.raw_response,
                created_at=excluded.created_at
            """,
            (
                cache_key,
                market,
                sector,
                model,
                int(include_fundamentals),
                top_n,
                results_json,
                raw_response,
                now,
            ),
        )


def list_recent_reports(limit: int = 20) -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT market, sector, model, include_fundamentals, top_n, created_at
            FROM research_reports
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def load_holdings_from_db() -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ticker, market, name, sector, industry, sub_sector, qty, avg_price, snapshot_price
            FROM holdings
            ORDER BY ticker
            """
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def save_holdings_to_db(df: pd.DataFrame) -> None:
    if df.empty:
        return
    init_db()
    now = _utc_now()
    with get_connection() as conn:
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            conn.execute(
                """
                INSERT INTO holdings (
                    ticker, market, name, sector, industry, sub_sector,
                    qty, avg_price, snapshot_price, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    market=excluded.market,
                    name=excluded.name,
                    sector=excluded.sector,
                    industry=excluded.industry,
                    sub_sector=excluded.sub_sector,
                    qty=excluded.qty,
                    avg_price=excluded.avg_price,
                    snapshot_price=excluded.snapshot_price,
                    updated_at=excluded.updated_at
                """,
                (
                    ticker,
                    row.get("market"),
                    row.get("name"),
                    row.get("sector"),
                    row.get("industry"),
                    row.get("sub_sector"),
                    row.get("qty"),
                    row.get("avg_price"),
                    row.get("snapshot_price"),
                    now,
                ),
            )


def replace_holdings_in_db(df: pd.DataFrame) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM holdings")
    save_holdings_to_db(df)


def holdings_count() -> int:
    init_db()
    with get_connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0])


def load_pead2_cache(tickers: list[str], *, max_hours: int) -> dict[str, dict]:
    """Fresh PEAD2 scan rows keyed by ticker."""
    if not tickers:
        return {}
    init_db()
    placeholders = ",".join("?" * len(tickers))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, payload_json, fetched_at
            FROM pead2_cache
            WHERE ticker IN ({placeholders})
            """,
            tickers,
        ).fetchall()
    out: dict[str, dict] = {}
    for row in rows:
        if not _is_fresh(row["fetched_at"], max_hours):
            continue
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            out[str(row["ticker"]).upper()] = payload
    return out


def load_all_pead2_cache_payloads(*, max_hours: int = 999999) -> list[dict]:
    """All fresh PEAD2 cache payloads (for universe scoring / demo)."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT ticker, payload_json, fetched_at FROM pead2_cache"
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        if not _is_fresh(row["fetched_at"], max_hours):
            continue
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload.setdefault("ticker", str(row["ticker"]).strip().upper())
        out.append(payload)
    return out


def _stock_note_row_to_dict(row: sqlite3.Row) -> dict:
    triggers: list[str] = []
    raw = row["triggers_json"]
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                triggers = [str(t).strip() for t in parsed if str(t).strip()]
        except (TypeError, json.JSONDecodeError):
            pass
    return {
        "business": row["business"] or "",
        "market_position": row["market_position"] or "",
        "triggers": triggers,
        "source": row["source"] or "",
        "updated_at": row["updated_at"],
    }


def upsert_stock_note(
    ticker: str,
    *,
    business: str | None = None,
    market_position: str | None = None,
    triggers: list[str] | None = None,
    source: str | None = None,
) -> None:
    init_db()
    key = safe_str(ticker).upper()
    if not key:
        return
    triggers_json = json.dumps(triggers or [])
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO stock_notes (
                ticker, business, market_position, triggers_json, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                business=excluded.business,
                market_position=excluded.market_position,
                triggers_json=excluded.triggers_json,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (
                key,
                (business or "").strip() or None,
                (market_position or "").strip() or None,
                triggers_json,
                (source or "").strip() or None,
                now,
            ),
        )


def load_stock_notes_map(tickers: list[str] | None = None) -> dict[str, dict]:
    """Ticker → note dict (business, market_position, triggers, source)."""
    init_db()
    with get_connection() as conn:
        if tickers:
            keys = [safe_str(t).upper() for t in tickers if safe_str(t)]
            if not keys:
                return {}
            placeholders = ",".join("?" * len(keys))
            rows = conn.execute(
                f"""
                SELECT ticker, business, market_position, triggers_json, source, updated_at
                FROM stock_notes WHERE ticker IN ({placeholders})
                """,
                keys,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT ticker, business, market_position, triggers_json, source, updated_at
                FROM stock_notes
                """
            ).fetchall()
    out: dict[str, dict] = {}
    for row in rows:
        note = _stock_note_row_to_dict(row)
        if note.get("business") or note.get("market_position") or note.get("triggers"):
            out[str(row["ticker"]).upper()] = note
    return out


def save_pead2_cache(rows: list[dict]) -> None:
    if not rows:
        return
    init_db()
    now = _utc_now()
    with get_connection() as conn:
        for row in rows:
            ticker = str(row.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            conn.execute(
                """
                INSERT INTO pead2_cache (ticker, market, payload_json, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    market=excluded.market,
                    payload_json=excluded.payload_json,
                    fetched_at=excluded.fetched_at
                """,
                (
                    ticker,
                    row.get("market"),
                    json.dumps(row, default=str),
                    now,
                ),
            )


def load_company_profile_cache(
    tickers: list[str],
    *,
    max_hours: int | None = None,
) -> dict[str, dict]:
    """Stored company website/about rows keyed by ticker (no expiry when max_hours is None)."""
    if not tickers:
        return {}
    init_db()
    keys = [str(t).strip().upper() for t in tickers if str(t).strip()]
    if not keys:
        return {}
    placeholders = ",".join("?" * len(keys))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, market, website, long_description, company_sector,
                   company_industry, headquarters, employees, source, fetched_at
            FROM company_profile_cache
            WHERE ticker IN ({placeholders})
            """,
            keys,
        ).fetchall()
    out: dict[str, dict] = {}
    for row in rows:
        if max_hours is not None and not _is_fresh(row["fetched_at"], max_hours):
            continue
        ticker = str(row["ticker"]).upper()
        out[ticker] = {
            "ticker": ticker,
            "market": row["market"],
            "website": row["website"],
            "long_description": row["long_description"],
            "company_sector": row["company_sector"],
            "company_industry": row["company_industry"],
            "headquarters": row["headquarters"],
            "employees": row["employees"],
            "source": row["source"],
            "fetched_at": row["fetched_at"],
        }
    return out


def load_company_profiles_from_db(tickers: list[str]) -> dict[str, dict]:
    """Load saved company profiles from SQLite (no time limit)."""
    return load_company_profile_cache(tickers, max_hours=None)


def save_company_profiles(rows: list[dict]) -> None:
    """Persist company profile rows to SQLite."""
    save_company_profile_cache(rows)


def save_company_profile_cache(rows: list[dict]) -> None:
    if not rows:
        return
    init_db()
    now = _utc_now()
    with get_connection() as conn:
        for row in rows:
            ticker = str(row.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            conn.execute(
                """
                INSERT INTO company_profile_cache (
                    ticker, market, website, long_description, company_sector,
                    company_industry, headquarters, employees, source, fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    market=excluded.market,
                    website=excluded.website,
                    long_description=excluded.long_description,
                    company_sector=excluded.company_sector,
                    company_industry=excluded.company_industry,
                    headquarters=excluded.headquarters,
                    employees=excluded.employees,
                    source=excluded.source,
                    fetched_at=excluded.fetched_at
                """,
                (
                    ticker,
                    row.get("market"),
                    row.get("website"),
                    row.get("long_description"),
                    row.get("company_sector"),
                    row.get("company_industry"),
                    row.get("headquarters"),
                    row.get("employees"),
                    row.get("source"),
                    now,
                ),
            )


def load_valuepickr_cache(*, max_hours: int) -> pd.DataFrame | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT payload_json, fetched_at FROM valuepickr_cache WHERE id = 1"
        ).fetchone()
    if row is None or not _is_fresh(row["fetched_at"], max_hours):
        return None
    try:
        data = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    return pd.DataFrame(data)


def save_valuepickr_cache(df: pd.DataFrame) -> None:
    if df.empty:
        return
    init_db()
    now = _utc_now()
    payload = df.to_dict(orient="records")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO valuepickr_cache (id, payload_json, fetched_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload_json=excluded.payload_json,
                fetched_at=excluded.fetched_at
            """,
            (json.dumps(payload, default=str), now),
        )


def load_superstar_portfolios_cache(
    *,
    max_hours: int,
    cache_version: int,
) -> dict[str, Any] | None:
    """Load cached superstar portfolios if fresh and version matches."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT payload_json, fetched_at, cache_version
            FROM superstar_portfolios_cache
            WHERE id = 1
            """
        ).fetchone()
    if row is None:
        return None
    if int(row["cache_version"] or 0) != int(cache_version):
        return None
    if not _is_fresh(row["fetched_at"], max_hours):
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("portfolios"), dict):
        return None
    return {
        "portfolios": payload["portfolios"],
        "fetched_at": row["fetched_at"],
        "fetched_at_display": payload.get("fetched_at_display") or row["fetched_at"][:16].replace("T", " "),
    }


def save_superstar_portfolios_cache(
    payload: dict[str, Any],
    *,
    cache_version: int,
) -> None:
    """Persist full superstar portfolio payload for 24h reuse."""
    if not payload or not isinstance(payload.get("portfolios"), dict):
        return
    init_db()
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO superstar_portfolios_cache (
                id, payload_json, fetched_at, cache_version
            )
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                payload_json=excluded.payload_json,
                fetched_at=excluded.fetched_at,
                cache_version=excluded.cache_version
            """,
            (json.dumps(payload, default=str), now, int(cache_version)),
        )


def load_intrinsic_value_cache(
    tickers: list[str],
    *,
    max_hours: int,
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    init_db()
    placeholders = ",".join("?" * len(tickers))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, market, name, price, market_cap_cr,
                   sales_growth_3y, roce_3y, pb, pe_ratio, forward_pe, fetched_at
            FROM intrinsic_value_cache
            WHERE ticker IN ({placeholders})
            """,
            tickers,
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    fresh = df["fetched_at"].apply(lambda ts: _is_fresh(ts, max_hours))
    return df[fresh].drop(columns=["fetched_at"], errors="ignore")


def save_intrinsic_value_cache(rows: list[dict]) -> None:
    if not rows:
        return
    init_db()
    now = _utc_now()
    payload = [
        (
            safe_str(r.get("ticker")).upper(),
            safe_str(r.get("market")) or None,
            safe_str(r.get("name")),
            r.get("price"),
            r.get("market_cap_cr"),
            r.get("sales_growth_3y"),
            r.get("roce_3y"),
            r.get("pb"),
            r.get("pe_ratio"),
            r.get("forward_pe"),
            now,
        )
        for r in rows
        if safe_str(r.get("ticker"))
    ]
    if not payload:
        return
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO intrinsic_value_cache (
                ticker, market, name, price, market_cap_cr,
                sales_growth_3y, roce_3y, pb, pe_ratio, forward_pe, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                market=excluded.market,
                name=excluded.name,
                price=excluded.price,
                market_cap_cr=excluded.market_cap_cr,
                sales_growth_3y=excluded.sales_growth_3y,
                roce_3y=excluded.roce_3y,
                pb=excluded.pb,
                pe_ratio=excluded.pe_ratio,
                forward_pe=excluded.forward_pe,
                fetched_at=excluded.fetched_at
            """,
            payload,
        )


HEADWIND_SCAN_CACHE_VERSION = 2


def load_headwind_scan_cache(
    *,
    max_hours: int,
    cache_version: int = HEADWIND_SCAN_CACHE_VERSION,
    scan_market: str = "NSE",
) -> dict[str, Any] | None:
    init_db()
    market = safe_str(scan_market).upper() or "NSE"
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT payload_json, fetched_at, cache_version
            FROM headwind_scan_cache_v2
            WHERE scan_market = ?
            """,
            (market,),
        ).fetchone()
    if row is None:
        return None
    if int(row["cache_version"] or 0) != int(cache_version):
        return None
    if not _is_fresh(row["fetched_at"], max_hours):
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    payload["fetched_at"] = row["fetched_at"]
    payload["fetched_at_display"] = payload.get("fetched_at_display") or row["fetched_at"][
        :16
    ].replace("T", " ")
    return payload


def save_headwind_scan_cache(
    payload: dict[str, Any],
    *,
    cache_version: int = HEADWIND_SCAN_CACHE_VERSION,
    scan_market: str = "NSE",
) -> None:
    if not payload:
        return
    init_db()
    market = safe_str(scan_market).upper() or "NSE"
    payload = {**payload, "scan_market": market}
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO headwind_scan_cache_v2 (
                scan_market, payload_json, fetched_at, cache_version
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(scan_market) DO UPDATE SET
                payload_json=excluded.payload_json,
                fetched_at=excluded.fetched_at,
                cache_version=excluded.cache_version
            """,
            (market, json.dumps(payload, default=str), now, int(cache_version)),
        )


def save_valuepickr_opportunities(df: pd.DataFrame) -> int:
    """Persist enriched ValuePickr threads for ticker lookup (PEAD, etc.)."""
    if df.empty:
        return 0
    init_db()
    now = _utc_now()
    rows: list[tuple] = []
    for _, row in df.iterrows():
        topic_id = int(row.get("topic_id") or 0)
        title = safe_str(row.get("title"))
        url = safe_str(row.get("url"))
        if not topic_id or not title or not url:
            continue
        ticker = safe_str(row.get("ticker")).upper() or None
        last = row.get("last_posted_at")
        created = row.get("created_at")
        rows.append(
            (
                topic_id,
                title,
                url,
                safe_str(row.get("slug")) or None,
                ticker,
                safe_str(row.get("company")) or None,
                safe_str(row.get("market")) or None,
                safe_str(row.get("sector")) or None,
                safe_str(row.get("subcategory")) or None,
                float(row["smart_rank"]) if pd.notna(row.get("smart_rank")) else None,
                int(row["rank"]) if pd.notna(row.get("rank")) else None,
                int(row.get("replies") or 0),
                int(row.get("views") or 0),
                int(row.get("likes") or 0),
                1 if bool(row.get("listed")) else 0,
                1 if bool(row.get("demerger")) else 0,
                1 if bool(row.get("spin_off")) else 0,
                1 if bool(row.get("corp_special_situation")) else 0,
                pd.Timestamp(last).isoformat() if pd.notna(last) else None,
                pd.Timestamp(created).isoformat() if pd.notna(created) else None,
                now,
            )
        )
    if not rows:
        return 0
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO valuepickr_opportunities (
                topic_id, title, url, slug, ticker, company, market, sector,
                subcategory, smart_rank, rank, replies, views, likes, listed,
                demerger, spin_off, special_situation, last_posted_at, created_at,
                fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                title=excluded.title,
                url=excluded.url,
                slug=excluded.slug,
                ticker=excluded.ticker,
                company=excluded.company,
                market=excluded.market,
                sector=excluded.sector,
                subcategory=excluded.subcategory,
                smart_rank=excluded.smart_rank,
                rank=excluded.rank,
                replies=excluded.replies,
                views=excluded.views,
                likes=excluded.likes,
                listed=excluded.listed,
                demerger=excluded.demerger,
                spin_off=excluded.spin_off,
                special_situation=excluded.special_situation,
                last_posted_at=excluded.last_posted_at,
                created_at=excluded.created_at,
                fetched_at=excluded.fetched_at
            """,
            rows,
        )
    return len(rows)


def load_valuepickr_opportunity_map(tickers: list[str]) -> dict[str, dict]:
    """Best ValuePickr thread per ticker (highest smart_rank)."""
    if not tickers:
        return {}
    init_db()
    uniq = list(dict.fromkeys(safe_str(t).upper() for t in tickers if safe_str(t)))
    if not uniq:
        return {}
    placeholders = ",".join("?" * len(uniq))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT topic_id, title, url, ticker, company, market, sector,
                   subcategory, smart_rank, rank, demerger, spin_off,
                   special_situation, last_posted_at
            FROM valuepickr_opportunities
            WHERE ticker IN ({placeholders})
            ORDER BY smart_rank DESC, last_posted_at DESC
            """,
            uniq,
        ).fetchall()
    out: dict[str, dict] = {}
    for row in rows:
        rec = dict(row)
        ticker = safe_str(rec.get("ticker")).upper()
        if ticker and ticker not in out:
            out[ticker] = rec
    return out


def save_valuepickr_analysis(row: dict) -> None:
    init_db()
    topic_id = int(row.get("topic_id") or 0)
    if not topic_id:
        return
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO valuepickr_analyses (
                topic_id, url, title, company, analysis_md,
                strengths_json, sentiment_json, summary_2025_json,
                posts_count, analyzed_through, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(topic_id) DO UPDATE SET
                url=excluded.url,
                title=excluded.title,
                company=excluded.company,
                analysis_md=excluded.analysis_md,
                strengths_json=excluded.strengths_json,
                sentiment_json=excluded.sentiment_json,
                summary_2025_json=excluded.summary_2025_json,
                posts_count=excluded.posts_count,
                analyzed_through=excluded.analyzed_through,
                fetched_at=excluded.fetched_at
            """,
            (
                topic_id,
                safe_str(row.get("url")),
                safe_str(row.get("title")),
                safe_str(row.get("company")),
                safe_str(row.get("analysis_md")),
                json.dumps(row.get("strengths") or [], default=str),
                json.dumps(row.get("monthly_sentiment") or [], default=str),
                json.dumps(row.get("summary_2025") or [], default=str),
                int(row.get("posts_count") or 0),
                safe_str(row.get("analyzed_through")),
                now,
            ),
        )


def load_valuepickr_analysis(topic_id: int, *, max_hours: int) -> dict | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT topic_id, url, title, company, analysis_md,
                   strengths_json, sentiment_json, summary_2025_json,
                   posts_count, analyzed_through, fetched_at
            FROM valuepickr_analyses
            WHERE topic_id = ?
            """,
            (int(topic_id),),
        ).fetchone()
    if row is None or not _is_fresh(row["fetched_at"], max_hours):
        return None
    try:
        strengths = json.loads(row["strengths_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        strengths = []
    try:
        monthly = json.loads(row["sentiment_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        monthly = []
    try:
        summary_2025 = json.loads(row["summary_2025_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        summary_2025 = []
    return {
        "topic_id": row["topic_id"],
        "url": row["url"],
        "title": row["title"],
        "company": row["company"],
        "analysis_md": row["analysis_md"],
        "strengths": strengths,
        "monthly_sentiment": monthly,
        "summary_2025": summary_2025,
        "posts_count": row["posts_count"],
        "analyzed_through": row["analyzed_through"],
        "fetched_at": row["fetched_at"],
    }


def load_valuepickr_opportunities_latest() -> pd.DataFrame:
    """Most recently fetched opportunities scan."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(fetched_at) AS ts FROM valuepickr_opportunities"
        ).fetchone()
        if row is None or not row["ts"]:
            return pd.DataFrame()
        rows = conn.execute(
            """
            SELECT topic_id, title, url, ticker, company, market, sector,
                   subcategory, smart_rank, rank, replies, views, likes,
                   listed, demerger, spin_off, special_situation,
                   last_posted_at, created_at, fetched_at
            FROM valuepickr_opportunities
            WHERE fetched_at = ?
            ORDER BY smart_rank DESC, last_posted_at DESC
            """,
            (row["ts"],),
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def save_superstar_holdings(
    investor: str,
    df: pd.DataFrame,
    *,
    fetched_at: str | None = None,
) -> int:
    """Replace persisted holdings for one superstar investor."""
    init_db()
    name = safe_str(investor)
    if not name:
        return 0
    now = fetched_at or _utc_now()
    with get_connection() as conn:
        conn.execute("DELETE FROM superstar_holdings WHERE investor = ?", (name,))
        if df is None or df.empty:
            return 0
        rows: list[tuple] = []
        for _, row in df.iterrows():
            symbol = safe_str(row.get("symbol")).upper()
            if not symbol:
                continue
            exchange = safe_str(row.get("exchange")).upper() or "NSE"
            rows.append(
                (
                    name,
                    symbol,
                    exchange,
                    safe_str(row.get("company_name")),
                    row.get("holding_percent"),
                    row.get("change_qtr"),
                    safe_str(row.get("change_type")),
                    row.get("holding_value_cr"),
                    row.get("price"),
                    now,
                )
            )
        if not rows:
            return 0
        conn.executemany(
            """
            INSERT INTO superstar_holdings (
                investor, symbol, exchange, company_name, holding_percent,
                change_qtr, change_type, holding_value_cr, price, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def load_superstar_holdings_map(tickers: list[str]) -> dict[str, list[dict]]:
    """All superstar investor rows per ticker symbol (latest fetch per investor)."""
    if not tickers:
        return {}
    init_db()
    uniq = list(dict.fromkeys(safe_str(t).upper() for t in tickers if safe_str(t)))
    if not uniq:
        return {}
    placeholders = ",".join("?" * len(uniq))
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT investor, symbol, exchange, company_name, holding_percent,
                   change_qtr, change_type, holding_value_cr, price, fetched_at
            FROM superstar_holdings
            WHERE symbol IN ({placeholders})
            ORDER BY investor COLLATE NOCASE
            """,
            uniq,
        ).fetchall()
    out: dict[str, list[dict]] = {}
    for row in rows:
        rec = dict(row)
        sym = safe_str(rec.get("symbol")).upper()
        if not sym:
            continue
        out.setdefault(sym, []).append(rec)
    return out


def superstar_holdings_db_stats() -> dict[str, int]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT COUNT(*) FROM superstar_holdings").fetchone()[0]
        investors = conn.execute(
            "SELECT COUNT(DISTINCT investor) FROM superstar_holdings"
        ).fetchone()[0]
        symbols = conn.execute(
            "SELECT COUNT(DISTINCT symbol) FROM superstar_holdings"
        ).fetchone()[0]
    return {"rows": int(rows), "investors": int(investors), "symbols": int(symbols)}


def save_strategy_tq_signals(df: pd.DataFrame) -> int:
    """Replace TQ breakout cache from a Strategy scan."""
    init_db()
    now = _utc_now()
    with get_connection() as conn:
        conn.execute("DELETE FROM strategy_tq_signals")
        if df is None or df.empty:
            return 0
        rows: list[tuple] = []
        for _, row in df.iterrows():
            ticker = safe_str(row.get("ticker")).upper()
            if not ticker:
                continue
            rows.append(
                (
                    ticker,
                    safe_str(row.get("market")) or None,
                    row.get("score"),
                    safe_str(row.get("crossover_type")),
                    row.get("crossover_score"),
                    safe_str(row.get("date")),
                    now,
                )
            )
        if not rows:
            return 0
        conn.executemany(
            """
            INSERT INTO strategy_tq_signals (
                ticker, market, score, crossover_type, crossover_score,
                signal_date, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def save_strategy_bb_signals(df: pd.DataFrame, *, timeframe: str) -> int:
    """Replace BB breakout cache for one timeframe from a Strategy scan."""
    init_db()
    tf = safe_str(timeframe) or "weekly"
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM strategy_bb_signals WHERE timeframe = ?",
            (tf,),
        )
        if df is None or df.empty:
            return 0
        rows: list[tuple] = []
        for _, row in df.iterrows():
            ticker = safe_str(row.get("ticker")).upper()
            if not ticker:
                continue
            rows.append(
                (
                    ticker,
                    safe_str(row.get("market")) or None,
                    safe_str(row.get("signal")) or "ABOVE_BAND",
                    safe_str(row.get("timeframe")) or tf,
                    row.get("price"),
                    row.get("upper_band"),
                    safe_str(row.get("date")),
                    now,
                )
            )
        if not rows:
            return 0
        conn.executemany(
            """
            INSERT INTO strategy_bb_signals (
                ticker, market, signal, timeframe, price, upper_band,
                signal_date, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def load_strategy_breakout_map(tickers: list[str]) -> dict[str, dict]:
    """TQ + BB breakout rows per ticker for PEAD cross-reference."""
    if not tickers:
        return {}
    init_db()
    uniq = list(dict.fromkeys(safe_str(t).upper() for t in tickers if safe_str(t)))
    if not uniq:
        return {}
    placeholders = ",".join("?" * len(uniq))
    out: dict[str, dict] = {t: {} for t in uniq}
    with get_connection() as conn:
        tq_rows = conn.execute(
            f"""
            SELECT ticker, market, score, crossover_type, crossover_score,
                   signal_date, fetched_at
            FROM strategy_tq_signals
            WHERE ticker IN ({placeholders})
            """,
            uniq,
        ).fetchall()
        bb_rows = conn.execute(
            f"""
            SELECT ticker, market, signal, timeframe, price, upper_band,
                   signal_date, fetched_at
            FROM strategy_bb_signals
            WHERE ticker IN ({placeholders})
            ORDER BY
                CASE signal WHEN 'NEW_BREAKOUT' THEN 0 ELSE 1 END,
                timeframe
            """,
            uniq,
        ).fetchall()
    for row in tq_rows:
        rec = dict(row)
        sym = safe_str(rec.get("ticker")).upper()
        if sym:
            out.setdefault(sym, {})["tq"] = rec
    for row in bb_rows:
        rec = dict(row)
        sym = safe_str(rec.get("ticker")).upper()
        if sym and "bb" not in out.get(sym, {}):
            out.setdefault(sym, {})["bb"] = rec
    return {k: v for k, v in out.items() if v}


def strategy_signals_db_stats() -> dict[str, int]:
    init_db()
    with get_connection() as conn:
        tq = conn.execute("SELECT COUNT(*) FROM strategy_tq_signals").fetchone()[0]
        bb = conn.execute("SELECT COUNT(*) FROM strategy_bb_signals").fetchone()[0]
    return {"tq": int(tq), "bb": int(bb)}


def strategy_signals_summary() -> dict[str, object]:
    """Counts + last fetch time for TQ / BB caches (Strategy → PEAD cross-ref)."""
    init_db()
    with get_connection() as conn:
        tq_row = conn.execute(
            "SELECT COUNT(*) AS n, MAX(fetched_at) AS ts FROM strategy_tq_signals"
        ).fetchone()
        bb_row = conn.execute(
            """
            SELECT COUNT(*) AS n, MAX(fetched_at) AS ts,
                   (SELECT timeframe FROM strategy_bb_signals
                    ORDER BY fetched_at DESC LIMIT 1) AS tf
            FROM strategy_bb_signals
            """
        ).fetchone()
    return {
        "tq_count": int(tq_row["n"] or 0),
        "tq_fetched_at": tq_row["ts"],
        "bb_count": int(bb_row["n"] or 0),
        "bb_fetched_at": bb_row["ts"],
        "bb_timeframe": safe_str(bb_row["tf"]) or "weekly",
    }


def load_business_groups() -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT g.id, g.name, g.token, g.created_at, g.updated_at,
                   COUNT(m.ticker) AS member_count
            FROM business_groups g
            LEFT JOIN business_group_members m ON m.group_id = g.id
            GROUP BY g.id
            ORDER BY g.name COLLATE NOCASE
            """
        ).fetchall()
    if not rows:
        return pd.DataFrame(
            columns=["id", "name", "token", "created_at", "updated_at", "member_count"]
        )
    return pd.DataFrame([dict(r) for r in rows])


def load_business_group_members(group_id: int) -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ticker, market, name, demerger, spin_off
            FROM business_group_members
            WHERE group_id = ?
            ORDER BY ticker
            """,
            (int(group_id),),
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["ticker", "market", "name", "demerger", "spin_off"])
    return pd.DataFrame([dict(r) for r in rows])


def load_all_business_group_members() -> pd.DataFrame:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ticker, market, name, demerger, spin_off
            FROM business_group_members
            ORDER BY ticker
            """
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["ticker", "market", "name", "demerger", "spin_off"])
    return pd.DataFrame([dict(r) for r in rows])


def save_business_group(
    name: str,
    members: list[dict],
    *,
    token: str | None = None,
) -> int:
    init_db()
    now = _utc_now()
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO business_groups (name, token, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, token, now, now),
        )
        group_id = int(cur.lastrowid)
        for member in members:
            conn.execute(
                """
                INSERT INTO business_group_members (group_id, ticker, market, name, demerger, spin_off)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    group_id,
                    str(member.get("ticker", "")).strip().upper(),
                    str(member.get("market", "NSE")).strip().upper() or "NSE",
                    member.get("name"),
                    1 if member.get("demerger") else 0,
                    1 if member.get("spin_off") else 0,
                ),
            )
        return group_id


def load_assigned_group_tickers() -> set[str]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT UPPER(ticker) AS ticker FROM business_group_members"
        ).fetchall()
    return {str(row["ticker"]).upper() for row in rows if row["ticker"]}


def load_ticker_group_map() -> dict[str, str]:
    """Map ticker -> saved group name."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT UPPER(m.ticker) AS ticker, g.name AS group_name
            FROM business_group_members m
            JOIN business_groups g ON g.id = m.group_id
            """
        ).fetchall()
    return {str(row["ticker"]).upper(): str(row["group_name"]) for row in rows if row["ticker"]}


def load_ticker_demerger_map() -> dict[str, bool]:
    """Map ticker -> True when flagged as a demerger spin-off within its group."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT UPPER(ticker) AS ticker, demerger
            FROM business_group_members
            """
        ).fetchall()
    return {
        str(row["ticker"]).upper(): bool(row["demerger"])
        for row in rows
        if row["ticker"] and bool(row["demerger"])
    }


def sync_group_demerger_tags(group_id: int, demerger_tickers: set[str]) -> int:
    """Set demerger=1 for listed tickers in a group; clear flag on other members."""
    init_db()
    want = {str(t).strip().upper() for t in demerger_tickers if str(t).strip()}
    updated = 0
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ticker, market, demerger
            FROM business_group_members
            WHERE group_id = ?
            """,
            (int(group_id),),
        ).fetchall()
        for row in rows:
            ticker = str(row["ticker"]).upper()
            market = str(row["market"] or "NSE").upper()
            flag = 1 if ticker in want else 0
            if int(row["demerger"] or 0) != flag:
                conn.execute(
                    """
                    UPDATE business_group_members
                    SET demerger = ?
                    WHERE group_id = ? AND UPPER(ticker) = ? AND UPPER(market) = ?
                    """,
                    (flag, int(group_id), ticker, market),
                )
                updated += 1
    return updated


def load_ticker_spin_off_map() -> dict[str, bool]:
    """Map ticker -> True when flagged as a subsidiary spin-off within its group."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT UPPER(ticker) AS ticker, spin_off
            FROM business_group_members
            """
        ).fetchall()
    return {
        str(row["ticker"]).upper(): bool(row["spin_off"])
        for row in rows
        if row["ticker"] and bool(row["spin_off"])
    }


def sync_group_spin_off_tags(group_id: int, spin_off_tickers: set[str]) -> int:
    """Set spin_off=1 for listed tickers in a group; clear flag on other members."""
    init_db()
    want = {str(t).strip().upper() for t in spin_off_tickers if str(t).strip()}
    updated = 0
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ticker, market, spin_off
            FROM business_group_members
            WHERE group_id = ?
            """,
            (int(group_id),),
        ).fetchall()
        for row in rows:
            ticker = str(row["ticker"]).upper()
            market = str(row["market"] or "NSE").upper()
            flag = 1 if ticker in want else 0
            if int(row["spin_off"] or 0) != flag:
                conn.execute(
                    """
                    UPDATE business_group_members
                    SET spin_off = ?
                    WHERE group_id = ? AND UPPER(ticker) = ? AND UPPER(market) = ?
                    """,
                    (flag, int(group_id), ticker, market),
                )
                updated += 1
    return updated


def add_business_group_members(group_id: int, members: list[dict]) -> int:
    init_db()
    now = _utc_now()
    added = 0
    with get_connection() as conn:
        conn.execute(
            "UPDATE business_groups SET updated_at = ? WHERE id = ?",
            (now, int(group_id)),
        )
        for member in members:
            ticker = str(member.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO business_group_members (group_id, ticker, market, name, demerger, spin_off)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(group_id),
                    ticker,
                    str(member.get("market", "NSE")).strip().upper() or "NSE",
                    member.get("name"),
                    1 if member.get("demerger") else 0,
                    1 if member.get("spin_off") else 0,
                ),
            )
            if cur.rowcount > 0:
                added += 1
    return added


def delete_business_group(group_id: int) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM business_group_members WHERE group_id = ?", (int(group_id),))
        conn.execute("DELETE FROM business_groups WHERE id = ?", (int(group_id),))


def remove_business_group_member(group_id: int, ticker: str, market: str | None = None) -> None:
    init_db()
    ticker = str(ticker).strip().upper()
    market = str(market or "NSE").strip().upper() or "NSE"
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM business_group_members
            WHERE group_id = ? AND UPPER(ticker) = ? AND UPPER(market) = ?
            """,
            (int(group_id), ticker, market),
        )
        conn.execute(
            "UPDATE business_groups SET updated_at = ? WHERE id = ?",
            (now, int(group_id)),
        )


def rename_business_group(group_id: int, name: str) -> None:
    init_db()
    clean = str(name).strip()
    if not clean:
        raise ValueError("Group name is required.")
    now = _utc_now()
    with get_connection() as conn:
        conn.execute(
            "UPDATE business_groups SET name = ?, updated_at = ? WHERE id = ?",
            (clean, now, int(group_id)),
        )


def clear_all_business_groups() -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM business_group_members")
        conn.execute("DELETE FROM business_groups")
