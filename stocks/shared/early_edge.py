"""Early Edge watchlist — curated names seeded into ``fund_watchlists`` (list_key=early_edge)."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from stocks.core.database import load_fund_watchlist, load_stocks_from_db, replace_fund_watchlist
from stocks.core.text_utils import safe_str
from stocks.shared.corp_tags import clear_corp_tags_cache

EARLY_EDGE_LIST_KEY = "early_edge"
EARLY_EDGE_PLAYLIST_LABEL = "Early Edge"
EARLY_EDGE_TAG = "Edge"

# Manual overrides for typos / ambiguous names → NSE/BSE ticker.
_MANUAL_TICKERS: dict[str, str] = {
    "enviro infra": "EIEL",
    "dam capital": "DAMCAPITAL",
    "creative graphics": "CGRAPHICS",
    "fly sbs": "FLYSBS",
    "sarkar healthcare": "SAKAR",  # Sakar Healthcare (common misspelling)
    "aeroflex industries": "AEROFLEX",
    "v2 retail": "V2RETAIL",
    "repco home finance": "REPCOHOME",
    "sg finserv": "SGFIN",
    "gateway distiparks": "GATEWAY",
    "gateway distriparks": "GATEWAY",
    "ice make": "ICEMAKE",
    "sacheerome": "SACHEEROME",
    "apex frozen": "APEX",
    "ashok leyland": "ASHOKLEY",
    "bajaj consumer": "BAJAJCON",
    "krsnaaa": "KRSNAA",
    "krsnaa": "KRSNAA",
    "pyramid technoplast": "PYRAMID",
    "snowman logistics": "SNOWMAN",
    "cantabil": "CANTABIL",
    "deep indus": "DEEPINDS",
    "deep industries": "DEEPINDS",
    "srm contractors": "SRM",
    "s chand": "SCHAND",
    "sunlight recycling": "SUNLITE",
    "ak capital services": "AKCAPIT",
    "ak captal services": "AKCAPIT",
    "blue pebble": "BLUEPEBBLE",
    "arrow greentech": "ARROWGREEN",
    "alpex solar": "ALPEXSOLAR",
    "mold-tek": "MOLDTKPAC",
    "mold tek": "MOLDTKPAC",
    "jash industries": "JASH",
    "ecos mobility": "ECOSMOBLTY",
    "vision infra": "VIESL",
    "lehar footwear": "LEHAR",
    "prizor viztecxh": "PRIZOR",
    "prizor viztech": "PRIZOR",
    "all e technologies": "ALLETEC",
    "paramount wires and cables": "PARACABLES",
    "chatha foods": "CHATHA",
    "suraksha clinic and diagnostics": "SURAKSHA",
    "yash high voltage": "YASHHV",
    "yash high": "YASHHV",
    "aps solar": "APS",
    "macfos ltd": "ROBU",
    "frehara agro exports": "FRESHARA",
    "freshara agro exports": "FRESHARA",
    "shri ahimsa naurals": "SHRIAHIMSA",
    "shri ahimsa naturals": "SHRIAHIMSA",
    "cosmo firts": "COSMOFIRST",
    "cosmo first": "COSMOFIRST",
    "competent automobiles": "COMPEAU",
    "siyraram silk mills": "SIYSIL",
    "siyaram silk mills": "SIYSIL",
    "dhabriya group": "DHABRIYA",
    "stallion india fluorochem": "STALLION",
    "mb agro": "MPAGI",
    "ramco systems": "RAMCOSYS",
    "aaron industries": "AARON",
    "gpt healtcare": "GPTHEALTH",
    "gpt healthcare": "GPTHEALTH",
    "izomo ltd": "IZMO",
    "izmo ltd": "IZMO",
    "espire hospital": "ESPIRE",
    "crizac": "CRIZAC",
    "frog celsat": "FROG",
    "sirca paints": "SIRCA",
    "pix transmission": "PIXTRANS",
    "tpl plastech": "TPLPLASTEH",
    "laxmi dental": "LAXMIDENTL",
    "windlas biotech": "WINDLAS",
    "mmp industries": "MMP",
    "swiss military": "SWISSMLTRY",
    "landmark global learning": "LGLL",
    "jindal drilling": "JINDRILL",
    "20 microsns": "20MICRONS",
    "20 microns": "20MICRONS",
    "kmew": "KMEW",
    "concord": "CEWATER",  # Concord Enviro Systems
    "systango tecg": "SYSTANGO",
    "systango tech": "SYSTANGO",
    "steel cast": "STEELCAS",
    "vishnu chem": "VISHNU",
    "krishca": "KRISHCA",
    "dishman carbogenic amics": "DCAL",
    "dishman carbogen amcis": "DCAL",
    "vilas transcore": "VILAS",
    "supreme power equipment": "SUPREMEPWR",
    "goodluck india": "GOODLUCK",
    "onepointone solution": "ONEPOINT",
    "worth preipheraks": "WORTHPERI",
    "worth peripherals": "WORTHPERI",
    "beezan explosion": "BEEZAASAN",
    "bew eng": "BEWLTD",
    "prospect": "PCL",
    "mindteck": "MINDTECK",
    "high green carbon": "HIGREEN",
}

# Display order seed queries (dedupe via ticker when seeding).
EARLY_EDGE_SEED_QUERIES: list[str] = [
    "ENVIRO INFRA",
    "DAM CAPITAL",
    "Creative GRAPHICS",
    "FLY SBS",
    "SARKAR Healthcare",
    "Aeroflex Industries",
    "V2 Retail",
    "Repco Home Finance",
    "SG Finserv",
    "Gateway Distiparks",
    "ICE MAKE",
    "SACHEEROME",
    "APEX FROZEN",
    "ASHOK LEyland",
    "Bajaj Consumer",
    "Krsnaaa",
    "Pyramid Technoplast",
    "Snowman Logistics",
    "CANTABIL",
    "Deep Indus",
    "SRM contractors",
    "S chand",
    "Sunlight Recycling",
    "AK capital services",
    "blue pebble",
    "arrow greentech",
    "alpex solar",
    "mold-tek",
    "jash industries",
    "ECOS mobility",
    "vision infra",
    "lehar footwear",
    "prizor viztecxh",
    "all e technologies",
    "Paramount wires and cables",
    "chatha foods",
    "suraksha clinic and diagnostics",
    "Yash high voltage",
    "APS Solar",
    "MACFOS ltd",
    "frehara Agro exports",
    "shri ahimsa naurals",
    "cosmo firts",
    "competent automobiles",
    "siyraram silk Mills",
    "Dhabriya Group",
    "stallion india fluorochem",
    "MB Agro",
    "RAMCO systems",
    "AARON INDUSTRIES",
    "GPT healtcare",
    "izomo ltd",
    "espire hospital",
    "crizac",
    "Frog celsat",
    "sirca paints",
    "PIX transmission",
    "TPL Plastech",
    "laxmi dental",
    "windlas biotech",
    "MMP Industries",
    "swiss military",
    "landmark global learning",
    "jindal drilling",
    "20 microsns",
    "KMEW",
    "YASH High",
    "CONCORD",
    "systango tecg",
    "steel cast",
    "vishnu chem",
    "krishca",
    "dishman carbogenic Amics",
    "vilas transcore",
    "supreme power equipment",
    "goodluck india",
    "onepointone solution",
    "worth preipheraks",
    "beezan explosion",
    "BEW eng",
    "prospect",
    "mindteck",
    "High green carbon",
]


def _norm_query(s: str) -> str:
    s = safe_str(s).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(
        r"\b(ltd|limited|industries|india|pvt|private|co|company|the|and|&)\b",
        " ",
        s,
    )
    return re.sub(r"\s+", " ", s).strip()


def resolve_early_edge_queries(
    queries: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Map seed queries → listing rows. Returns (resolved_df, unresolved_queries)."""
    stocks = load_stocks_from_db()
    if stocks.empty:
        return pd.DataFrame(), list(queries or EARLY_EDGE_SEED_QUERIES)

    pref = {"NSE": 0, "NSE SME": 1, "BSE": 2}
    work = stocks.copy()
    work["_ticker"] = work["ticker"].astype(str).str.strip().str.upper()
    work["_pref"] = work["market"].map(lambda m: pref.get(str(m), 9))
    work = work.sort_values(["_pref", "_ticker"])
    by_ticker: dict[str, Any] = {}
    for t, grp in work.groupby("_ticker", sort=False):
        by_ticker[safe_str(t).upper()] = grp.iloc[0]

    # Index overrides by the same normalizer used for queries.
    manual_by_norm: dict[str, str] = {}
    for key, ticker in _MANUAL_TICKERS.items():
        manual_by_norm[_norm_query(key)] = safe_str(ticker).upper()
        manual_by_norm[safe_str(key).lower().strip()] = safe_str(ticker).upper()

    rows: list[dict[str, Any]] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for raw in queries or EARLY_EDGE_SEED_QUERIES:
        q = safe_str(raw).strip()
        if not q:
            continue
        nq = _norm_query(q)
        ticker = manual_by_norm.get(nq) or manual_by_norm.get(q.lower())
        if not ticker:
            guess = re.sub(r"[^A-Z0-9]", "", q.upper())
            if guess in by_ticker:
                ticker = guess
        if not ticker or ticker not in by_ticker:
            unresolved.append(q)
            continue
        if ticker in seen:
            continue
        seen.add(ticker)
        hit = by_ticker[ticker]
        rows.append(
            {
                "ticker": ticker,
                "market": safe_str(hit.get("market")).upper() or "NSE",
                "name": safe_str(hit.get("name")) or ticker,
                "sector": safe_str(hit.get("sector")) or "",
                "source_investor": "Early Edge",
                "holding_entity": q,
            }
        )
    return pd.DataFrame(rows), unresolved


def seed_early_edge(*, force: bool = False) -> dict[str, Any]:
    """Write Early Edge tickers into DB. Skips if non-empty unless ``force``."""
    existing = load_fund_watchlist(EARLY_EDGE_LIST_KEY)
    if not force and not existing.empty:
        return {
            "written": len(existing),
            "skipped": True,
            "unresolved": [],
        }
    df, unresolved = resolve_early_edge_queries()
    n = replace_fund_watchlist(EARLY_EDGE_LIST_KEY, df)
    clear_corp_tags_cache()
    return {"written": n, "skipped": False, "unresolved": unresolved, "df": df}


def ensure_early_edge_seeded() -> int:
    """Idempotent seed used by page / playlist loaders."""
    info = seed_early_edge(force=False)
    return int(info.get("written") or 0)


def load_early_edge_df() -> pd.DataFrame:
    ensure_early_edge_seeded()
    return load_fund_watchlist(EARLY_EDGE_LIST_KEY)


def early_edge_tickers() -> set[str]:
    df = load_early_edge_df()
    if df.empty:
        return set()
    return {safe_str(t).upper() for t in df["ticker"] if safe_str(t)}


def early_edge_count() -> int:
    return len(early_edge_tickers())


def hydrate_early_edge_missing(
    df: pd.DataFrame | None = None,
    *,
    progress_callback=None,
) -> dict[str, int]:
    """
    Fetch missing mcap / website / sector from screener + Yahoo and persist to SQLite.

    Returns counts: ``tried``, ``mcap``, ``website``, ``sector``.
    """
    from stocks.core.database import (
        load_company_profiles_from_db,
        load_market_cap_from_db,
        save_market_cap_to_db,
        update_stock_classification,
    )
    from stocks.core.text_utils import sanitize_website
    from stocks.market.company_profile import merge_company_profile
    from stocks.market.screener_profile import fetch_market_cap_cr

    view = enrich_watching_board(df)
    if view.empty:
        return {"tried": 0, "mcap": 0, "website": 0, "sector": 0}

    tickers = view["ticker"].astype(str).str.upper().tolist()
    profiles = load_company_profiles_from_db(tickers)
    mcap_known: set[str] = set()
    try:
        mcap_df = load_market_cap_from_db(tickers, allow_stale=True)
        if mcap_df is not None and not mcap_df.empty:
            mcap_known = {
                safe_str(t).upper()
                for t in mcap_df["ticker"]
                if safe_str(t)
            }
    except Exception:
        pass

    pending: list[tuple[str, str, bool, bool, bool]] = []
    for _, row in view.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        market = safe_str(row.get("market")).upper() or "NSE"
        need_mcap = ticker not in mcap_known
        prof = profiles.get(ticker) or {}
        need_web = not sanitize_website(prof.get("website"))
        need_sector = not safe_str(row.get("sector"))
        if need_mcap or need_web or need_sector:
            pending.append((ticker, market, need_mcap, need_web, need_sector))

    stats = {"tried": len(pending), "mcap": 0, "website": 0, "sector": 0}
    total = len(pending)
    for i, (ticker, market, need_mcap, need_web, need_sector) in enumerate(pending, start=1):
        if progress_callback:
            try:
                progress_callback(i - 1, total, ticker)
            except Exception:
                pass
        try:
            if need_mcap:
                mcap = fetch_market_cap_cr(ticker, market)
                if mcap is not None and mcap > 0:
                    save_market_cap_to_db(ticker, float(mcap), market=market)
                    stats["mcap"] += 1
                    need_mcap = False
            if need_web or need_sector or need_mcap:
                merged = merge_company_profile({}, ticker, market)
                if sanitize_website(merged.get("website")):
                    if need_web:
                        stats["website"] += 1
                sector = safe_str(merged.get("company_sector"))
                industry = safe_str(merged.get("company_industry"))
                if need_sector and (sector or industry):
                    if update_stock_classification(
                        ticker,
                        market=market,
                        sector=sector or None,
                        industry=industry or None,
                        sub_sector=industry or None,
                    ):
                        stats["sector"] += 1
                # Profile path may also have saved mcap from screener/Yahoo.
                if need_mcap:
                    mcap_df = load_market_cap_from_db([ticker], allow_stale=True)
                    if mcap_df is not None and not mcap_df.empty:
                        stats["mcap"] += 1
        except Exception:
            continue
    if progress_callback:
        try:
            progress_callback(total, total, "")
        except Exception:
            pass
    return stats


hydrate_watching_missing = hydrate_early_edge_missing


def enrich_watching_board(
    df: pd.DataFrame | None = None,
    *,
    list_tag: str = "",
    is_edge: bool = False,
    is_holding: bool = False,
) -> pd.DataFrame:
    """Watchlist rows + listing sector/sub_sector + SQLite mcap / Cap code / website."""
    from stocks.core.database import load_company_profiles_from_db, load_market_cap_from_db
    from stocks.core.text_utils import sanitize_website
    from stocks.governance.score import mcap_cap_code, mcap_cap_label
    from stocks.listings.classification_service import (
        load_classification_maps,
        lookup_classification,
    )
    from stocks.shared.links import research_links

    base = df if df is not None else load_early_edge_df()
    if base is None or base.empty:
        return pd.DataFrame()

    out = base.copy()
    out["ticker"] = out["ticker"].astype(str).str.strip().str.upper()
    stocks = load_stocks_from_db()
    listing_cols = ["ticker", "name", "market", "sector", "industry", "sub_sector"]
    if not stocks.empty:
        have = [c for c in listing_cols if c in stocks.columns]
        listings = stocks[have].copy()
        listings["ticker"] = listings["ticker"].astype(str).str.strip().str.upper()
        pref = {"NSE": 0, "NSE SME": 1, "BSE": 2}
        if "market" in listings.columns:
            listings["_pref"] = listings["market"].map(lambda m: pref.get(str(m), 9))
            listings = listings.sort_values("_pref").drop_duplicates("ticker", keep="first")
            listings = listings.drop(columns=["_pref"], errors="ignore")
        else:
            listings = listings.drop_duplicates("ticker", keep="first")
        out = out.drop(
            columns=[c for c in ("name", "market", "sector") if c in out.columns and c in listings.columns],
            errors="ignore",
        )
        out = out.merge(listings, on="ticker", how="left", suffixes=("", "_list"))

    for col in ("sector", "industry", "sub_sector", "name", "market"):
        if col not in out.columns:
            out[col] = ""

    # Fill gaps from classification maps (stock-analysis DBs).
    try:
        class_maps = load_classification_maps()
    except Exception:
        class_maps = None
    if class_maps:
        for idx, row in out.iterrows():
            ticker = safe_str(row.get("ticker")).upper()
            if not ticker:
                continue
            sector, industry, subsector = lookup_classification(ticker, maps=class_maps)
            if not safe_str(row.get("sector")) and sector:
                out.at[idx, "sector"] = sector
            if not safe_str(row.get("industry")) and industry:
                out.at[idx, "industry"] = industry
            if not safe_str(row.get("sub_sector")) and subsector:
                out.at[idx, "sub_sector"] = subsector

    tickers = out["ticker"].tolist()
    profiles = load_company_profiles_from_db(tickers)
    websites: list[str | None] = []
    for _, row in out.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        prof = profiles.get(ticker) or {}
        web = sanitize_website(prof.get("website"))
        websites.append(web)
        if not safe_str(row.get("sector")) and safe_str(prof.get("company_sector")):
            out.at[row.name, "sector"] = safe_str(prof.get("company_sector"))
        if not safe_str(row.get("industry")) and safe_str(prof.get("company_industry")):
            out.at[row.name, "industry"] = safe_str(prof.get("company_industry"))
        if not safe_str(row.get("sub_sector")) and safe_str(prof.get("company_industry")):
            out.at[row.name, "sub_sector"] = safe_str(prof.get("company_industry"))
    out["website"] = websites

    # Prefer industry as sub_sector display when sub_sector blank.
    out["sub_sector"] = out.apply(
        lambda r: safe_str(r.get("sub_sector"))
        or safe_str(r.get("industry"))
        or "",
        axis=1,
    )
    out["sector"] = out["sector"].map(lambda s: safe_str(s) or "")
    out["market"] = out["market"].map(lambda m: safe_str(m).upper() or "NSE")
    out["name"] = out.apply(
        lambda r: safe_str(r.get("name")) or safe_str(r.get("ticker")),
        axis=1,
    )

    mcap_map: dict[str, float] = {}
    try:
        mcap_df = load_market_cap_from_db(tickers, allow_stale=True)
        if mcap_df is not None and not mcap_df.empty:
            for _, row in mcap_df.iterrows():
                t = safe_str(row.get("ticker")).upper()
                val = row.get("market_cap_cr")
                if t and val is not None and not pd.isna(val):
                    try:
                        mcap_map[t] = float(val)
                    except (TypeError, ValueError):
                        continue
    except Exception:
        pass

    out["market_cap_cr"] = out["ticker"].map(lambda t: mcap_map.get(safe_str(t).upper()))
    out["cap_code"] = out["market_cap_cr"].map(mcap_cap_code)
    out["cap_label"] = out["market_cap_cr"].map(mcap_cap_label)
    out["list_tag"] = safe_str(list_tag)
    out["is_edge"] = bool(is_edge)
    out["is_holding"] = bool(is_holding)

    # Prices: SQLite first, then Yahoo batch for gaps (saved back for next open).
    from stocks.core.database import load_stock_prices_from_db, save_stock_price_to_db
    from stocks.market.price_service import fetch_current_prices

    price_map = load_stock_prices_from_db(tickers, allow_stale=True)
    missing_price = [
        safe_str(t).upper()
        for t in tickers
        if safe_str(t).upper() and safe_str(t).upper() not in price_map
    ]
    if missing_price:
        market_by = {
            safe_str(r.get("ticker")).upper(): safe_str(r.get("market")).upper() or "NSE"
            for _, r in out.iterrows()
            if safe_str(r.get("ticker"))
        }
        fetched = fetch_current_prices(
            missing_price,
            [market_by.get(t) for t in missing_price],
        )
        for t, px in fetched.items():
            key = safe_str(t).upper()
            if px is None:
                continue
            try:
                price_map[key] = float(px)
                save_stock_price_to_db(key, float(px), market=market_by.get(key))
            except (TypeError, ValueError):
                continue

    out["price"] = out["ticker"].map(lambda t: price_map.get(safe_str(t).upper()))

    sc_list: list[str] = []
    tv_list: list[str] = []
    for _, row in out.iterrows():
        sc, tv = research_links(
            safe_str(row.get("ticker")),
            safe_str(row.get("market")) or "NSE",
        )
        sc_list.append(sc)
        tv_list.append(tv)
    out["sc"] = sc_list
    out["tv"] = tv_list

    sort_cols = [c for c in ("sector", "name", "ticker") if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=True, na_position="last")
    return out.reset_index(drop=True)


def enrich_early_edge_display(df: pd.DataFrame | None = None) -> pd.DataFrame:
    return enrich_watching_board(df, list_tag="Edge", is_edge=True)


def watching_gap_counts(view: pd.DataFrame | None) -> dict[str, int]:
    """How many rows are missing price / sector / mcap / website (Fill-missing targets)."""
    base = {"total": 0, "price": 0, "sector": 0, "mcap": 0, "web": 0, "any_rows": 0}
    if view is None or view.empty:
        return base
    n = len(view)
    missing_price = (
        int(pd.Series(view["price"]).isna().sum()) if "price" in view.columns else n
    )
    missing_sector = (
        int(view["sector"].astype(str).str.strip().eq("").sum())
        if "sector" in view.columns
        else n
    )
    missing_mcap = (
        int(view["market_cap_cr"].isna().sum()) if "market_cap_cr" in view.columns else n
    )
    missing_web = (
        int(view["website"].astype(str).str.strip().eq("").sum())
        if "website" in view.columns
        else n
    )
    gap_rows = 0
    for _, row in view.iterrows():
        if (
            (pd.isna(row.get("price")) if "price" in view.columns else True)
            or not safe_str(row.get("sector"))
            or (pd.isna(row.get("market_cap_cr")) if "market_cap_cr" in view.columns else True)
            or not safe_str(row.get("website"))
        ):
            gap_rows += 1
    return {
        "total": n,
        "price": missing_price,
        "sector": missing_sector,
        "mcap": missing_mcap,
        "web": missing_web,
        "any_rows": gap_rows,
    }


def format_watching_gaps(counts: dict[str, int]) -> str:
    if not counts.get("total"):
        return ""
    if not counts.get("any_rows"):
        return "No gaps — price, sector, mcap, and web filled for every name."
    bits: list[str] = []
    for key, label in (
        ("price", "price"),
        ("sector", "sector"),
        ("mcap", "mcap"),
        ("web", "web"),
    ):
        n = int(counts.get(key) or 0)
        if n:
            bits.append(f"{label} **{n}**")
    head = f"**{counts['any_rows']}** names need Fill missing"
    return f"{head} · " + " · ".join(bits) if bits else head


def is_early_edge_playlist(market: str) -> bool:
    return safe_str(market) == EARLY_EDGE_PLAYLIST_LABEL


def early_edge_playlist_listings(
    stocks: pd.DataFrame,
    *,
    sector: str | list[str] = "All",
    search: str = "",
    industry: str | list[str] = "All",
    sub_sector: str | list[str] = "All",
) -> pd.DataFrame:
    """Listings for Early Edge watchlist, merged with India dataset metadata."""
    edge = load_early_edge_df()
    if edge.empty:
        return stocks.iloc[0:0].copy()

    tickers = {safe_str(t).upper() for t in edge["ticker"] if safe_str(t)}
    matched = stocks[stocks["ticker"].astype(str).str.upper().isin(tickers)].copy()
    matched_tickers = set(matched["ticker"].astype(str).str.upper())
    missing = tickers - matched_tickers
    if missing:
        lookup = edge.set_index(edge["ticker"].astype(str).str.upper())
        extra_rows: list[dict] = []
        for ticker in sorted(missing):
            row = lookup.loc[ticker] if ticker in lookup.index else None
            if row is None:
                continue
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            extra_rows.append(
                {
                    "ticker": ticker,
                    "market": safe_str(row.get("market")).upper() or "NSE",
                    "name": safe_str(row.get("name")) or "",
                    "sector": safe_str(row.get("sector")) or "",
                }
            )
        if extra_rows:
            matched = pd.concat([matched, pd.DataFrame(extra_rows)], ignore_index=True)

    matched = matched.drop_duplicates("ticker", keep="first")
    from stocks.listings.stocks_data import apply_classifier_filters, normalize_sectors

    sectors = normalize_sectors(sector)
    if sectors is not None:
        matched = matched[matched["sector"].isin(sectors)]
    matched = apply_classifier_filters(matched, industry=industry, sub_sector=sub_sector)
    if search.strip():
        q = search.strip().lower()
        mask = (
            matched["ticker"].astype(str).str.lower().str.contains(q, na=False)
            | matched["name"].astype(str).str.lower().str.contains(q, na=False)
        )
        matched = matched[mask]
    return matched.reset_index(drop=True)
