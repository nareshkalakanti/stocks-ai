import pandas as pd
from huggingface_hub import hf_hub_download

from stocks.listings.classification_service import (
    classification_coverage,
    enrich_stocks_classification,
    sync_holdings_classification,
)
from stocks.core.config import INDIA_STOCKS_DATASET, get_hf_token
from stocks.core.database import (
    init_db,
    load_stocks_from_db,
    save_stocks_to_db,
    stocks_cache_fresh,
)
from stocks.scans.scan_playlists import insert_scan_playlist_markets, is_scan_playlist, scan_playlist_listings
from stocks.core.log_service import DATASET_ERROR, log_error
from stocks.core.text_utils import safe_str
from stocks.listings.sector_display import apply_display_sector_mapping
from stocks.listings.stock_overrides import apply_stock_overrides


def _overlay_holdings_metadata(stocks: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
    """Prefer SQLite holdings labels for portfolio tickers."""
    if stocks.empty or holdings.empty:
        return stocks
    out = stocks.copy()
    lookup = holdings.drop_duplicates("ticker").set_index(
        holdings["ticker"].astype(str).str.upper()
    )
    tickers = out["ticker"].astype(str).str.upper()
    for idx, ticker in tickers.items():
        if ticker not in lookup.index:
            continue
        row = lookup.loc[ticker]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        for col in ("name", "market", "sector", "industry", "sub_sector"):
            val = safe_str(row.get(col))
            if val:
                out.at[idx, col] = val
        sub = safe_str(row.get("sub_sector"))
        cur_ind = safe_str(out.at[idx, "industry"])
        if sub and (not cur_ind or cur_ind == safe_str(out.at[idx, "sector"])):
            out.at[idx, "industry"] = sub
    return out


def _sync_holdings_listings(stocks: pd.DataFrame) -> pd.DataFrame:
    """Ensure SQLite holdings tickers exist in the scan universe (e.g. EPACKPEB)."""
    try:
        from stocks.shared.portfolio import load_holdings
        from stocks.listings.listing_enrichment import ensure_tickers_in_universe

        holdings = load_holdings(seed_if_empty=False)
        if holdings.empty:
            return apply_display_sector_mapping(apply_stock_overrides(stocks))

        tickers = [
            str(t).upper()
            for t in holdings["ticker"]
            if str(t).strip()
        ]
        updated, _ = ensure_tickers_in_universe(stocks, tickers, persist=False)
        updated = _overlay_holdings_metadata(updated, holdings)
        updated = enrich_stocks_classification(updated)
        updated = _overlay_holdings_metadata(updated, holdings)
        updated = apply_display_sector_mapping(apply_stock_overrides(updated))
        save_stocks_to_db(updated)
        sync_holdings_classification()
        return updated
    except Exception:
        return apply_display_sector_mapping(apply_stock_overrides(stocks))


def _ensure_search_listings(stocks: pd.DataFrame, search: str) -> pd.DataFrame:
    """Add a searched ticker when missing from the cached universe."""
    query = safe_str(search).upper()
    if not query:
        return stocks
    existing = set(stocks["ticker"].astype(str).str.upper())
    if query in existing:
        return stocks
    from stocks.listings.listing_enrichment import ensure_tickers_in_universe

    updated, _ = ensure_tickers_in_universe(stocks, [query], persist=False)
    if len(updated) <= len(stocks):
        return stocks
    updated = apply_display_sector_mapping(
        apply_stock_overrides(enrich_stocks_classification(updated))
    )
    save_stocks_to_db(updated)
    return updated


def _download_india_stocks_csv() -> pd.DataFrame:
    path = hf_hub_download(
        INDIA_STOCKS_DATASET,
        "india.csv",
        repo_type="dataset",
        token=get_hf_token(),
    )
    return pd.read_csv(path, dtype={"ticker": str, "name": str, "market": str, "sector": str}).fillna("")


# Re-run sqlite enrichment when cached industry fill is below this share of unique tickers.
_CLASSIFICATION_REENRICH_MIN_FILL = 0.85


def _needs_bse_label_fix(cached: pd.DataFrame) -> bool:
    """BSE rows where industry was copied from display sector need HF re-import."""
    if cached.empty or "market" not in cached.columns:
        return False
    bse = cached[cached["market"].astype(str).str.upper() == "BSE"]
    if len(bse) < 100:
        return False
    same = (
        bse["sector"].fillna("").astype(str).str.strip()
        == bse["industry"].fillna("").astype(str).str.strip()
    )
    return float(same.sum()) / len(bse) > 0.5


def _needs_classification_reenrich(cached: pd.DataFrame) -> bool:
    if cached.empty:
        return False
    if _needs_bse_label_fix(cached):
        return True
    if "sub_sector" not in cached.columns or cached["sub_sector"].eq("").all():
        return True
    cov = classification_coverage(cached)
    tickers = cov.get("tickers") or 0
    if tickers <= 0:
        return True
    return (cov.get("industry") or 0) / tickers < _CLASSIFICATION_REENRICH_MIN_FILL


def _finalize_stocks(stocks: pd.DataFrame) -> pd.DataFrame:
    return apply_display_sector_mapping(apply_stock_overrides(enrich_stocks_classification(stocks)))


def _enrich_and_persist(stocks: pd.DataFrame) -> pd.DataFrame:
    stocks = _finalize_stocks(stocks)
    save_stocks_to_db(stocks)
    sync_holdings_classification()
    return stocks


def load_india_stocks(*, force_refresh: bool = False) -> pd.DataFrame:
    init_db()

    if not force_refresh and stocks_cache_fresh():
        cached = load_stocks_from_db()
        if not cached.empty:
            if _needs_classification_reenrich(cached):
                base = (
                    _download_india_stocks_csv()
                    if _needs_bse_label_fix(cached)
                    else cached
                )
                return _sync_holdings_listings(_enrich_and_persist(base))
            return _sync_holdings_listings(apply_display_sector_mapping(apply_stock_overrides(cached)))

    try:
        stocks = _sync_holdings_listings(_enrich_and_persist(_download_india_stocks_csv()))
        return stocks
    except Exception as exc:
        log_error(
            DATASET_ERROR,
            "Failed to download India stocks dataset",
            error=str(exc),
            dataset=INDIA_STOCKS_DATASET,
        )
        cached = load_stocks_from_db()
        if not cached.empty:
            enriched = _sync_holdings_listings(_finalize_stocks(cached))
            return enriched
        raise


def normalize_sectors(sector: str | list[str]) -> list[str] | None:
    """Return selected sectors, or None when all sectors should be included."""
    if isinstance(sector, str):
        return None if sector == "All" else [sector]
    picked = [s for s in sector if s and s != "All"]
    return picked or None


def sector_filter_label(sector: str | list[str]) -> str:
    """Short label for captions (empty string means all sectors)."""
    sectors = normalize_sectors(sector)
    if sectors is None:
        return ""
    if len(sectors) == 1:
        return sectors[0]
    return f"{len(sectors)} sectors"


def classifier_filter_label(kind: str, values: str | list[str]) -> str:
    """Short label for industry / sector captions."""
    if isinstance(values, str):
        if values == "All" or not values.strip():
            return ""
        return values
    picked = [v for v in values if v and str(v).strip()]
    if not picked:
        return ""
    if len(picked) == 1:
        return picked[0]
    return f"{len(picked)} {kind}"


def apply_classifier_filters(
    frame: pd.DataFrame,
    *,
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    """Filter by industry / sub-sector when columns exist."""
    filtered = frame
    industries = normalize_sectors(industry)
    sub_sectors = normalize_sectors(sub_sector)
    if industries is not None and "industry" in filtered.columns:
        filtered = filtered[filtered["industry"].isin(industries)]
    if sub_sectors is not None and "sub_sector" in filtered.columns:
        filtered = filtered[filtered["sub_sector"].isin(sub_sectors)]
    return filtered


def filter_stocks(
    stocks: pd.DataFrame,
    market: str = "All",
    sector: str | list[str] = "All",
    search: str = "",
    *,
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    sectors = normalize_sectors(sector)
    if is_scan_playlist(market):
        return scan_playlist_listings(
            stocks,
            market,
            sector=sector,
            search=search,
            industry=industry,
            sub_sector=sub_sector,
        )

    filtered = stocks.copy()
    if market != "All":
        filtered = filtered[filtered["market"] == market]
    if sectors is not None:
        filtered = filtered[filtered["sector"].isin(sectors)]
    filtered = apply_classifier_filters(
        filtered, industry=industry, sub_sector=sub_sector
    )
    if search.strip():
        query = search.strip().lower()
        filtered = filtered[
            filtered["ticker"].str.lower().str.contains(query, na=False)
            | filtered["name"].str.lower().str.contains(query, na=False)
        ]
        if filtered.empty:
            expanded = _ensure_search_listings(stocks, search)
            if len(expanded) > len(stocks):
                filtered = expanded.copy()
                if market != "All":
                    filtered = filtered[filtered["market"] == market]
                if sectors is not None:
                    filtered = filtered[filtered["sector"].isin(sectors)]
                filtered = apply_classifier_filters(
                    filtered, industry=industry, sub_sector=sub_sector
                )
                filtered = filtered[
                    filtered["ticker"].str.lower().str.contains(query, na=False)
                    | filtered["name"].str.lower().str.contains(query, na=False)
                ]
    return filtered


def market_options(stocks: pd.DataFrame, *, include_scan_playlists: bool = True) -> list[str]:
    markets = sorted(stocks["market"].dropna().unique().tolist())
    opts = ["All"] + markets
    if include_scan_playlists:
        return insert_scan_playlist_markets(opts)
    return opts


def _distinct_values(frame: pd.DataFrame, column: str) -> list[str]:
    if column not in frame.columns or frame.empty:
        return []
    values = frame[column].fillna("").astype(str).str.strip()
    return sorted({v for v in values if v and v.lower() != "nan"})


def sector_options(stocks: pd.DataFrame, frame: pd.DataFrame | None = None) -> list[str]:
    source = frame if frame is not None else stocks
    return ["All"] + _distinct_values(source, "sector")


def industry_options(stocks: pd.DataFrame, frame: pd.DataFrame | None = None) -> list[str]:
    source = frame if frame is not None else stocks
    return ["All"] + _distinct_values(source, "industry")


def sub_sector_options(stocks: pd.DataFrame, frame: pd.DataFrame | None = None) -> list[str]:
    source = frame if frame is not None else stocks
    return ["All"] + _distinct_values(source, "sub_sector")
