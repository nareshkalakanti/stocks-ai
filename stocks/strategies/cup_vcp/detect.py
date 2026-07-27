"""Cup & Handle and VCP (volatility contraction) pattern detectors."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from stocks.core.text_utils import safe_str


def _closes(data: pd.DataFrame) -> pd.Series:
    close = pd.to_numeric(data["Close"], errors="coerce")
    return close.dropna()


def _downsample_series(values: list[float], *, max_points: int = 120) -> list[dict[str, float]]:
    if not values:
        return []
    n = len(values)
    if n <= max_points:
        return [{"i": float(i), "v": float(values[i])} for i in range(n)]
    step = n / float(max_points)
    out: list[dict[str, float]] = []
    for k in range(max_points):
        idx = min(n - 1, int(k * step))
        out.append({"i": float(idx), "v": float(values[idx])})
    return out


def _bollinger_on_chart(
    values: list[float],
    chart_closes: list[dict[str, float]],
    *,
    period: int = 20,
    std_mult: float = 2.0,
) -> dict[str, Any] | None:
    """Bollinger bands aligned to downsampled chart close points."""
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n < period or not chart_closes:
        return None
    upper = np.full(n, np.nan)
    mid = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    for i in range(period - 1, n):
        window = arr[i + 1 - period : i + 1]
        m = float(np.mean(window))
        s = float(np.std(window))
        mid[i] = m
        upper[i] = m + std_mult * s
        lower[i] = m - std_mult * s

    def _pick(line: np.ndarray) -> list[dict[str, float]]:
        pts: list[dict[str, float]] = []
        for k, pt in enumerate(chart_closes):
            ri = int(min(n - 1, max(0, round(float(pt["i"])))))
            v = line[ri]
            if np.isnan(v):
                continue
            pts.append({"i": float(k), "v": float(v)})
        return pts

    up_pts = _pick(upper)
    mid_pts = _pick(mid)
    lo_pts = _pick(lower)
    if len(mid_pts) < 3:
        return None
    return {
        "period": period,
        "upper": up_pts,
        "mid": mid_pts,
        "lower": lo_pts,
    }


def _downsample_ohlc(
    frame: pd.DataFrame,
    *,
    max_points: int = 90,
) -> list[dict[str, float]]:
    """OHLC bars aligned to chart indices 0..len-1."""
    if frame.empty:
        return []
    o = pd.to_numeric(frame["Open"], errors="coerce").to_numpy(dtype=float)
    h = pd.to_numeric(frame["High"], errors="coerce").to_numpy(dtype=float)
    l = pd.to_numeric(frame["Low"], errors="coerce").to_numpy(dtype=float)
    c = pd.to_numeric(frame["Close"], errors="coerce").to_numpy(dtype=float)
    n = len(c)
    if n <= max_points:
        idxs = list(range(n))
    else:
        step = n / float(max_points)
        idxs = [min(n - 1, int(k * step)) for k in range(max_points)]
    out: list[dict[str, float]] = []
    for k, ri in enumerate(idxs):
        if ri < 0 or ri >= n or np.isnan(c[ri]):
            continue
        out.append(
            {
                "i": float(k),
                "o": round(float(o[ri]), 2),
                "h": round(float(h[ri]), 2),
                "l": round(float(l[ri]), 2),
                "c": round(float(c[ri]), 2),
            }
        )
    return out


def _tail_ohlc_frame(data: pd.DataFrame, max_bars: int) -> pd.DataFrame:
    close = _closes(data)
    if close.empty:
        return pd.DataFrame()
    tail = close.iloc[-max_bars:]
    idx = tail.index
    frame = pd.DataFrame(
        {
            "Open": pd.to_numeric(data.loc[idx, "Open"], errors="coerce"),
            "High": pd.to_numeric(data.loc[idx, "High"], errors="coerce"),
            "Low": pd.to_numeric(data.loc[idx, "Low"], errors="coerce"),
            "Close": pd.to_numeric(data.loc[idx, "Close"], errors="coerce"),
        }
    )
    if "Open" not in data.columns or frame["Open"].isna().all():
        frame["Open"] = frame["Close"]
    if "High" not in data.columns or frame["High"].isna().all():
        frame["High"] = frame["Close"]
    if "Low" not in data.columns or frame["Low"].isna().all():
        frame["Low"] = frame["Close"]
    return frame.dropna(subset=["Close", "High", "Low"]).reset_index(drop=True)


def _map_index(raw_i: int, n: int, chart_n: int) -> int:
    if n <= 1 or chart_n <= 1:
        return 0
    return int(round(raw_i * (chart_n - 1) / (n - 1)))


def detect_cup_and_handle(
    data: pd.DataFrame,
    *,
    min_bars: int = 60,
    max_bars: int = 160,
    min_cup_depth_pct: float = 12.0,
    max_cup_depth_pct: float = 50.0,
    max_handle_depth_frac: float = 0.45,
    rim_tolerance_pct: float = 8.0,
    near_breakout_pct: float = 5.0,
) -> dict[str, Any] | None:
    """
    Geometric Cup & Handle on daily closes.

    Requires a U-shaped cup (left rim → trough → right rim) and a shallow
    handle pullback. Prefers setups near / just through the rim.
    """
    close = _closes(data)
    if len(close) < min_bars:
        return None
    series = close.iloc[-max_bars:]
    vals = series.to_numpy(dtype=float)
    n = len(vals)
    if n < min_bars:
        return None

    # Split: cup uses most of the window; handle is the last segment.
    handle_len = max(5, min(25, n // 6))
    cup_end = n - handle_len
    if cup_end < 40:
        return None
    cup = vals[:cup_end]
    handle = vals[cup_end:]

    left_i = int(np.argmax(cup[: max(10, cup_end // 3)]))
    trough_i = left_i + int(np.argmin(cup[left_i:]))
    if trough_i <= left_i + 5:
        return None
    right_slice = cup[trough_i:]
    if len(right_slice) < 8:
        return None
    right_i = trough_i + int(np.argmax(right_slice))
    if right_i <= trough_i + 5 or right_i >= cup_end - 2:
        return None

    left_px = float(cup[left_i])
    trough_px = float(cup[trough_i])
    right_px = float(cup[right_i])
    if left_px <= 0 or trough_px <= 0 or right_px <= 0:
        return None

    depth_pct = (left_px - trough_px) / left_px * 100.0
    if depth_pct < min_cup_depth_pct or depth_pct > max_cup_depth_pct:
        return None

    rim = max(left_px, right_px)
    rim_gap_pct = abs(left_px - right_px) / rim * 100.0
    if rim_gap_pct > rim_tolerance_pct:
        return None
    # Right rim should recover most of the cup (not a V dump).
    recovery = (right_px - trough_px) / (left_px - trough_px)
    if recovery < 0.70:
        return None

    handle_high = float(np.max(handle))
    handle_low = float(np.min(handle))
    cup_depth = rim - trough_px
    if cup_depth <= 0:
        return None
    handle_depth = handle_high - handle_low
    if handle_depth > cup_depth * max_handle_depth_frac:
        return None
    # Handle should not break the cup mid / trough badly.
    if handle_low < trough_px + 0.25 * cup_depth:
        return None

    price = float(vals[-1])
    dist_to_rim_pct = (rim - price) / rim * 100.0
    broken = price >= rim * 0.998
    near = broken or dist_to_rim_pct <= near_breakout_pct
    if not near:
        return None

    # Score: deeper-but-not-crash cups, tight handle, near rim.
    score = 40.0
    score += min(25.0, depth_pct * 0.5)
    score += max(0.0, 15.0 - rim_gap_pct * 1.5)
    score += max(0.0, 15.0 - (handle_depth / cup_depth) * 30.0)
    if broken:
        score += 10.0
    else:
        score += max(0.0, 10.0 - dist_to_rim_pct)
    score = float(max(0.0, min(100.0, round(score, 1))))

    chart_closes = _downsample_series(vals.tolist())
    chart_n = len(chart_closes)
    ohlc_frame = _tail_ohlc_frame(data, max_bars)
    candles = _downsample_ohlc(ohlc_frame, max_points=chart_n)
    if len(candles) != chart_n and candles:
        chart_n = len(candles)
        chart_closes = [{"i": float(c["i"]), "v": float(c["c"])} for c in candles]
    bb = _bollinger_on_chart(vals.tolist(), chart_closes)
    left_c = _map_index(left_i, n, chart_n)
    trough_c = _map_index(trough_i, n, chart_n)
    right_c = _map_index(right_i, n, chart_n)
    handle0_c = _map_index(cup_end, n, chart_n)
    handle_low_i = cup_end + int(np.argmin(handle))
    handle_low_c = _map_index(handle_low_i, n, chart_n)
    zones = [
        {
            "kind": "cup",
            "i0": left_c,
            "i1": right_c,
            "label": "Cup",
        },
        {
            "kind": "handle",
            "i0": handle0_c,
            "i1": chart_n - 1,
            "label": "Handle",
        },
        {
            "kind": "rim",
            "level": round(rim, 2),
            "label": "Rim",
        },
    ]
    if broken:
        zones.append({"kind": "breakout", "i": chart_n - 1, "label": "Breakout"})

    return {
        "pattern": "Cup & Handle",
        "pattern_code": "CUP_HANDLE",
        "signal": "BREAKOUT" if broken else "NEAR_BREAKOUT",
        "score": score,
        "price": round(price, 2),
        "rim": round(rim, 2),
        "cup_depth_pct": round(depth_pct, 1),
        "handle_depth_pct": round(handle_depth / rim * 100.0, 1),
        "dist_to_rim_pct": round(dist_to_rim_pct, 2),
        "pattern_chart": {
            "closes": chart_closes,
            "candles": candles,
            "zones": zones,
            "title": "Cup & Handle",
            "shape": "cup_handle",
            "timeframe": "daily",
            "markings": [
                {
                    "kind": "buy" if broken else "setup",
                    "i": chart_n - 1,
                    "label": "Buy" if broken else "Near rim",
                }
            ],
            "landmarks": {
                "left": {"i": left_c, "v": round(left_px, 2), "label": "Left rim"},
                "trough": {"i": trough_c, "v": round(trough_px, 2), "label": "Trough"},
                "right": {"i": right_c, "v": round(right_px, 2), "label": "Right rim"},
                "handle_low": {
                    "i": handle_low_c,
                    "v": round(handle_low, 2),
                    "label": "Handle low",
                },
            },
            "rim": round(rim, 2),
            **({"bb": bb} if bb else {}),
        },
        "detail": (
            f"Cup depth {depth_pct:.0f}% · handle {handle_depth / rim * 100:.1f}% · "
            + ("broke rim" if broken else f"{dist_to_rim_pct:.1f}% under rim")
        ),
    }


def _local_extrema(values: np.ndarray, *, order: int = 3) -> tuple[list[int], list[int]]:
    """Return indices of local highs and lows with `order` bars on each side."""
    n = len(values)
    highs: list[int] = []
    lows: list[int] = []
    if n < order * 2 + 1:
        return highs, lows
    for i in range(order, n - order):
        window = values[i - order : i + order + 1]
        v = values[i]
        if v >= float(np.max(window)) and (not highs or i - highs[-1] >= order):
            highs.append(i)
        if v <= float(np.min(window)) and (not lows or i - lows[-1] >= order):
            lows.append(i)
    return highs, lows


def detect_vcp(
    data: pd.DataFrame,
    *,
    min_bars: int = 50,
    max_bars: int = 140,
    min_contractions: int = 2,
    max_contractions: int = 4,
    near_pivot_pct: float = 6.0,
) -> dict[str, Any] | None:
    """
    Volatility Contraction Pattern — successive smaller pullbacks into a pivot.
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
    n = len(frame)
    highs = frame["High"].to_numpy(dtype=float)
    lows = frame["Low"].to_numpy(dtype=float)
    closes = frame["Close"].to_numpy(dtype=float)
    volumes = (
        frame["Volume"].fillna(0).to_numpy(dtype=float)
        if "Volume" in frame.columns
        else np.ones(n)
    )

    # Pivot = highest high in the last third of the window.
    pivot_start = max(0, n - max(20, n // 3))
    pivot_i = pivot_start + int(np.argmax(highs[pivot_start:]))
    pivot = float(highs[pivot_i])
    if pivot <= 0 or pivot_i < 30:
        return None

    price = float(closes[-1])
    dist_pct = (pivot - price) / pivot * 100.0
    broken = price >= pivot * 0.998
    if not (broken or dist_pct <= near_pivot_pct):
        return None

    # Swing pullbacks left of the pivot: high → following low.
    swing_highs, swing_lows = _local_extrema(closes[: pivot_i + 1], order=3)
    if pivot_i not in swing_highs:
        swing_highs.append(pivot_i)
        swing_highs = sorted(set(swing_highs))

    contractions: list[dict[str, Any]] = []
    for hi_i in reversed(swing_highs):
        if hi_i >= pivot_i and hi_i != pivot_i:
            continue
        if hi_i > pivot_i:
            continue
        # Low after this high, before the next high (or pivot).
        next_highs = [h for h in swing_highs if h > hi_i]
        right = next_highs[0] if next_highs else pivot_i
        candidate_lows = [lo for lo in swing_lows if hi_i < lo <= right]
        if not candidate_lows:
            # Fall back to argmin in the segment.
            if right - hi_i < 4:
                continue
            lo_i = hi_i + 1 + int(np.argmin(lows[hi_i + 1 : right + 1]))
        else:
            lo_i = min(candidate_lows, key=lambda i: lows[i])
        hi = float(highs[hi_i])
        lo = float(lows[lo_i])
        if hi <= 0 or lo <= 0 or lo_i <= hi_i:
            continue
        pct = (hi - lo) / hi * 100.0
        if pct < 3.0:
            continue
        avg_vol = float(np.nanmean(volumes[hi_i : lo_i + 1]))
        contractions.append(
            {
                "i0": hi_i,
                "i1": lo_i,
                "pct": round(pct, 1),
                "avg_vol": avg_vol,
            }
        )
        if len(contractions) >= max_contractions:
            break

    contractions = list(reversed(contractions))
    if len(contractions) < min_contractions:
        return None

    # Keep a trailing shrinking sequence (each pullback tighter than prior).
    kept: list[dict[str, Any]] = [contractions[0]]
    for c in contractions[1:]:
        if c["pct"] < kept[-1]["pct"] * 0.88:
            kept.append(c)
        else:
            # Restart from this contraction if it could head a new sequence.
            kept = [c]
    if len(kept) < min_contractions:
        return None
    contractions = kept[-max_contractions:]
    pcts = [c["pct"] for c in contractions]
    if pcts[0] < 8.0 or pcts[-1] > pcts[0] * 0.75:
        return None

    vol_ok = True
    if len(contractions) >= 2:
        v0 = contractions[0]["avg_vol"]
        v1 = contractions[-1]["avg_vol"]
        vol_ok = not (v0 > 0 and v1 > v0 * 1.35)

    score = 45.0
    score += min(20.0, len(contractions) * 6.0)
    score += max(0.0, 15.0 - pcts[-1])
    if vol_ok:
        score += 8.0
    if broken:
        score += 10.0
    else:
        score += max(0.0, 10.0 - dist_pct)
    score = float(max(0.0, min(100.0, round(score, 1))))

    chart_closes = _downsample_series(closes.tolist())
    chart_n = len(chart_closes)
    zones = [
        {
            "kind": "contraction",
            "i0": _map_index(int(c["i0"]), n, chart_n),
            "i1": _map_index(int(c["i1"]), n, chart_n),
            "pct": c["pct"],
            "label": f'{c["pct"]}%',
        }
        for c in contractions
    ]
    zones.append({"kind": "pivot", "level": round(pivot, 2), "label": "Pivot"})
    if broken:
        zones.append({"kind": "breakout", "i": chart_n - 1, "label": "Breakout"})

    return {
        "pattern": "VCP",
        "pattern_code": "VCP",
        "signal": "BREAKOUT" if broken else "NEAR_BREAKOUT",
        "score": score,
        "price": round(price, 2),
        "pivot": round(pivot, 2),
        "contractions": len(contractions),
        "contraction_pcts": pcts,
        "dist_to_pivot_pct": round(dist_pct, 2),
        "volume_dryup": vol_ok,
        "pattern_chart": {
            "closes": chart_closes,
            "zones": zones,
            "title": "VCP",
        },
        "detail": (
            f"{len(contractions)} contractions {' → '.join(f'{p:.0f}%' for p in pcts)}"
            + (" · vol dry-up" if vol_ok else "")
            + (" · broke pivot" if broken else f" · {dist_pct:.1f}% under pivot")
        ),
    }


def detect_patterns(data: pd.DataFrame) -> list[dict[str, Any]]:
    """Return matching patterns (Cup & Handle and/or VCP), best first."""
    hits: list[dict[str, Any]] = []
    cup = detect_cup_and_handle(data)
    if cup:
        hits.append(cup)
    vcp = detect_vcp(data)
    if vcp:
        hits.append(vcp)
    hits.sort(key=lambda h: float(h.get("score") or 0), reverse=True)
    return hits


def analyze_ticker_patterns(
    ticker: str,
    market: str | None,
    data: pd.DataFrame,
    *,
    pattern_code: str | None = None,
) -> dict[str, Any] | None:
    """Pick the best pattern hit for one ticker (optionally one pattern type only)."""
    hits = detect_patterns(data)
    if pattern_code:
        code = safe_str(pattern_code).upper()
        hits = [h for h in hits if safe_str(h.get("pattern_code")).upper() == code]
    if not hits:
        return None
    best = hits[0]
    latest = data.iloc[-1]
    date = ""
    try:
        date = latest.name.strftime("%Y-%m-%d")
    except Exception:
        date = safe_str(latest.name)[:10]
    return {
        "ticker": safe_str(ticker).upper(),
        "market": safe_str(market) or None,
        "price": best.get("price"),
        "pattern": best.get("pattern"),
        "pattern_code": best.get("pattern_code"),
        "signal": best.get("signal"),
        "score": best.get("score"),
        "detail": best.get("detail"),
        "rim": best.get("rim"),
        "pivot": best.get("pivot"),
        "cup_depth_pct": best.get("cup_depth_pct"),
        "contractions": best.get("contractions"),
        "pattern_chart": best.get("pattern_chart"),
        "date": date,
        "timeframe": "daily",
        "patterns_found": [h.get("pattern_code") for h in hits],
    }
