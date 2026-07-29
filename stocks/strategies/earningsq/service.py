"""EarningsQ — NSE live results feed + PEAD/Yahoo metric enrich + scores."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stocks.core.config import HOLDINGS_PEAD_CACHE_HOURS, yfinance_worker_count
from stocks.core.database import load_pead2_cache
from stocks.core.json_utils import json_safe_obj
from stocks.core.text_utils import safe_str
from stocks.market.nse_earningsq import fetch_nse_earnings_announcements
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


def enrich_earningsq_row(
    event: dict,
    *,
    pead_blob: dict | None = None,
    with_returns: bool = True,
) -> dict:
    row = dict(event)
    lag0 = None
    if pead_blob:
        norm = _normalize_cache_blob(pead_blob)
        lag0 = (norm.get("lags") or {}).get("0")
        payload = expand_from_lag_row(lag0 if isinstance(lag0, dict) else None)
        if payload.get("quarters"):
            row["quarters"] = payload["quarters"]
    metrics = _metrics_from_pead_lag(lag0 if isinstance(lag0, dict) else None)
    for key, val in metrics.items():
        if val is not None:
            row[key] = val
        elif key not in row or row.get(key) is None:
            row[key] = None

    text = " ".join(
        safe_str(row.get(k))
        for k in ("desc", "attachment_text", "consolidated", "relating_to")
    )
    row["filing_type"] = filing_type_label(
        text, consolidated_flag=row.get("consolidated")
    )
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


def load_fixture_events() -> list[dict]:
    import json

    if not FIXTURES_PATH.is_file():
        return []
    try:
        data = json.loads(FIXTURES_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


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
    """
    events = fetch_nse_earnings_announcements(lookback_days=lookback_days)
    source = "nse"
    if not events and use_fixtures_if_empty:
        events = load_fixture_events()
        source = "fixture"

    if not events:
        return pd.DataFrame()

    tickers = [safe_str(e.get("ticker")).upper() for e in events if safe_str(e.get("ticker"))]
    pead_map = load_pead2_cache(tickers, max_hours=HOLDINGS_PEAD_CACHE_HOURS)

    enriched: list[dict] = []
    total = len(events)
    workers = yfinance_worker_count(total, max_workers or 6) if with_returns else 1

    def _one(ev: dict) -> dict:
        t = safe_str(ev.get("ticker")).upper()
        return enrich_earningsq_row(
            ev,
            pead_blob=pead_map.get(t),
            with_returns=with_returns,
        )

    if with_returns and total > 1:
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
    if df.empty:
        return df
    df["feed_source"] = source
    df["fetched_at"] = datetime.now(timezone.utc).isoformat()
    if min_surprise is not None and "surprise_score" in df.columns:
        s = pd.to_numeric(df["surprise_score"], errors="coerce")
        df = df[s.notna() & (s > float(min_surprise))].copy()
    sort_cols = [c for c in ("broadcast_at", "ticker") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False, True], kind="mergesort")
    return df.reset_index(drop=True)


__all__ = [
    "FIXTURES_PATH",
    "enrich_earningsq_row",
    "load_fixture_events",
    "metrics_from_quarters",
    "price_returns_around_broadcast",
    "run_earningsq_scan",
]
