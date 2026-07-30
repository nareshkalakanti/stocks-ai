"""Positive Surprise Quant — NSE-only scan (Integrated Filing XBRL YoY)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from typing import Any

import pandas as pd

from stocks.core.config import yfinance_worker_count
from stocks.core.database import load_market_cap_from_db, load_metrics_from_db
from stocks.core.json_utils import json_safe_obj
from stocks.core.text_utils import safe_str
from stocks.listings.classification_service import load_classification_maps, lookup_classification
from stocks.market.nse_earningsq import fetch_nse_earnings_announcements
from stocks.market.nse_financials_xbrl import seasonal_yoy_metrics_from_nse
from stocks.strategies.positive_surprise.strategy import score_positive_surprise


def prepare_psq_universe(
    stocks: pd.DataFrame,
    *,
    min_mcap_cr: float | None = None,
) -> pd.DataFrame:
    """NSE equities only (PositiveQ is NSE-native)."""
    if stocks is None or stocks.empty:
        return pd.DataFrame()
    out = stocks.copy()
    if "market" in out.columns:
        m = out["market"].astype(str).str.upper()
        out = out[m.eq("NSE") | m.str.startswith("NSE")].copy()
    if min_mcap_cr is not None and "market_cap_cr" in out.columns:
        caps = pd.to_numeric(out["market_cap_cr"], errors="coerce")
        out = out[caps.isna() | (caps >= float(min_mcap_cr))].copy()
    if "ticker" in out.columns:
        out["ticker"] = out["ticker"].astype(str).str.strip().str.upper()
        out = out[out["ticker"].ne("")].drop_duplicates("ticker")
    return out.reset_index(drop=True)


def _attach_meta(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    tickers = out["ticker"].astype(str).str.upper().tolist()

    pe_map: dict[str, float] = {}
    try:
        metrics = load_metrics_from_db(tickers)
        if metrics is not None and not metrics.empty:
            for _, row in metrics.iterrows():
                t = safe_str(row.get("ticker")).upper()
                for col in ("forward_pe", "pe_ratio"):
                    val = row.get(col)
                    if t and val is not None and not pd.isna(val):
                        try:
                            pe_map[t] = float(val)
                            break
                        except (TypeError, ValueError):
                            pass
    except Exception:
        pass

    mcap_map: dict[str, float] = {}
    try:
        for allow_stale in (False, True):
            caps = load_market_cap_from_db(tickers, allow_stale=allow_stale)
            if caps is None or caps.empty:
                continue
            for _, row in caps.iterrows():
                t = safe_str(row.get("ticker")).upper()
                if t in mcap_map:
                    continue
                val = row.get("market_cap_cr")
                if t and val is not None and not pd.isna(val):
                    try:
                        mcap_map[t] = float(val)
                    except (TypeError, ValueError):
                        pass
    except Exception:
        pass

    class_maps = None
    try:
        class_maps = load_classification_maps()
    except Exception:
        class_maps = None

    sectors: list[str] = []
    industries: list[str] = []
    fps: list[float | None] = []
    mcaps: list[float | None] = []
    for _, row in out.iterrows():
        t = safe_str(row.get("ticker")).upper()
        sector = safe_str(row.get("sector"))
        industry = safe_str(row.get("industry"))
        if class_maps is not None and (not sector or not industry):
            s, i, _ss = lookup_classification(t, maps=class_maps, market="NSE")
            sector = sector or s or i
            industry = industry or i
        sectors.append(sector)
        industries.append(industry)
        fp = row.get("forward_pe")
        if fp is None or (isinstance(fp, float) and pd.isna(fp)):
            fp = pe_map.get(t)
        else:
            try:
                fp = float(fp)
            except (TypeError, ValueError):
                fp = pe_map.get(t)
        fps.append(fp)
        mc = row.get("market_cap_cr")
        if mc is None or (isinstance(mc, float) and pd.isna(mc)):
            mc = mcap_map.get(t)
        else:
            try:
                mc = float(mc)
            except (TypeError, ValueError):
                mc = mcap_map.get(t)
        mcaps.append(mc)

    out["sector"] = sectors
    out["industry"] = industries
    out["forward_pe"] = fps
    out["market_cap_cr"] = mcaps
    return out


def run_positive_surprise_scan(
    universe: pd.DataFrame,
    *,
    lookback_days: int = 90,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    min_mcap_cr: float | None = None,
) -> dict[str, Any]:
    """
    Independent Positive Surprise scan on NSE data only.

    1) NSE corporate announcements (financial results) in ``lookback_days``
    2) Intersect with filtered NSE universe
    3) Integrated Filing Ind-AS XBRL → same-quarter YoY (EPS / sales / NP)
    4) Score positive surprises (+ optional PEG from cached PE)
    """
    uni = prepare_psq_universe(universe, min_mcap_cr=min_mcap_cr)
    uni_tickers = set(uni["ticker"].tolist()) if not uni.empty and "ticker" in uni.columns else set()
    name_map: dict[str, str] = {}
    if not uni.empty and "ticker" in uni.columns:
        name_col = uni["name"] if "name" in uni.columns else uni["ticker"]
        name_map = {
            safe_str(t).upper(): safe_str(n)
            for t, n in zip(uni["ticker"], name_col, strict=False)
        }

    events, feed_stats = fetch_nse_earnings_announcements(lookback_days=lookback_days)
    event_tickers = [
        safe_str(e.get("ticker")).upper()
        for e in events
        if safe_str(e.get("ticker"))
    ]
    # Prefer intersection with universe; if universe empty, use announcement tickers.
    if uni_tickers:
        tickers = [t for t in dict.fromkeys(event_tickers) if t in uni_tickers]
    else:
        tickers = list(dict.fromkeys(event_tickers))

    scan_stats = {
        **feed_stats,
        "universe_nse": len(uni_tickers),
        "announcement_tickers": len(set(event_tickers)),
        "to_fetch": len(tickers),
        "xbrl_ok": 0,
        "feed_source": "nse",
    }

    if not tickers:
        empty = pd.DataFrame()
        return {
            "candidates": empty,
            "candidates_previous": empty,
            "hits": 0,
            "hits_previous": 0,
            "fetched": 0,
            "saved": 0,
            "cache_hits": 0,
            "scan_stats": scan_stats,
            "coverage": None,
        }

    workers = yfinance_worker_count(len(tickers), max_workers or 8)
    rows: list[dict] = []
    done = 0

    def _one(t: str) -> dict | None:
        try:
            metrics = seasonal_yoy_metrics_from_nse(t, use_cache=True)
        except Exception:
            return None
        if not metrics:
            return None
        if name_map.get(t):
            metrics["name"] = name_map[t] or metrics.get("name")
        return metrics

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(tickers)))) as pool:
        futs = {pool.submit(_one, t): t for t in tickers}
        for fut in as_completed(futs):
            done += 1
            if progress_callback:
                progress_callback(done, len(tickers))
            try:
                row = fut.result()
            except Exception:
                continue
            if row:
                rows.append(row)

    scan_stats["xbrl_ok"] = len(rows)
    raw = pd.DataFrame(json_safe_obj(rows))
    if raw.empty:
        empty = pd.DataFrame()
        return {
            "candidates": empty,
            "candidates_previous": empty,
            "hits": 0,
            "hits_previous": 0,
            "fetched": len(tickers),
            "saved": 0,
            "cache_hits": 0,
            "scan_stats": scan_stats,
            "coverage": None,
        }

    enriched = _attach_meta(raw)
    scored = score_positive_surprise(enriched)
    if not scored.empty:
        scored["has_tq"] = False
        scored["has_bb"] = False
        scored["feed_source"] = "nse_xbrl"

    return {
        "candidates": scored,
        "candidates_previous": pd.DataFrame(),
        "hits": len(scored),
        "hits_previous": 0,
        "fetched": len(tickers),
        "saved": len(rows),
        "cache_hits": 0,
        "scan_stats": scan_stats,
        "coverage": None,
    }


# Back-compat alias used by the page
def prepare_pead_universe(stocks: pd.DataFrame, *, cap_tier_id: str | None = None, **_: Any) -> tuple:
    """Deprecated alias — PositiveQ no longer uses PEAD universe prep."""
    from stocks.scans.scan_universe import cap_tier_min_mcap_cr

    min_mcap = cap_tier_min_mcap_cr(cap_tier_id) if cap_tier_id else None
    uni = prepare_psq_universe(stocks, min_mcap_cr=min_mcap)
    return uni, len(uni), 0


__all__ = [
    "prepare_pead_universe",
    "prepare_psq_universe",
    "run_positive_surprise_scan",
]
