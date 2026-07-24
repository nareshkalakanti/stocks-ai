"""Director network score — DIN-weighted peers, big↔small bridge, role, overload."""

from __future__ import annotations

import math
from typing import Any

from stocks.core.text_utils import safe_str

# Mcap bands (₹ Cr) for the bridge bonus.
LARGE_MCAP_CR = 5_000.0
SMALL_MCAP_CR = 1_000.0

# Cap label shortcuts (aligned with CAP_TIERS nano/micro/small/mid/large).
# Mid uses MC; Micro uses MIC so the two do not collide.
CAP_CODE_BANDS: tuple[tuple[float | None, float | None, str, str], ...] = (
    (0.0, 100.0, "NC", "Nano Cap (< 100 Cr)"),
    (100.0, 500.0, "MIC", "Micro Cap (100–500 Cr)"),
    (500.0, 5_000.0, "SC", "Small Cap (500–5,000 Cr)"),
    (5_000.0, 20_000.0, "MC", "Mid Cap (5,000–20,000 Cr)"),
    (20_000.0, None, "LC", "Large Cap (≥ 20,000 Cr)"),
)


def mcap_cap_code(market_cap_cr: float | None) -> str | None:
    """Return NC / MIC / SC / MC / LC from market cap in ₹ Cr, or None if unknown."""
    if market_cap_cr is None:
        return None
    try:
        cap = float(market_cap_cr)
    except (TypeError, ValueError):
        return None
    if cap != cap or cap <= 0:  # NaN / non-positive
        return None
    for lo, hi, code, _label in CAP_CODE_BANDS:
        if lo is not None and cap < lo:
            continue
        if hi is not None and cap >= hi:
            continue
        return code
    return None


def mcap_cap_label(market_cap_cr: float | None) -> str | None:
    """Human-readable cap band for tooltips."""
    code = mcap_cap_code(market_cap_cr)
    if not code:
        return None
    for _lo, _hi, band_code, label in CAP_CODE_BANDS:
        if band_code == code:
            return label
    return None

DIN_MATCH_WEIGHT = 1.0
NAME_MATCH_WEIGHT = 0.25

BRIDGE_BONUS = 15.0
HAS_LARGE_BONUS = 8.0
OVERLOAD_AFTER = 5
OVERLOAD_PENALTY_PER = 4.0

# Name-only person_ids with this many boards are treated as likely collisions
# (common names like "Sanjay Jain" merged across unrelated companies).
NAME_COLLISION_MIN_BOARDS = 5


def likely_name_collision(
    *,
    din_backed: bool,
    board_count: int,
    min_boards: int = NAME_COLLISION_MIN_BOARDS,
) -> bool:
    """True when identity is name-only and board count looks unreasonably high."""
    if din_backed:
        return False
    try:
        n = int(board_count)
    except (TypeError, ValueError):
        return False
    return n >= max(2, int(min_boards))


def is_din_person(person_id: str | None, din: str | None = None) -> bool:
    if safe_str(din).strip():
        return True
    pid = safe_str(person_id)
    return bool(pid) and not pid.startswith("n:")


def match_weight(*, person_id: str | None = None, din: str | None = None) -> float:
    return DIN_MATCH_WEIGHT if is_din_person(person_id, din) else NAME_MATCH_WEIGHT


def role_weight(designation: str | None = None, category: str | None = None) -> float:
    text = f"{safe_str(designation)} {safe_str(category)}".lower()
    if "chair" in text:
        return 1.25
    if any(x in text for x in ("managing", "whole-time", "whole time", "ceo", "md")):
        return 1.2
    if "independent" in text:
        return 1.15
    return 1.0


def mcap_log_weight(market_cap_cr: float | None) -> float:
    if market_cap_cr is None:
        return 0.5  # unknown size — small credit
    try:
        cap = float(market_cap_cr)
    except (TypeError, ValueError):
        return 0.5
    if cap <= 0 or math.isnan(cap):
        return 0.5
    return math.log10(1.0 + cap)


def seat_contribution(
    *,
    market_cap_cr: float | None,
    person_id: str | None = None,
    din: str | None = None,
    designation: str | None = None,
    category: str | None = None,
) -> float:
    return (
        mcap_log_weight(market_cap_cr)
        * match_weight(person_id=person_id, din=din)
        * role_weight(designation, category)
    )


def score_director_seats(
    seats: list[dict[str, Any]],
    *,
    person_id: str | None = None,
    din: str | None = None,
) -> dict[str, Any]:
    """
    Score one director from their board seats (each needs market_cap_cr when known).

    Returns ``dir_score`` 0–100 plus a transparent breakdown.
    """
    pid = safe_str(person_id) or safe_str((seats[0] if seats else {}).get("person_id"))
    din_key = safe_str(din) or safe_str((seats[0] if seats else {}).get("din"))
    din_backed = is_din_person(pid, din_key)

    raw = 0.0
    big_n = 0
    small_n = 0
    known_mcap_n = 0
    for seat in seats:
        mcap = seat.get("market_cap_cr")
        try:
            mcap_f = float(mcap) if mcap is not None and not (
                isinstance(mcap, float) and math.isnan(mcap)
            ) else None
        except (TypeError, ValueError):
            mcap_f = None
        if mcap_f is not None and mcap_f > 0:
            known_mcap_n += 1
            if mcap_f >= LARGE_MCAP_CR:
                big_n += 1
            if mcap_f <= SMALL_MCAP_CR:
                small_n += 1
        raw += seat_contribution(
            market_cap_cr=mcap_f,
            person_id=pid or seat.get("person_id"),
            din=din_key or seat.get("din"),
            designation=seat.get("designation"),
            category=seat.get("category"),
        )

    board_count = len({safe_str(s.get("ticker")).upper() for s in seats if safe_str(s.get("ticker"))})
    if board_count <= 0:
        board_count = len(seats)

    bridge = False
    bonus = 0.0
    if big_n >= 1 and small_n >= 1:
        bridge = True
        bonus += BRIDGE_BONUS
    elif big_n >= 1:
        bonus += HAS_LARGE_BONUS

    overload = max(0, board_count - OVERLOAD_AFTER) * OVERLOAD_PENALTY_PER

    # Soft map of raw peer strength into ~0–70, then bonuses/penalties.
    base = 70.0 * (1.0 - math.exp(-raw / 6.0))
    score = base + bonus - overload
    score = max(0.0, min(100.0, round(score, 1)))
    name_collision = likely_name_collision(
        din_backed=din_backed, board_count=board_count
    )

    return {
        "dir_score": score,
        "din_backed": din_backed,
        "name_collision": name_collision,
        "board_count": board_count,
        "big_n": big_n,
        "small_n": small_n,
        "bridge": bridge,
        "raw": round(raw, 3),
        "base": round(base, 1),
        "bonus": bonus,
        "overload_penalty": overload,
        "known_mcap_n": known_mcap_n,
        "match_weight": match_weight(person_id=pid, din=din_key),
    }
