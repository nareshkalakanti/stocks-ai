"""Shared scan-universe helpers."""

from __future__ import annotations

from stocks.scans.scan_playlists import is_holdings_playlist


def resolve_cap_tier_id(market: str, cap_tier_id: str) -> str:
    """Holdings scans never apply a market-cap tier or floor."""
    if is_holdings_playlist(market):
        return "all"
    return cap_tier_id or "all"


def cap_tier_min_mcap_cr(cap_tier_id: str) -> float | None:
    """Per-ticker minimum mcap when scanning; None = no floor (All caps / Holdings)."""
    tier_id = cap_tier_id if cap_tier_id not in ("", None) else "all"
    if tier_id == "all":
        return None
    from stocks.core.config import CAP_TIERS

    tier = next((t for t in CAP_TIERS if t["id"] == tier_id), None)
    if not tier:
        return None
    min_val = tier.get("min")
    if min_val is None:
        return None
    try:
        floor = float(min_val)
    except (TypeError, ValueError):
        return None
    return floor if floor > 0 else None
