"""ValuePickr Stock Opportunities — fetch, ticker match, smart rank."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from stocks.core.config import (
    VALUEPICKR_BASE_URL,
    VALUEPICKR_CACHE_HOURS,
    VALUEPICKR_MAX_PAGES,
)
from stocks.core.database import load_valuepickr_cache, save_valuepickr_cache, save_valuepickr_opportunities
from stocks.core.text_utils import safe_str
from stocks.listings.stocks_data import load_india_stocks
from stocks.shared.links import attach_research_links
from stocks.valuepickr.forum import VP_SUBCATEGORIES, fetch_category_topics

# Slugs for Discourse category JSON endpoints.
VP_CATEGORY_SLUGS: dict[int, str] = {
    11: "stock-opportunities",
    18: "not-so-hidden-gems",
    19: "untested-but-worth-a-good-look",
    34: "my-top-5-picks",
    36: "techno-funda-picks",
    37: "special-situations",
    68: "unlisted-shares",
    69: "sme-stocks",
}

_SUBCATEGORY_BOOST: dict[str, float] = {
    "Not-so-Hidden Gems": 8.0,
    "Special Situations": 6.0,
    "Techno-Funda Picks": 4.0,
    "Untested - but worth a good look": 2.0,
    "Unlisted Shares": -12.0,
}

_SUFFIXES = (
    " LTD",
    " LIMITED",
    " LTD.",
    " PVT",
    " PRIVATE",
    " INC",
    " INC.",
    " CORPORATION",
    " CORP",
    " COMPANY",
    " CO",
    " CO.",
)


def normalize_company_name(name: str) -> str:
    text = safe_str(name).upper()
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return re.sub(r"\s+", " ", text.replace("-", " ")).strip()


def extract_company_from_title(title: str) -> str:
    text = safe_str(title)
    for sep in (" - ", " : ", " – ", " | ", " — "):
        if sep in text:
            return text.split(sep)[0].strip()
    return text


def build_ticker_lookup(stocks: pd.DataFrame) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    if stocks is None or stocks.empty:
        return lookup
    for _, row in stocks.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        name = safe_str(row.get("name"))
        entry = {
            "ticker": ticker,
            "name": name,
            "market": safe_str(row.get("market")).upper() or "NSE",
            "sector": safe_str(row.get("sector")),
            "industry": safe_str(row.get("industry")),
            "sub_sector": safe_str(row.get("sub_sector")),
        }
        lookup[ticker] = entry
        if name:
            lookup[name.upper()] = entry
            norm = normalize_company_name(name)
            if norm:
                lookup[norm] = entry
                first = norm.split()[0] if norm.split() else ""
                if len(first) > 3:
                    lookup[first] = entry
    return lookup


def match_listed_stock(title: str, lookup: dict[str, dict]) -> dict | None:
    if not title or not lookup:
        return None
    extracted = extract_company_from_title(title)
    candidates = [
        extracted.upper(),
        normalize_company_name(extracted),
        title.upper(),
    ]
    for key in candidates:
        if key and key in lookup:
            return lookup[key]
    title_upper = title.upper()
    for key, entry in lookup.items():
        if len(key) < 4:
            continue
        if key in title_upper or title_upper in key:
            return entry
    return None


def _pct_rank(series: pd.Series, *, invert: bool = False) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() == 0:
        return pd.Series(0.0, index=series.index)
    ranked = s.rank(pct=True, method="average")
    if invert:
        ranked = 1.0 - ranked
    return ranked.fillna(0.0) * 100.0


def _days_since(ts: str | None) -> float:
    if not ts:
        return 9999.0
    try:
        dt = pd.Timestamp(ts)
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        now = pd.Timestamp.now(tz="UTC")
        return max(0.0, (now - dt).total_seconds() / 86400.0)
    except Exception:
        return 9999.0


def compute_smart_rank(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    work = df.copy()
    work["days_since_activity"] = work["last_posted_at"].map(_days_since)
    work["listed"] = work["ticker"].astype(str).str.strip().ne("")

    recency = _pct_rank(work["days_since_activity"], invert=True)
    engagement = _pct_rank(
        work["reply_count"].fillna(0)
        + work["views"].fillna(0) / 100.0
        + work["likes"].fillna(0) * 2.0
    )
    op_quality = _pct_rank(
        work.get("op_likes", pd.Series(0, index=work.index)).fillna(0)
        + work["likes"].fillna(0) / work["reply_count"].replace(0, np.nan).fillna(1)
    )
    freshness = _pct_rank(work["days_since_activity"], invert=True)

    base = (
        recency * 0.28
        + engagement * 0.32
        + op_quality * 0.18
        + freshness * 0.12
    )
    boost = work["subcategory"].map(lambda s: _SUBCATEGORY_BOOST.get(safe_str(s), 0.0)).fillna(0.0)
    listed_bonus = work["listed"].astype(float) * 6.0
    work["smart_rank"] = (base + boost + listed_bonus).clip(0, 100).round(1)

    work = work.sort_values(
        ["smart_rank", "last_posted_at"],
        ascending=[False, False],
        na_position="last",
    ).reset_index(drop=True)
    work["rank"] = range(1, len(work) + 1)
    return work


def fetch_all_opportunities(*, max_pages: int | None = None) -> pd.DataFrame:
    pages = VALUEPICKR_MAX_PAGES if max_pages is None else max_pages
    rows: list[dict] = []
    seen: set[int] = set()
    for cid, label in VP_SUBCATEGORIES.items():
        slug = VP_CATEGORY_SLUGS.get(cid, f"category-{cid}")
        for topic in fetch_category_topics(cid, slug=slug, max_pages=pages):
            tid = int(topic["topic_id"])
            if tid in seen:
                continue
            seen.add(tid)
            topic["subcategory"] = VP_SUBCATEGORIES.get(
                int(topic.get("category_id") or cid), label
            )
            rows.append(topic)
    return pd.DataFrame(rows)


def prepare_opportunities_table(
    stocks: pd.DataFrame | None = None,
    *,
    max_pages: int | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    if use_cache:
        cached = load_valuepickr_cache(max_hours=VALUEPICKR_CACHE_HOURS)
        if cached is not None and not cached.empty:
            return cached

    if stocks is None:
        stocks = load_india_stocks()
    lookup = build_ticker_lookup(stocks)

    raw = fetch_all_opportunities(max_pages=max_pages)
    if raw.empty:
        return raw

    records: list[dict] = []
    for _, row in raw.iterrows():
        title = safe_str(row.get("title"))
        match = match_listed_stock(title, lookup)
        rec = dict(row)
        rec["company"] = extract_company_from_title(title)
        rec["op_likes"] = 0
        rec["demerger"] = "demerger" in title.lower()
        rec["spin_off"] = "spin off" in title.lower() or "spin-off" in title.lower()
        rec["corp_special_situation"] = rec.get("subcategory") == "Special Situations"
        if match:
            rec["ticker"] = match["ticker"]
            rec["market"] = match["market"]
            rec["sector"] = match.get("sector")
            rec["industry"] = match.get("industry")
            rec["sub_sector"] = match.get("sub_sector")
        else:
            rec["ticker"] = None
            rec["market"] = None
            rec["sector"] = None
            rec["industry"] = None
            rec["sub_sector"] = None
        records.append(rec)

    df = compute_smart_rank(pd.DataFrame(records))
    if "reply_count" in df.columns and "replies" not in df.columns:
        df["replies"] = df["reply_count"]
    df["scan_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_valuepickr_cache(df)
    save_valuepickr_opportunities(df)
    return attach_research_links(df)


def latest_scan_label(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""
    if "scan_date" in df.columns and df["scan_date"].notna().any():
        return str(df["scan_date"].dropna().iloc[0])
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
