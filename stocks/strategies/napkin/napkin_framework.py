"""Lotusdew Napkin Investing Framework — rate-adjusted PE hurdle vs revenue CAGR.

Educational research math only. Not investment advice.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from stocks.core.config import DATA_DIR
from stocks.core.text_utils import safe_str
from stocks.market.price_service import to_yfinance_symbol
from stocks.market.yfinance_utils import install_yfinance_noise_filters

NAPKIN_CACHE_DIR = DATA_DIR / "napkin"
PRICE_CACHE_DIR = NAPKIN_CACHE_DIR / "prices"
FUND_CACHE_DIR = NAPKIN_CACHE_DIR / "fundamentals"

PRICE_CACHE_TTL_SEC = 24 * 3600
FUND_CACHE_TTL_SEC = 7 * 24 * 3600
YF_PRICE_CHUNK = 100
FUND_MAX_WORKERS = 8

DEFAULT_BASE_RATE = 8.0
DEFAULT_CURRENT_RATE = 7.0
DEFAULT_BASE_TV_WEIGHT = 0.70
DEFAULT_MIN_PRICE = 20.0
DEFAULT_MIN_ADV = 1_000_000.0

NSE_FUND_CAP = 300
NSE_SME_FUND_CAP = 150


# ---------------------------------------------------------------------------
# Core napkin math
# ---------------------------------------------------------------------------


def rate_shift(base_rate: float, current_rate: float) -> float:
    """(base_rate - current_rate) / base_rate."""
    base = float(base_rate)
    if base == 0:
        return 0.0
    return (base - float(current_rate)) / base


def adj_tv_weight(
    base_rate: float,
    current_rate: float,
    base_tv_weight: float = DEFAULT_BASE_TV_WEIGHT,
) -> float:
    """Adjusted terminal-value weight, capped at 0.95."""
    shift = rate_shift(base_rate, current_rate)
    return float(min(float(base_tv_weight) + (shift * 0.60), 0.95))


def near_term_weight(
    base_rate: float,
    current_rate: float,
    base_tv_weight: float = DEFAULT_BASE_TV_WEIGHT,
) -> float:
    """1 - adj_tv_weight."""
    return 1.0 - adj_tv_weight(base_rate, current_rate, base_tv_weight)


def required_cagr(
    pe: float,
    *,
    base_rate: float = DEFAULT_BASE_RATE,
    current_rate: float = DEFAULT_CURRENT_RATE,
    base_tv_weight: float = DEFAULT_BASE_TV_WEIGHT,
) -> float:
    """
    Growth the market is pricing into the near-term PE slice over 5 years.

    target5 = PE * near_term_weight
    required_cagr = target5^(1/5) - 1  (0 if target5 <= 1)
    """
    if pe is None or (isinstance(pe, float) and np.isnan(pe)) or float(pe) <= 0:
        return float("nan")
    near_w = near_term_weight(base_rate, current_rate, base_tv_weight)
    target5 = float(pe) * near_w
    if target5 <= 1.0:
        return 0.0
    return float(target5 ** (1.0 / 5.0) - 1.0)


def napkin_score(expected_cagr: float, req_cagr: float) -> float:
    """expected_cagr - required_cagr (both as decimals)."""
    if pd.isna(expected_cagr) or pd.isna(req_cagr):
        return float("nan")
    return float(expected_cagr) - float(req_cagr)


def verdict(pe: float | None, score: float | None, expected_cagr: float | None) -> str:
    """Map score / PE / growth availability to a Napkin verdict."""
    if pe is None or (isinstance(pe, float) and (np.isnan(pe) or pe <= 0)):
        return "Unprofitable"
    if expected_cagr is None or (isinstance(expected_cagr, float) and np.isnan(expected_cagr)):
        return "Insufficient Data"
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "Insufficient Data"
    s = float(score)
    if s > 0.05:
        return "Napkin Buy"
    if -0.05 <= s <= 0.05:
        return "Fair Value"
    return "Overvalued"


def revenue_cagr_from_annual(revenues: list[float]) -> float:
    """
    3-year revenue CAGR from annual Total Revenue series (newest first or oldest first).

    Needs at least 4 annual points → 3-year span between first and fourth.
    """
    vals = [float(v) for v in revenues if v is not None and not pd.isna(v) and float(v) > 0]
    if len(vals) < 4:
        return float("nan")
    # income_stmt columns are newest-first typically
    newest, older = vals[0], vals[3]
    if older <= 0 or newest <= 0:
        return float("nan")
    return float((newest / older) ** (1.0 / 3.0) - 1.0)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _ensure_dirs() -> None:
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FUND_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _cache_fresh(path: Path, ttl_sec: int) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < ttl_sec


# ---------------------------------------------------------------------------
# Stage 1 — price screen
# ---------------------------------------------------------------------------


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def download_price_metrics(
    tickers: list[str],
    markets: dict[str, str | None] | None = None,
    *,
    period: str = "3mo",
) -> tuple[pd.DataFrame, str]:
    """
    Batch yf.download in chunks of 100; cache parquet 24h.

    Returns (df with ticker, last_price, adv_20d, yf_symbol), prices_timestamp.
    """
    install_yfinance_noise_filters()
    _ensure_dirs()
    markets = markets or {}
    keys = [safe_str(t).upper() for t in tickers if safe_str(t)]
    if not keys:
        return pd.DataFrame(columns=["ticker", "last_price", "adv_20d", "yf_symbol"]), ""

    cache_tag = f"px_{len(keys)}_{hash(tuple(keys)) & 0xFFFFFFFF:x}"
    cache_path = PRICE_CACHE_DIR / f"{cache_tag}.parquet"
    meta_path = PRICE_CACHE_DIR / f"{cache_tag}.meta.json"
    if _cache_fresh(cache_path, PRICE_CACHE_TTL_SEC):
        try:
            df = pd.read_parquet(cache_path)
            ts = ""
            if meta_path.exists():
                ts = json.loads(meta_path.read_text()).get("fetched_at", "")
            return df, ts
        except Exception:
            pass

    try:
        import yfinance as yf
    except Exception:
        return pd.DataFrame(columns=["ticker", "last_price", "adv_20d", "yf_symbol"]), ""

    yf_map = {t: to_yfinance_symbol(t, markets.get(t)) for t in keys}
    symbols = list(dict.fromkeys(yf_map.values()))
    close_by: dict[str, pd.Series] = {}
    traded_by: dict[str, pd.Series] = {}

    def _field(data: pd.DataFrame, symbol: str, field: str) -> pd.Series | None:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                lvl0 = data.columns.get_level_values(0)
                if symbol in set(lvl0) and field in data[symbol].columns:
                    return pd.to_numeric(data[symbol][field], errors="coerce")
                if field in set(lvl0) and symbol in set(data.columns.get_level_values(1)):
                    return pd.to_numeric(data[field][symbol], errors="coerce")
            elif field in data.columns and len(symbols) == 1:
                return pd.to_numeric(data[field], errors="coerce")
        except Exception:
            return None
        return None

    for chunk in _chunked(symbols, YF_PRICE_CHUNK):
        try:
            data = yf.download(
                tickers=chunk,
                period=period,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
        except Exception:
            continue
        if data is None or getattr(data, "empty", True):
            continue
        for sym in chunk:
            c = _field(data, sym, "Close")
            v = _field(data, sym, "Volume")
            if c is not None and not c.dropna().empty:
                close_by[sym] = c.dropna()
            if c is not None and v is not None:
                traded = (pd.to_numeric(c, errors="coerce") * pd.to_numeric(v, errors="coerce")).dropna()
                if not traded.empty:
                    traded_by[sym] = traded

    inv = {v: k for k, v in yf_map.items()}
    rows: list[dict] = []
    for sym, close in close_by.items():
        ticker = inv.get(sym, safe_str(sym).replace(".NS", "").replace(".BO", ""))
        last = float(close.iloc[-1])
        adv = float("nan")
        tr = traded_by.get(sym)
        if tr is not None and not tr.empty:
            adv = float(tr.tail(20).mean())
        rows.append(
            {
                "ticker": ticker,
                "last_price": last,
                "adv_20d": adv,
                "yf_symbol": sym,
            }
        )

    out = pd.DataFrame(rows)
    ts = _utc_now_iso()
    try:
        out.to_parquet(cache_path, index=False)
        meta_path.write_text(json.dumps({"fetched_at": ts}))
    except Exception:
        pass
    return out, ts


def price_screen(
    price_df: pd.DataFrame,
    *,
    min_price: float = DEFAULT_MIN_PRICE,
    min_adv: float = DEFAULT_MIN_ADV,
) -> pd.DataFrame:
    """Filter price >= min_price and ADV >= min_adv."""
    if price_df is None or price_df.empty:
        return pd.DataFrame()
    df = price_df.copy()
    px = pd.to_numeric(df["last_price"], errors="coerce")
    adv = pd.to_numeric(df["adv_20d"], errors="coerce")
    return df[(px >= float(min_price)) & (adv >= float(min_adv))].copy()


# ---------------------------------------------------------------------------
# Stage 2 — fundamentals
# ---------------------------------------------------------------------------


def _fund_cache_path(ticker: str) -> Path:
    return FUND_CACHE_DIR / f"{safe_str(ticker).upper()}.json"


def load_cached_fundamentals(ticker: str) -> dict | None:
    path = _fund_cache_path(ticker)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return None
    # Incomplete rows (no PE and no growth) expire fast so retries can fill gaps.
    pe = payload.get("pe")
    growth = payload.get("expected_cagr")
    incomplete = (pe is None or pe == "" or (isinstance(pe, float) and pe <= 0)) and (
        growth is None or growth == ""
    )
    ttl = 3600 if incomplete else FUND_CACHE_TTL_SEC
    if not _cache_fresh(path, ttl):
        return None
    return payload


def save_cached_fundamentals(ticker: str, payload: dict) -> None:
    _ensure_dirs()
    try:
        _fund_cache_path(ticker).write_text(json.dumps(payload))
    except Exception:
        pass


def _income_revenues(ticker_obj) -> list[float]:
    """Newest-first Total Revenue from annual income_stmt (up to 4)."""
    for attr in ("income_stmt", "financials"):
        try:
            stmt = getattr(ticker_obj, attr, None)
        except Exception:
            stmt = None
        if stmt is None or getattr(stmt, "empty", True):
            continue
        for label in ("Total Revenue", "Operating Revenue", "Revenue"):
            if label in stmt.index:
                series = pd.to_numeric(stmt.loc[label], errors="coerce").dropna()
                vals = [float(x) for x in series.tolist()[:4]]
                if len(vals) >= 4:
                    return vals
                if vals:
                    return vals
    return []


def _resolve_pe(info: dict) -> tuple[float | None, str]:
    """trailingPE → price/eps → forwardPE (last resort)."""
    pe_raw = info.get("trailingPE")
    if pe_raw is not None:
        try:
            pe = float(pe_raw)
            if pe > 0:
                return pe, "trailingPE"
        except (TypeError, ValueError):
            pass
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    eps = info.get("trailingEps")
    try:
        if price is not None and eps is not None and float(eps) > 0:
            pe = float(price) / float(eps)
            if pe > 0:
                return pe, "price/eps"
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    # Negative trailing EPS → try forward PE so loss-makers with growth still score.
    fwd = info.get("forwardPE")
    if fwd is not None:
        try:
            pe = float(fwd)
            if pe > 0:
                return pe, "forwardPE"
        except (TypeError, ValueError):
            pass
    return None, ""


def fetch_ticker_fundamentals(ticker: str, market: str | None = None) -> dict:
    """
    PE (trailing → price/eps → forward) + 4 annual revenue rows.

    Retries with exponential backoff. Never raises.
    Incomplete results are cached briefly so a later run can refill.
    """
    cached = load_cached_fundamentals(ticker)
    if cached is not None:
        return cached

    install_yfinance_noise_filters()
    symbol = to_yfinance_symbol(ticker, market)
    payload: dict = {
        "ticker": safe_str(ticker).upper(),
        "yf_symbol": symbol,
        "pe": None,
        "pe_source": "",
        "expected_cagr": None,
        "growth_source": "",
        "fetched_at": _utc_now_iso(),
        "error": None,
    }

    try:
        import yfinance as yf
    except Exception as exc:
        payload["error"] = f"yfinance import: {exc}"
        return payload

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            t = yf.Ticker(symbol)
            info = {}
            try:
                info = t.info or {}
            except Exception:
                info = {}
            pe, pe_src = _resolve_pe(info)

            revenues = _income_revenues(t)
            exp = revenue_cagr_from_annual(revenues)
            src = "income_stmt" if not pd.isna(exp) else ""
            if pd.isna(exp):
                rg = info.get("revenueGrowth")
                try:
                    if rg is not None:
                        exp = float(rg)
                        src = "info.revenueGrowth"
                except (TypeError, ValueError):
                    exp = float("nan")
                    src = ""

            payload["pe"] = pe
            payload["pe_source"] = pe_src
            payload["expected_cagr"] = None if pd.isna(exp) else float(exp)
            payload["growth_source"] = src if payload["expected_cagr"] is not None else ""
            payload["revenues"] = revenues
            payload["fetched_at"] = _utc_now_iso()
            save_cached_fundamentals(ticker, payload)
            return payload
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5 * (2**attempt))

    payload["error"] = str(last_exc) if last_exc else "fetch failed"
    save_cached_fundamentals(ticker, payload)
    return payload


def fundamentals_cap_for_list(list_label: str, n_survivors: int, *, force_full: bool) -> int:
    """Caps: <=100 → all; NSE SME → 150; NSE → 300; force_full → all."""
    if force_full or n_survivors <= 100:
        return n_survivors
    label = safe_str(list_label).upper()
    if label == "NSE SME":
        return min(NSE_SME_FUND_CAP, n_survivors)
    if label == "NSE":
        return min(NSE_FUND_CAP, n_survivors)
    return n_survivors


def fetch_fundamentals_pool(
    survivors: pd.DataFrame,
    *,
    list_label: str,
    force_full: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[pd.DataFrame, str]:
    """ThreadPool fundamentals on survivors (ADV-ranked caps for big lists)."""
    if survivors is None or survivors.empty:
        return pd.DataFrame(), ""

    ranked = survivors.sort_values("adv_20d", ascending=False, na_position="last")
    cap = fundamentals_cap_for_list(list_label, len(ranked), force_full=force_full)
    work = ranked.head(cap).copy()

    markets = {}
    if "market" in work.columns:
        markets = {
            safe_str(r["ticker"]).upper(): safe_str(r.get("market")) or None
            for _, r in work.iterrows()
        }

    rows: list[dict] = []
    total = len(work)
    done = 0
    newest_ts = ""

    with ThreadPoolExecutor(max_workers=FUND_MAX_WORKERS) as pool:
        futures = {
            pool.submit(
                fetch_ticker_fundamentals,
                safe_str(r["ticker"]).upper(),
                markets.get(safe_str(r["ticker"]).upper()),
            ): safe_str(r["ticker"]).upper()
            for _, r in work.iterrows()
        }
        for fut in as_completed(futures):
            done += 1
            if progress_callback:
                progress_callback(done, total)
            try:
                payload = fut.result()
            except Exception as exc:
                payload = {
                    "ticker": futures[fut],
                    "pe": None,
                    "expected_cagr": None,
                    "growth_source": "",
                    "error": str(exc),
                    "fetched_at": _utc_now_iso(),
                }
            rows.append(payload)
            ts = safe_str(payload.get("fetched_at"))
            if ts and ts > newest_ts:
                newest_ts = ts

    return pd.DataFrame(rows), newest_ts


# ---------------------------------------------------------------------------
# Score + pipeline
# ---------------------------------------------------------------------------


@dataclass
class NapkinParams:
    base_rate: float = DEFAULT_BASE_RATE
    current_rate: float = DEFAULT_CURRENT_RATE
    base_tv_weight: float = DEFAULT_BASE_TV_WEIGHT
    min_price: float = DEFAULT_MIN_PRICE
    min_adv: float = DEFAULT_MIN_ADV
    force_full: bool = False


@dataclass
class NapkinResult:
    universe: pd.DataFrame
    price_metrics: pd.DataFrame
    survivors: pd.DataFrame
    scored: pd.DataFrame
    in_list: int = 0
    passed_price: int = 0
    fundamentals_available: int = 0
    scored_n: int = 0
    adj_tv: float = 0.0
    near_w: float = 0.0
    prices_ts: str = ""
    fundamentals_ts: str = ""
    notes: list[str] = field(default_factory=list)


def score_napkin_frame(
    fund_df: pd.DataFrame,
    price_df: pd.DataFrame,
    universe: pd.DataFrame,
    params: NapkinParams,
) -> pd.DataFrame:
    """Join PE / expected CAGR with prices and apply napkin verdicts."""
    if fund_df is None or fund_df.empty:
        return pd.DataFrame()

    name_by = {}
    if universe is not None and not universe.empty and "ticker" in universe.columns:
        name_col = "name" if "name" in universe.columns else "ticker"
        name_by = {
            safe_str(r["ticker"]).upper(): r.get(name_col)
            for _, r in universe.iterrows()
        }

    px = price_df.set_index("ticker") if price_df is not None and not price_df.empty else None
    rows: list[dict] = []
    for _, f in fund_df.iterrows():
        ticker = safe_str(f.get("ticker")).upper()
        pe = pd.to_numeric(f.get("pe"), errors="coerce")
        pe_f = float(pe) if pe is not None and not pd.isna(pe) else float("nan")
        exp = pd.to_numeric(f.get("expected_cagr"), errors="coerce")
        exp_f = float(exp) if exp is not None and not pd.isna(exp) else float("nan")

        req = required_cagr(
            pe_f,
            base_rate=params.base_rate,
            current_rate=params.current_rate,
            base_tv_weight=params.base_tv_weight,
        )
        score = napkin_score(exp_f, req)
        verd = verdict(
            None if pd.isna(pe_f) else pe_f,
            None if pd.isna(score) else score,
            None if pd.isna(exp_f) else exp_f,
        )
        last_px = adv = float("nan")
        if px is not None and ticker in px.index:
            last_px = pd.to_numeric(px.loc[ticker].get("last_price"), errors="coerce")
            adv = pd.to_numeric(px.loc[ticker].get("adv_20d"), errors="coerce")

        rows.append(
            {
                "ticker": ticker,
                "name": name_by.get(ticker),
                "pe": None if pd.isna(pe_f) else round(pe_f, 2),
                "pe_source": safe_str(f.get("pe_source")),
                "required_cagr": None if pd.isna(req) else round(req, 4),
                "expected_cagr": None if pd.isna(exp_f) else round(exp_f, 4),
                "napkin_score": None if pd.isna(score) else round(score, 4),
                "verdict": verd,
                "growth_source": f.get("growth_source") or "",
                "last_price": last_px,
                "adv_20d": adv,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Sort score desc; NaN scores last
    out["_sort"] = pd.to_numeric(out["napkin_score"], errors="coerce")
    out = out.sort_values("_sort", ascending=False, na_position="last").drop(columns=["_sort"])
    return out.reset_index(drop=True)


def run_napkin_pipeline(
    universe: pd.DataFrame,
    list_label: str,
    params: NapkinParams,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
) -> NapkinResult:
    """
    Full pipeline: price screen → fundamentals (capped) → score.

    Saves partial results; never raises to the caller.
    """
    notes: list[str] = []
    uni = universe.copy() if universe is not None else pd.DataFrame()
    if not uni.empty and "ticker" in uni.columns:
        uni["ticker"] = uni["ticker"].map(lambda t: safe_str(t).upper())

    adj = adj_tv_weight(params.base_rate, params.current_rate, params.base_tv_weight)
    near = 1.0 - adj
    result = NapkinResult(
        universe=uni,
        price_metrics=pd.DataFrame(),
        survivors=pd.DataFrame(),
        scored=pd.DataFrame(),
        in_list=len(uni),
        adj_tv=adj,
        near_w=near,
    )

    if uni.empty:
        notes.append("Universe is empty.")
        result.notes = notes
        return result

    markets = {}
    if "market" in uni.columns:
        markets = {
            safe_str(r["ticker"]).upper(): safe_str(r.get("market")) or None
            for _, r in uni.iterrows()
        }

    try:
        price_df, px_ts = download_price_metrics(uni["ticker"].tolist(), markets)
    except Exception as exc:
        notes.append(f"Price download failed: {exc}")
        price_df, px_ts = pd.DataFrame(), ""

    result.price_metrics = price_df
    result.prices_ts = px_ts
    survivors = price_screen(price_df, min_price=params.min_price, min_adv=params.min_adv)
    # Attach market for yf symbol quality
    if not survivors.empty and "market" in uni.columns:
        survivors = survivors.merge(uni[["ticker", "market"]], on="ticker", how="left")
    result.survivors = survivors
    result.passed_price = len(survivors)
    notes.append(f"Price screen: {result.passed_price} / {result.in_list} passed.")

    if survivors.empty:
        notes.append("No tickers passed price / ADV screen.")
        result.notes = notes
        return result

    try:
        fund_df, fund_ts = fetch_fundamentals_pool(
            survivors,
            list_label=list_label,
            force_full=params.force_full,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        notes.append(f"Fundamentals fetch failed: {exc}")
        fund_df, fund_ts = pd.DataFrame(), ""

    result.fundamentals_ts = fund_ts
    if fund_df is not None and not fund_df.empty:
        result.fundamentals_available = int(
            pd.to_numeric(fund_df.get("pe"), errors="coerce").notna().sum()
        )
    try:
        scored = score_napkin_frame(fund_df, survivors, uni, params)
    except Exception as exc:
        notes.append(f"Scoring failed: {exc}")
        scored = fund_df if isinstance(fund_df, pd.DataFrame) else pd.DataFrame()

    result.scored = scored
    result.scored_n = len(scored) if scored is not None else 0
    result.notes = notes
    return result


__all__ = [
    "NapkinParams",
    "NapkinResult",
    "adj_tv_weight",
    "near_term_weight",
    "required_cagr",
    "napkin_score",
    "verdict",
    "revenue_cagr_from_annual",
    "run_napkin_pipeline",
    "rate_shift",
]
