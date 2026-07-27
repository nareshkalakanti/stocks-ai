"""Weekly base breakout detector for long consolidations."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.strategies.cup_vcp.detect import _downsample_series, _map_index


def _closes(data: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(data["Close"], errors="coerce")
    return close.dropna()


def detect_weekly_base_breakout(
    data: pd.DataFrame,
    *,
    min_bars: int = 30,
    max_bars: int = 90,
    near_breakout_pct: float = 5.0,
) -> dict[str, Any] | None:
    """
    Detect a long weekly consolidation/base near breakout.

    Heuristic:
    - 30-60 week base
    - moderate depth, not too loose
    - latest close near or above resistance
    - recent tightening vs earlier part of the base
    """
    close = _closes(data)
    if len(close) < min_bars:
        return None
    high = pd.to_numeric(data["High"], errors="coerce")
    low = pd.to_numeric(data["Low"], errors="coerce")
    vol = pd.to_numeric(data.get("Volume"), errors="coerce")
    frame = pd.DataFrame({"Close": close, "High": high, "Low": low, "Volume": vol}).dropna(
        subset=["Close", "High", "Low"]
    )
    if len(frame) < min_bars:
        return None
    frame = frame.iloc[-max_bars:]
    closes = frame["Close"].to_numpy(dtype=float)
    highs = frame["High"].to_numpy(dtype=float)
    lows = frame["Low"].to_numpy(dtype=float)
    vols = frame["Volume"].fillna(0).to_numpy(dtype=float) if "Volume" in frame.columns else np.zeros(len(frame))
    n = len(frame)

    best: dict[str, Any] | None = None
    for base_len in (60, 52, 45, 36, 30):
        if n < base_len:
            continue
        i0 = n - base_len
        seg_close = closes[i0:]
        seg_high = highs[i0:]
        seg_low = lows[i0:]
        resistance = float(np.max(seg_high))
        support = float(np.min(seg_low))
        if resistance <= 0 or support <= 0:
            continue
        depth_pct = (resistance - support) / resistance * 100.0
        if depth_pct < 8.0 or depth_pct > 35.0:
            continue

        latest = float(seg_close[-1])
        dist_pct = (resistance - latest) / resistance * 100.0
        broken = latest >= resistance * 0.995
        if not (broken or dist_pct <= near_breakout_pct):
            continue

        first_half = seg_close[: max(10, base_len // 2)]
        last_weeks = seg_close[-8:] if len(seg_close) >= 8 else seg_close[-6:]
        if len(last_weeks) < 4:
            continue
        early_range = (float(np.max(first_half)) - float(np.min(first_half))) / max(float(np.max(first_half)), 1.0) * 100.0
        late_range = (float(np.max(last_weeks)) - float(np.min(last_weeks))) / max(float(np.max(last_weeks)), 1.0) * 100.0
        if late_range > max(6.0, early_range * 0.7):
            continue

        ma_period = min(30, len(seg_close))
        ma_now = float(np.mean(seg_close[-ma_period:]))
        ma_prev = float(np.mean(seg_close[-(ma_period + 4):-4])) if len(seg_close) >= ma_period + 4 else ma_now
        trend_ok = latest >= ma_now and ma_now >= ma_prev
        if not trend_ok:
            continue

        vol_ok = True
        if len(vols[i0:]) >= 12 and np.nanmean(vols[i0:-2]) > 0:
            recent_vol = float(np.nanmean(vols[-2:]))
            base_vol = float(np.nanmean(vols[i0:-2]))
            vol_ok = recent_vol >= base_vol * 0.85
        else:
            recent_vol = 0.0
            base_vol = 0.0

        score = 45.0
        score += min(18.0, max(0.0, 18.0 - abs(depth_pct - 18.0)))
        score += min(16.0, base_len * 0.25)
        score += max(0.0, 10.0 - late_range)
        score += 10.0 if broken else max(0.0, 8.0 - dist_pct)
        if vol_ok:
            score += 6.0
        score = float(max(0.0, min(100.0, round(score, 1))))

        candidate = {
            "i0": i0,
            "i1": n - 1,
            "base_len": base_len,
            "resistance": resistance,
            "support": support,
            "depth_pct": round(depth_pct, 1),
            "late_range_pct": round(late_range, 1),
            "dist_pct": round(dist_pct, 2),
            "broken": broken,
            "vol_ok": vol_ok,
            "score": score,
            "recent_vol": recent_vol,
            "base_vol": base_vol,
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    if best is None:
        return None

    chart_closes = _downsample_series(closes.tolist())
    chart_n = len(chart_closes)
    zones: list[dict[str, Any]] = [
        {
            "kind": "base",
            "i0": _map_index(int(best["i0"]), n, chart_n),
            "i1": _map_index(int(best["i1"]), n, chart_n),
            "label": "Base",
        },
        {
            "kind": "pivot",
            "level": round(float(best["resistance"]), 2),
            "label": "Breakout",
        },
    ]
    if best["broken"]:
        zones.append({"kind": "breakout", "i": chart_n - 1, "label": "Breakout"})

    return {
        "pattern": "Weekly Base Breakout",
        "pattern_code": "BASE_BREAKOUT",
        "signal": "BREAKOUT" if best["broken"] else "NEAR_BREAKOUT",
        "score": best["score"],
        "price": round(float(closes[-1]), 2),
        "pivot": round(float(best["resistance"]), 2),
        "base_weeks": int(best["base_len"]),
        "base_depth_pct": best["depth_pct"],
        "late_range_pct": best["late_range_pct"],
        "dist_to_pivot_pct": best["dist_pct"],
        "volume_ok": bool(best["vol_ok"]),
        "pattern_chart": {
            "closes": chart_closes,
            "zones": zones,
            "title": "Weekly Base Breakout",
            "shape": "base_breakout",
            "pivot": round(float(best["resistance"]), 2),
        },
        "detail": (
            f"{best['base_len']}w base · depth {best['depth_pct']:.0f}% · "
            f"tight range {best['late_range_pct']:.1f}%"
            + (" · broke pivot" if best["broken"] else f" · {best['dist_pct']:.1f}% under pivot")
        ),
    }


def analyze_ticker_base_breakout(
    ticker: str,
    market: str | None,
    data: pd.DataFrame,
) -> dict[str, Any] | None:
    hit = detect_weekly_base_breakout(data)
    if not hit:
        return None
    latest = data.iloc[-1]
    date = ""
    try:
        date = latest.name.strftime("%Y-%m-%d")
    except Exception:
        date = safe_str(latest.name)[:10]
    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": hit.get("price"),
        "pattern": hit.get("pattern"),
        "pattern_code": hit.get("pattern_code"),
        "signal": hit.get("signal"),
        "score": hit.get("score"),
        "detail": hit.get("detail"),
        "pivot": hit.get("pivot"),
        "base_weeks": hit.get("base_weeks"),
        "base_depth_pct": hit.get("base_depth_pct"),
        "late_range_pct": hit.get("late_range_pct"),
        "dist_to_pivot_pct": hit.get("dist_to_pivot_pct"),
        "pattern_chart": hit.get("pattern_chart"),
        "date": date,
        "timeframe": "weekly",
    }
