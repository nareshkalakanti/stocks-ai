"""Business group and corporate-action tag lookup for scan reports."""

from __future__ import annotations

import html as html_mod
from functools import lru_cache

import pandas as pd

from stocks.core.text_utils import safe_str


@lru_cache(maxsize=1)
def business_group_map() -> dict[str, str]:
    from stocks.core.database import load_ticker_group_map

    return load_ticker_group_map()


@lru_cache(maxsize=1)
def demerger_map() -> dict[str, bool]:
    from stocks.core.database import load_ticker_demerger_map

    return load_ticker_demerger_map()


@lru_cache(maxsize=1)
def spin_off_map() -> dict[str, bool]:
    from stocks.core.database import load_ticker_spin_off_map

    return load_ticker_spin_off_map()


@lru_cache(maxsize=1)
def parents_ticker_set() -> frozenset[str]:
    from stocks.core.database import load_demerger_stocks_from_db

    df = load_demerger_stocks_from_db()
    if df.empty or "role" not in df.columns:
        return frozenset()
    parents = df[df["role"].astype(str) == "Parent"]
    return frozenset(safe_str(t).upper() for t in parents["ticker"] if safe_str(t))


@lru_cache(maxsize=1)
def spinoffs_ticker_set() -> frozenset[str]:
    from stocks.core.database import load_demerger_stocks_from_db

    df = load_demerger_stocks_from_db()
    if df.empty or "role" not in df.columns:
        return frozenset()
    spins = df[df["role"].astype(str) == "Spin-off"]
    return frozenset(safe_str(t).upper() for t in spins["ticker"] if safe_str(t))


@lru_cache(maxsize=1)
def ds_ticker_set() -> frozenset[str]:
    from stocks.core.database import load_demerger_stocks_from_db

    df = load_demerger_stocks_from_db()
    if df.empty:
        return frozenset()
    return frozenset(safe_str(t).upper() for t in df["ticker"] if safe_str(t))


@lru_cache(maxsize=1)
def holdings_ticker_set() -> frozenset[str]:
    from stocks.core.database import load_holdings_from_db

    df = load_holdings_from_db()
    if df.empty:
        return frozenset()
    return frozenset(safe_str(t).upper() for t in df["ticker"] if safe_str(t))


def clear_corp_tags_cache() -> None:
    business_group_map.cache_clear()
    demerger_map.cache_clear()
    parents_ticker_set.cache_clear()
    spinoffs_ticker_set.cache_clear()
    ds_ticker_set.cache_clear()
    holdings_ticker_set.cache_clear()


def business_group_for_ticker(ticker: str) -> str:
    return business_group_map().get(safe_str(ticker).upper(), "")


def demerger_for_ticker(ticker: str) -> bool:
    t = safe_str(ticker).upper()
    return bool(t) and t in parents_ticker_set()


def spin_off_for_ticker(ticker: str) -> bool:
    t = safe_str(ticker).upper()
    return bool(t) and t in spinoffs_ticker_set()


def is_holding_for_ticker(ticker: str) -> bool:
    t = safe_str(ticker).upper()
    return bool(t) and t in holdings_ticker_set()


def corp_tags_dict_for_ticker(ticker: str) -> dict[str, str | bool]:
    """Row fields for JSON reports: business_group, is_holding, demerger, spin_off."""
    t = safe_str(ticker).upper()
    if not t:
        return {}
    out: dict[str, str | bool] = {}
    bg = business_group_for_ticker(t)
    if bg:
        out["business_group"] = bg
    if is_holding_for_ticker(t):
        out["is_holding"] = True
    if demerger_for_ticker(t):
        out["demerger"] = True
    if spin_off_for_ticker(t):
        out["spin_off"] = True
    return out


def corp_tags_html(
    ticker: str,
    *,
    business_group: str | None = None,
    is_holding: bool | None = None,
    demerger: bool | None = None,
    spin_off: bool | None = None,
) -> str:
    t = safe_str(ticker).upper()
    bg = safe_str(business_group) or (business_group_for_ticker(t) if t else "")
    in_holdings = (
        is_holding
        if is_holding is not None
        else (is_holding_for_ticker(t) if t else False)
    )
    is_dem = demerger if demerger is not None else (demerger_for_ticker(t) if t else False)
    is_spin = spin_off if spin_off is not None else (spin_off_for_ticker(t) if t else False)
    parts: list[str] = []
    if bg:
        esc_bg = html_mod.escape(bg)
        parts.append(
            f'<div class="corp-tag corp-tag-bg" title="{esc_bg}">{esc_bg}</div>'
        )
    if in_holdings:
        parts.append(
            '<div class="corp-tag corp-tag-hold" title="In your Holdings portfolio">Holding</div>'
        )
    if is_dem:
        parts.append('<div class="corp-tag corp-tag-dem">Demerger</div>')
    if is_spin:
        parts.append('<div class="corp-tag corp-tag-spin">Spin off</div>')
    if not parts:
        return ""
    return f'<div class="corp-tags">{"".join(parts)}</div>'


def attach_business_groups(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ticker" not in df.columns:
        return df
    bg_map = business_group_map()
    if not bg_map:
        return df
    out = df.copy()
    out["business_group"] = out["ticker"].astype(str).str.upper().map(
        lambda t: bg_map.get(safe_str(t).upper(), "")
    )
    return out


def attach_corp_tags(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ticker" not in df.columns:
        return df
    out = df.copy()
    tickers = out["ticker"].astype(str).str.upper()
    bg_map = business_group_map()
    parents = parents_ticker_set()
    spinoffs = spinoffs_ticker_set()
    holdings = holdings_ticker_set()
    out["business_group"] = tickers.map(lambda t: bg_map.get(safe_str(t).upper(), ""))
    out["is_holding"] = tickers.map(lambda t: safe_str(t).upper() in holdings)
    out["demerger"] = tickers.map(lambda t: safe_str(t).upper() in parents)
    out["spin_off"] = tickers.map(lambda t: safe_str(t).upper() in spinoffs)
    return out
