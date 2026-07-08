"""Disk cache for superstar portfolios (24h default)."""

from __future__ import annotations

from typing import Any

import pandas as pd

from stocks.core.database import (
    load_superstar_portfolios_cache,
    save_superstar_portfolios_cache,
)
from stocks.core.text_utils import safe_str

_FRAME_KEYS = ("all", "new_picks", "increased", "decreased", "unchanged")


def _serialize_portfolios(portfolios: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, data in portfolios.items():
        if not isinstance(data, dict):
            continue
        frames: dict[str, list[dict]] = {}
        for key in _FRAME_KEYS:
            df = data.get(key)
            if isinstance(df, pd.DataFrame) and not df.empty:
                frames[key] = df.to_dict(orient="records")
            else:
                frames[key] = []
        out[name] = {
            "count": int(data.get("count") or len(frames.get("all") or [])),
            "error": safe_str(data.get("error")),
            "frames": frames,
        }
    return out


def _deserialize_portfolios(data: dict[str, dict]) -> dict[str, dict]:
    portfolios: dict[str, dict] = {}
    for name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        frames = entry.get("frames") if isinstance(entry.get("frames"), dict) else {}
        rebuilt: dict[str, pd.DataFrame | str | int] = {}
        for key in _FRAME_KEYS:
            records = frames.get(key) or []
            rebuilt[key] = pd.DataFrame(records) if records else pd.DataFrame()
        rebuilt["count"] = int(entry.get("count") or len(rebuilt["all"]))
        rebuilt["error"] = safe_str(entry.get("error"))
        portfolios[name] = rebuilt
    return portfolios


def load_cached_superstar_portfolios(
    *,
    max_hours: int,
    cache_version: int,
) -> tuple[dict, str] | None:
    """Return (portfolios, fetched_at_display) when cache is fresh."""
    raw = load_superstar_portfolios_cache(
        max_hours=max_hours,
        cache_version=cache_version,
    )
    if not raw:
        return None
    portfolios = _deserialize_portfolios(raw["portfolios"])
    if not portfolios:
        return None
    return portfolios, safe_str(raw.get("fetched_at_display"))


def save_cached_superstar_portfolios(
    portfolios: dict,
    *,
    fetched_at_display: str,
    cache_version: int,
) -> None:
    payload: dict[str, Any] = {
        "portfolios": _serialize_portfolios(portfolios),
        "fetched_at_display": fetched_at_display,
    }
    save_superstar_portfolios_cache(payload, cache_version=cache_version)
