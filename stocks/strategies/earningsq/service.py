"""EarningsQ — NSE live results feed + PEAD/Yahoo metric enrich + scores."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stocks.core.config import HOLDINGS_PEAD_CACHE_HOURS, yfinance_worker_count
from stocks.core.database import load_market_cap_from_db, load_pead2_cache
from stocks.core.json_utils import json_safe_obj
from stocks.core.text_utils import safe_str
from stocks.listings.classification_service import load_classification_maps, lookup_classification
from stocks.market.nse_earningsq import fetch_nse_earnings_announcements
from stocks.market.nse_financials_xbrl import seasonal_yoy_metrics_from_nse
from stocks.strategies.earningsq.scores import (
    compute_return_score,
    compute_surprise_score,
    filing_type_label,
    market_hours_bucket,
)
from stocks.strategies.pead2.expand_data import expand_from_lag_row
from stocks.strategies.pead2.quarters import yoy_pair_from_panel
from stocks.strategies.pead2.service import _normalize_cache_blob
from stocks.strategies.whatif_returns.service import _fetch_returns_history

FIXTURES_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_live_rows.json"


def _pct_change(latest: float | None, prior: float | None) -> float | None:
    if latest is None or prior is None or prior == 0:
        return None
    return round((latest / prior - 1.0) * 100.0, 2)


def _panel_row_values(quarters: dict | None, label: str) -> tuple[list, list]:
    if not isinstance(quarters, dict):
        return [], []
    labels = quarters.get("labels") or []
    for row in quarters.get("rows") or []:
        if safe_str(row.get("label")) == label:
            return list(labels), list(row.get("values") or [])
    return list(labels), []


def metrics_from_quarters(quarters: dict | None) -> dict[str, float | None]:
    """Actual + YoY/QoQ (+ OPM) from a PEAD-style quarter panel."""
    out: dict[str, float | None] = {
        "rev_actual": None,
        "rev_yoy": None,
        "rev_qoq": None,
        "np_actual": None,
        "np_yoy": None,
        "np_qoq": None,
        "eps_actual": None,
        "eps_yoy": None,
        "eps_qoq": None,
        "opm_actual": None,
        "opm_yoy_pp": None,
        "opm_qoq_pp": None,
    }
    labels, sales = _panel_row_values(quarters, "Sales")
    _, op = _panel_row_values(quarters, "Operating Profit")
    _, np_vals = _panel_row_values(quarters, "Net Profit")
    _, eps_vals = _panel_row_values(quarters, "EPS in Rs")

    def _num(seq: list, idx: int) -> float | None:
        if idx < 0 or idx >= len(seq):
            return None
        try:
            v = float(seq[idx])
        except (TypeError, ValueError):
            return None
        return v

    if sales:
        out["rev_actual"] = _num(sales, -1)
        ly, py = yoy_pair_from_panel(sales, labels)
        out["rev_yoy"] = _pct_change(ly, py)
        if len(sales) >= 2:
            out["rev_qoq"] = _pct_change(_num(sales, -1), _num(sales, -2))
    if np_vals:
        out["np_actual"] = _num(np_vals, -1)
        ly, py = yoy_pair_from_panel(np_vals, labels)
        out["np_yoy"] = _pct_change(ly, py)
        if len(np_vals) >= 2:
            out["np_qoq"] = _pct_change(_num(np_vals, -1), _num(np_vals, -2))
    if eps_vals:
        out["eps_actual"] = _num(eps_vals, -1)
        ly, py = yoy_pair_from_panel(eps_vals, labels)
        out["eps_yoy"] = _pct_change(ly, py)
        if len(eps_vals) >= 2:
            out["eps_qoq"] = _pct_change(_num(eps_vals, -1), _num(eps_vals, -2))

    # OPM % and pp changes from Sales / Operating Profit columns.
    if sales and op and len(sales) == len(op) and sales:
        opm: list[float | None] = []
        for s, o in zip(sales, op):
            try:
                sf, of = float(s), float(o)
            except (TypeError, ValueError):
                opm.append(None)
                continue
            opm.append(round(of / sf * 100.0, 2) if sf else None)
        out["opm_actual"] = opm[-1] if opm else None
        if len(opm) >= 5 and opm[-1] is not None and opm[0] is not None:
            # oldest-first panel → YoY is last vs first of 5
            out["opm_yoy_pp"] = round(float(opm[-1]) - float(opm[0]), 2)
        if len(opm) >= 2 and opm[-1] is not None and opm[-2] is not None:
            out["opm_qoq_pp"] = round(float(opm[-1]) - float(opm[-2]), 2)
    return out


def _metrics_from_pead_lag(lag0: dict | None) -> dict[str, float | None]:
    base = metrics_from_quarters(
        lag0.get("quarters") if isinstance(lag0, dict) else None
    )
    if not isinstance(lag0, dict):
        return base
    # Prefer explicit PEAD growth fields when present.
    for src, dst in (
        ("sales_yoy", "rev_yoy"),
        ("sales_qoq", "rev_qoq"),
        ("np_yoy", "np_yoy"),
        ("np_qoq", "np_qoq"),
        ("eps_yoy", "eps_yoy"),
        ("eps_qoq", "eps_qoq"),
    ):
        val = lag0.get(src)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            try:
                base[dst] = round(float(val), 2)
            except (TypeError, ValueError):
                pass
    return base


def _close_on_or_after(closes: pd.Series, target: pd.Timestamp) -> float | None:
    after = closes.loc[closes.index >= target]
    if after.empty:
        before = closes.loc[closes.index <= target]
        if before.empty:
            return None
        return float(before.iloc[-1])
    return float(after.iloc[0])


def _close_on_or_before(closes: pd.Series, target: pd.Timestamp) -> float | None:
    before = closes.loc[closes.index <= target]
    if before.empty:
        after = closes.loc[closes.index >= target]
        if after.empty:
            return None
        return float(after.iloc[0])
    return float(before.iloc[-1])


def price_returns_around_broadcast(
    ticker: str,
    broadcast_at: str | pd.Timestamp,
    *,
    market: str = "NSE",
) -> dict[str, float | None]:
    """1D / 1W / QTD returns from broadcast date using Yahoo/BSE history."""
    out = {"ret_1d": None, "ret_1w": None, "ret_qtd": None, "price_now": None}
    try:
        ts = pd.Timestamp(broadcast_at).tz_localize(None).normalize()
    except (ValueError, TypeError):
        return out
    hist = _fetch_returns_history(ticker, market)
    if hist is None or hist.empty:
        return out
    closes = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if closes.empty:
        return out
    out["price_now"] = round(float(closes.iloc[-1]), 2)
    px0 = _close_on_or_before(closes, ts)
    if px0 is None or px0 <= 0:
        return out
    d1 = _close_on_or_after(closes, ts + pd.Timedelta(days=1))
    if d1 is None:
        d1 = float(closes.iloc[-1])
    w1 = _close_on_or_after(closes, ts + pd.Timedelta(days=7))
    if w1 is None:
        w1 = float(closes.iloc[-1])
    # QTD: from quarter start containing broadcast → now
    q_start = pd.Timestamp(year=ts.year, month=((ts.month - 1) // 3) * 3 + 1, day=1)
    q0 = _close_on_or_after(closes, q_start)
    now = float(closes.iloc[-1])
    out["ret_1d"] = round((d1 / px0 - 1.0) * 100.0, 2)
    out["ret_1w"] = round((w1 / px0 - 1.0) * 100.0, 2)
    if q0 and q0 > 0:
        out["ret_qtd"] = round((now / q0 - 1.0) * 100.0, 2)
    return out


def _is_num(val) -> bool:
    if val is None:
        return False
    try:
        if isinstance(val, float) and pd.isna(val):
            return False
        float(val)
        return True
    except (TypeError, ValueError):
        return False


def _has_growth_metrics(row: dict) -> bool:
    return any(_is_num(row.get(k)) for k in ("rev_yoy", "np_yoy", "eps_yoy", "rev_qoq", "np_qoq", "eps_qoq"))



def _apply_nse_xbrl_metrics(row: dict) -> dict:
    """Fill YoY growth from NSE Ind-AS XBRL when PEAD cache is empty."""
    ticker = safe_str(row.get("ticker")).upper()
    if not ticker or _has_growth_metrics(row):
        return row
    try:
        metrics = seasonal_yoy_metrics_from_nse(ticker, use_cache=True)
    except Exception:
        return row
    if not metrics:
        return row
    for src, dst in (
        ("rev_actual", "rev_actual"),
        ("np_actual", "np_actual"),
        ("eps_actual", "eps_actual"),
        ("sales_yoy", "rev_yoy"),
        ("np_yoy", "np_yoy"),
        ("eps_yoy", "eps_yoy"),
    ):
        val = metrics.get(src)
        if val is not None and not _is_num(row.get(dst)):
            row[dst] = val
    if not row.get("period_end") and metrics.get("period_end"):
        row["period_end"] = metrics.get("period_end")
    if metrics.get("filing_type") and not row.get("filing_type"):
        row["filing_type"] = metrics.get("filing_type")
    row["metrics_source"] = "nse_xbrl"
    return row


def _apply_yahoo_quarter_metrics(row: dict) -> dict:
    """Yahoo quarterly income fallback when PEAD + NSE XBRL miss."""
    ticker = safe_str(row.get("ticker")).upper()
    if not ticker or _has_growth_metrics(row):
        return row
    try:
        from stocks.strategies.pead2.expand_data import fetch_pead_expand_data

        payload = fetch_pead_expand_data(
            ticker,
            safe_str(row.get("market")) or "NSE",
            price=row.get("price_now"),
        )
    except Exception:
        return row
    if not payload or not payload.get("quarters"):
        return row
    metrics = metrics_from_quarters(payload.get("quarters"))
    filled = False
    for key, val in metrics.items():
        if val is not None and not _is_num(row.get(key)):
            row[key] = val
            filled = True
    if filled:
        row["quarters"] = payload.get("quarters")
        row["metrics_source"] = "yahoo"
    return row


def _rescore_row(row: dict) -> dict:
    row["surprise_score"] = compute_surprise_score(
        sales_yoy=row.get("rev_yoy"),
        sales_qoq=row.get("rev_qoq"),
        np_yoy=row.get("np_yoy"),
        np_qoq=row.get("np_qoq"),
        eps_yoy=row.get("eps_yoy"),
        eps_qoq=row.get("eps_qoq"),
        opm_yoy_pp=row.get("opm_yoy_pp"),
        opm_qoq_pp=row.get("opm_qoq_pp"),
    )
    row["return_score"] = compute_return_score(
        ret_1d=row.get("ret_1d"),
        ret_1w=row.get("ret_1w"),
        ret_qtd=row.get("ret_qtd"),
    )
    return row


def enrich_earningsq_row(
    event: dict,
    *,
    pead_blob: dict | None = None,
    with_returns: bool = True,
    fetch_nse_metrics: bool = True,
) -> dict:
    row = dict(event)
    lag0 = None
    if pead_blob:
        norm = _normalize_cache_blob(pead_blob)
        lag0 = (norm.get("lags") or {}).get("0")
        payload = expand_from_lag_row(lag0 if isinstance(lag0, dict) else None)
        if payload.get("quarters"):
            row["quarters"] = payload["quarters"]
            row["metrics_source"] = "pead_cache"
    metrics = _metrics_from_pead_lag(lag0 if isinstance(lag0, dict) else None)
    for key, val in metrics.items():
        if val is not None:
            row[key] = val
        elif key not in row or row.get(key) is None:
            row[key] = None

    if fetch_nse_metrics and not _has_growth_metrics(row):
        row = _apply_nse_xbrl_metrics(row)
    if not _has_growth_metrics(row):
        row = _apply_yahoo_quarter_metrics(row)

    text = " ".join(
        safe_str(row.get(k))
        for k in ("desc", "attachment_text", "consolidated", "relating_to")
    )
    row["filing_type"] = filing_type_label(
        text, consolidated_flag=row.get("consolidated")
    ) or row.get("filing_type")
    try:
        bts = pd.Timestamp(row.get("broadcast_at"))
    except (ValueError, TypeError):
        bts = None
    row["market_hours"] = market_hours_bucket(bts)

    if with_returns:
        rets = price_returns_around_broadcast(
            row.get("ticker") or "",
            row.get("broadcast_at") or "",
            market=safe_str(row.get("market")) or "NSE",
        )
        row.update(rets)

    return _rescore_row(row)


def rehydrate_earningsq_from_pead(
    df: pd.DataFrame,
    *,
    only_missing: bool = True,
) -> tuple[pd.DataFrame, int]:
    """
    Merge PEAD2 cache growth into an EarningsQ frame (fast, no live NSE/Yahoo).

    Returns ``(df, n_updated)``.
    """
    if df is None or df.empty or "ticker" not in df.columns:
        return (df if df is not None else pd.DataFrame()), 0

    work = df.copy()
    tickers = [
        safe_str(t).upper()
        for t in work["ticker"]
        if safe_str(t)
    ]
    pead_map = load_pead2_cache(tickers, max_hours=HOLDINGS_PEAD_CACHE_HOURS)
    if not pead_map:
        return work, 0

    keep_keys = (
        "rev_actual", "rev_yoy", "rev_qoq",
        "np_actual", "np_yoy", "np_qoq",
        "eps_actual", "eps_yoy", "eps_qoq",
        "opm_actual", "opm_yoy_pp", "opm_qoq_pp",
        "surprise_score", "return_score",
        "metrics_source", "filing_type",
    )
    for key in keep_keys:
        if key not in work.columns:
            work[key] = None

    updated = 0
    for idx, row in work.iterrows():
        t = safe_str(row.get("ticker")).upper()
        blob = pead_map.get(t)
        if not blob:
            continue
        if only_missing and _is_num(row.get("surprise_score")) and any(
            _is_num(row.get(k)) for k in ("rev_yoy", "np_yoy", "eps_yoy")
        ):
            continue
        raw = row.to_dict()
        # Keep existing returns/price; only refresh growth + surprise from PEAD.
        filled = enrich_earningsq_row(
            raw,
            pead_blob=blob,
            with_returns=False,
            fetch_nse_metrics=False,
        )
        if not _is_num(filled.get("surprise_score")) and not any(
            _is_num(filled.get(k)) for k in ("rev_yoy", "np_yoy", "eps_yoy")
        ):
            continue
        for key in keep_keys:
            if key in filled and filled.get(key) is not None:
                # Don't wipe an existing return_score with None from with_returns=False path
                if key == "return_score" and not _is_num(filled.get(key)):
                    continue
                work.at[idx, key] = filled.get(key)
        # Recompute return_score from existing ret_* if present.
        r1 = work.at[idx, "ret_1d"] if "ret_1d" in work.columns else None
        rw = work.at[idx, "ret_1w"] if "ret_1w" in work.columns else None
        rq = work.at[idx, "ret_qtd"] if "ret_qtd" in work.columns else None
        if _is_num(r1) or _is_num(rw) or _is_num(rq):
            work.at[idx, "return_score"] = compute_return_score(
                ret_1d=r1, ret_1w=rw, ret_qtd=rq
            )
        updated += 1

    stats = dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
    stats = dict(stats)
    stats["pead_rehydrated"] = updated
    if "surprise_score" in work.columns:
        stats["with_surprise"] = int(
            pd.to_numeric(work["surprise_score"], errors="coerce").notna().sum()
        )
    work.attrs["scan_stats"] = stats
    return work, updated


def metrics_missing_rate(df: pd.DataFrame) -> float:
    """Share of rows missing surprise or core YoY fields (0–1)."""
    if df is None or df.empty:
        return 1.0
    surprise = pd.to_numeric(df.get("surprise_score"), errors="coerce")
    np_y = pd.to_numeric(df.get("np_yoy"), errors="coerce")
    rev_y = pd.to_numeric(df.get("rev_yoy"), errors="coerce")
    miss = surprise.isna() & np_y.isna() & rev_y.isna()
    return float(miss.mean()) if len(miss) else 1.0


def backfill_earningsq_metrics(
    df: pd.DataFrame,
    *,
    with_returns: bool = True,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> pd.DataFrame:
    """
    Fill missing Surprise / Sales / Profit / EPS YoY (and optional returns)
    on an existing EarningsQ frame — PEAD → NSE XBRL → Yahoo.
    """
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    work = df.copy()
    stats = dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
    tickers = [
        safe_str(t).upper()
        for t in work.get("ticker", pd.Series(dtype=str))
        if safe_str(t)
    ]
    pead_map = load_pead2_cache(tickers, max_hours=HOLDINGS_PEAD_CACHE_HOURS) if tickers else {}

    need_mask = []
    for _, row in work.iterrows():
        has_growth = any(_is_num(row.get(k)) for k in ("rev_yoy", "np_yoy", "eps_yoy"))
        has_surprise = _is_num(row.get("surprise_score"))
        need_rets = with_returns and not _is_num(row.get("ret_1d"))
        need_mask.append(not has_growth or not has_surprise or need_rets)

    idxs = [i for i, need in enumerate(need_mask) if need]
    if not idxs:
        return work

    total = len(idxs)
    workers = yfinance_worker_count(total, max_workers or 8)

    def _one(i: int) -> tuple[int, dict]:
        raw = work.iloc[i].to_dict()
        t = safe_str(raw.get("ticker")).upper()
        filled = enrich_earningsq_row(
            raw,
            pead_blob=pead_map.get(t),
            with_returns=with_returns,
            fetch_nse_metrics=True,
        )
        return i, filled

    updated = 0
    # Scalar / JSON-safe fields only — avoid writing nested dicts into odd dtypes.
    keep_keys = (
        "rev_actual", "rev_yoy", "rev_qoq",
        "np_actual", "np_yoy", "np_qoq",
        "eps_actual", "eps_yoy", "eps_qoq",
        "opm_actual", "opm_yoy_pp", "opm_qoq_pp",
        "surprise_score", "return_score",
        "ret_1d", "ret_1w", "ret_qtd", "price_now",
        "metrics_source", "filing_type", "period_end", "market_hours",
    )
    for key in keep_keys:
        if key not in work.columns:
            work[key] = None

    results: dict[int, dict] = {}
    if total > 1:
        done = 0
        with ThreadPoolExecutor(max_workers=max(1, min(workers, total))) as pool:
            futs = {pool.submit(_one, i): i for i in idxs}
            for fut in as_completed(futs):
                done += 1
                try:
                    i, filled = fut.result()
                except Exception:
                    continue
                results[i] = filled
                updated += 1
                if progress_callback:
                    progress_callback(done, total, safe_str(filled.get("ticker")))
    else:
        i, filled = _one(idxs[0])
        results[i] = filled
        updated = 1
        if progress_callback:
            progress_callback(1, 1, safe_str(filled.get("ticker")))

    for i, filled in results.items():
        idx = work.index[i]
        for key in keep_keys:
            if key in filled:
                work.at[idx, key] = filled.get(key)

    stats = dict(stats)
    stats["metrics_backfilled"] = updated
    if "surprise_score" in work.columns:
        stats["with_surprise"] = int(
            pd.to_numeric(work["surprise_score"], errors="coerce").notna().sum()
        )
    work.attrs["scan_stats"] = stats
    return work


def load_fixture_events() -> list[dict]:
    import json

    if not FIXTURES_PATH.is_file():
        return []
    try:
        data = json.loads(FIXTURES_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def attach_sector_mcap(df: pd.DataFrame) -> pd.DataFrame:
    """Fill sector / market_cap_cr from classification maps + SQLite / PEAD cache."""
    if df is None or df.empty or "ticker" not in df.columns:
        return df
    out = df.copy()
    tickers = (
        out["ticker"].astype(str).str.strip().str.upper().replace("", pd.NA).dropna().unique().tolist()
    )
    if not tickers:
        return out

    mcap_map: dict[str, float] = {}
    try:
        # Prefer fresh cache; fall back to last-known so names like CENTENKA still show mcap.
        for allow_stale in (False, True):
            mcap_df = load_market_cap_from_db(tickers, allow_stale=allow_stale)
            if mcap_df is None or mcap_df.empty:
                continue
            for _, row in mcap_df.iterrows():
                t = safe_str(row.get("ticker")).upper()
                if t in mcap_map:
                    continue
                val = row.get("market_cap_cr")
                if t and val is not None and not (isinstance(val, float) and pd.isna(val)):
                    try:
                        mcap_map[t] = float(val)
                    except (TypeError, ValueError):
                        continue
    except Exception:
        pass

    missing = [t for t in tickers if t not in mcap_map]
    if missing:
        try:
            pead_map = load_pead2_cache(missing, max_hours=HOLDINGS_PEAD_CACHE_HOURS)
            for t, blob in (pead_map or {}).items():
                key = safe_str(t).upper()
                if not key or key in mcap_map or not isinstance(blob, dict):
                    continue
                raw = blob.get("market_cap_cr")
                if raw is None:
                    lag0 = (blob.get("lags") or {}).get("0")
                    if isinstance(lag0, dict):
                        snap = lag0.get("snapshot") if isinstance(lag0.get("snapshot"), dict) else {}
                        raw = snap.get("market_cap_cr") or lag0.get("market_cap_cr")
                try:
                    if raw is not None and not pd.isna(raw):
                        mcap_map[key] = float(raw)
                except (TypeError, ValueError):
                    continue
        except Exception:
            pass

    class_maps = None
    try:
        class_maps = load_classification_maps()
    except Exception:
        class_maps = None

    sectors: list[str] = []
    industries: list[str] = []
    mcaps: list[float | None] = []
    for _, row in out.iterrows():
        t = safe_str(row.get("ticker")).upper()
        sector = safe_str(row.get("sector"))
        industry = safe_str(row.get("industry"))
        if class_maps is not None and (not sector or not industry):
            s, i, _ss = lookup_classification(
                t, maps=class_maps, market=safe_str(row.get("market")) or "NSE"
            )
            sector = sector or s or i
            industry = industry or i
        sectors.append(sector or "")
        industries.append(industry or "")

        mcap = row.get("market_cap_cr")
        if mcap is None or (isinstance(mcap, float) and pd.isna(mcap)):
            mcap = mcap_map.get(t)
            if mcap is None:
                snap = row.get("snapshot")
                if isinstance(snap, dict):
                    raw = snap.get("market_cap_cr")
                    try:
                        mcap = float(raw) if raw is not None and not pd.isna(raw) else None
                    except (TypeError, ValueError):
                        mcap = None
        else:
            try:
                mcap = float(mcap)
            except (TypeError, ValueError):
                mcap = mcap_map.get(t)
        mcaps.append(mcap)

    out["sector"] = sectors
    out["industry"] = industries
    out["market_cap_cr"] = mcaps
    return out


def run_earningsq_scan(
    *,
    lookback_days: int = 7,
    min_surprise: float | None = 0.0,
    with_returns: bool = True,
    use_fixtures_if_empty: bool = True,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> pd.DataFrame:
    """
    NSE-only live earnings table.

    1) Pull financial-result announcements from NSE
    2) Enrich growth metrics from PEAD2 cache (long TTL)
    3) Optional post-result returns from Yahoo/BSE history
    4) Score surprise + return

    Scan coverage is stored on ``df.attrs["scan_stats"]``.
    """
    events, feed_stats = fetch_nse_earnings_announcements(lookback_days=lookback_days)
    source = "nse"
    if not events and use_fixtures_if_empty:
        events = load_fixture_events()
        source = "fixture"
        feed_stats = {
            "lookback_days": int(lookback_days),
            "nse_announcements_raw": 0,
            "result_prints": len(events),
            "unique_tickers": len(
                {safe_str(e.get("ticker")).upper() for e in events if safe_str(e.get("ticker"))}
            ),
        }

    nse_universe = 0
    try:
        from stocks.market.nse_equity_listings import fetch_nse_equity_listings

        listings = fetch_nse_equity_listings(force=False)
        if listings is not None and not listings.empty:
            nse_universe = int(listings["ticker"].nunique()) if "ticker" in listings.columns else len(listings)
    except Exception:
        nse_universe = 0

    scan_stats = {
        **feed_stats,
        "nse_equity_universe": nse_universe,
        "scored": 0,
        "feed_source": source,
    }

    if not events:
        empty = pd.DataFrame()
        empty.attrs["scan_stats"] = scan_stats
        return empty

    tickers = [safe_str(e.get("ticker")).upper() for e in events if safe_str(e.get("ticker"))]
    pead_map = load_pead2_cache(tickers, max_hours=HOLDINGS_PEAD_CACHE_HOURS)

    enriched: list[dict] = []
    total = len(events)
    # Parallel always — PEAD-miss path hits NSE XBRL per ticker.
    workers = yfinance_worker_count(total, max_workers or 8)

    def _one(ev: dict) -> dict:
        t = safe_str(ev.get("ticker")).upper()
        return enrich_earningsq_row(
            ev,
            pead_blob=pead_map.get(t),
            with_returns=with_returns,
        )

    if total > 1:
        done = 0
        with ThreadPoolExecutor(max_workers=max(1, min(workers, total))) as pool:
            futs = {pool.submit(_one, ev): ev for ev in events}
            for fut in as_completed(futs):
                done += 1
                ev = futs[fut]
                if progress_callback:
                    progress_callback(done, total, safe_str(ev.get("ticker")))
                try:
                    enriched.append(fut.result())
                except Exception:
                    continue
    else:
        for i, ev in enumerate(events, start=1):
            if progress_callback:
                progress_callback(i, total, safe_str(ev.get("ticker")))
            try:
                enriched.append(_one(ev))
            except Exception:
                continue

    df = pd.DataFrame(json_safe_obj(enriched))
    scan_stats["scored"] = len(df)
    if not df.empty and "metrics_source" in df.columns:
        scan_stats["xbrl_metrics"] = int((df["metrics_source"] == "nse_xbrl").sum())
        scan_stats["pead_metrics"] = int((df["metrics_source"] == "pead_cache").sum())
        scan_stats["with_surprise"] = int(
            pd.to_numeric(df.get("surprise_score"), errors="coerce").notna().sum()
        )
    if df.empty:
        df.attrs["scan_stats"] = scan_stats
        return df
    df = attach_sector_mcap(df)
    df["feed_source"] = source
    df["fetched_at"] = datetime.now(timezone.utc).isoformat()
    if min_surprise is not None and "surprise_score" in df.columns:
        s = pd.to_numeric(df["surprise_score"], errors="coerce")
        # Keep unscored prints (no PEAD/Yahoo metrics yet); only drop scored
        # rows that fail the floor.
        df = df[s.isna() | (s > float(min_surprise))].copy()
    sort_cols = [c for c in ("broadcast_at", "ticker") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False, True], kind="mergesort")
    out = df.reset_index(drop=True)
    out.attrs["scan_stats"] = scan_stats
    return out


__all__ = [
    "FIXTURES_PATH",
    "attach_sector_mcap",
    "backfill_earningsq_metrics",
    "enrich_earningsq_row",
    "load_fixture_events",
    "metrics_from_quarters",
    "metrics_missing_rate",
    "price_returns_around_broadcast",
    "rehydrate_earningsq_from_pead",
    "run_earningsq_scan",
]
