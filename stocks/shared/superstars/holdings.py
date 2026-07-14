"""Superstar investor holdings — DB persistence, PEAD cross-reference, aggregation."""

from __future__ import annotations

import pandas as pd

from stocks.core.database import (
    load_all_superstar_holdings_df,
    load_superstar_fetched_at,
    load_superstar_holdings_map,
)
from stocks.core.text_utils import safe_str
from stocks.listings.classification_service import enrich_stocks_classification


def hydrate_superstar_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add display columns used by the Superstars UI."""
    if df is None or df.empty:
        return pd.DataFrame()
    work = df.copy()
    if "change_display" not in work.columns:
        work["change_display"] = work.apply(
            lambda row: (
                "NEW"
                if safe_str(row.get("change_type")).lower() == "new"
                else (
                    f"{float(row['change_qtr']):+.2f}%"
                    if row.get("change_qtr") is not None
                    and not pd.isna(row.get("change_qtr"))
                    else "0.00%"
                )
            ),
            axis=1,
        )
    if "holding_value_display" not in work.columns:
        work["holding_value_display"] = work["holding_value_cr"].apply(
            lambda v: f"₹{v:.1f} Cr" if v is not None and not pd.isna(v) and v else ""
        )
    if "price_display" not in work.columns:
        work["price_display"] = work["price"].apply(
            lambda p: f"₹{p:,.2f}" if pd.notna(p) and p else ""
        )
    return work


def portfolio_dict_from_df(df: pd.DataFrame) -> dict[str, pd.DataFrame | str | int]:
    if df is None or df.empty or "change_type" not in df.columns:
        return {
            "all": df if df is not None else pd.DataFrame(),
            "new_picks": pd.DataFrame(),
            "increased": pd.DataFrame(),
            "decreased": pd.DataFrame(),
            "unchanged": pd.DataFrame(),
            "count": 0,
            "error": "",
        }
    work = hydrate_superstar_display_df(df)
    return {
        "all": work,
        "new_picks": work[work["change_type"] == "new"].copy(),
        "increased": work[work["change_type"] == "increased"].copy(),
        "decreased": work[work["change_type"] == "decreased"].copy(),
        "unchanged": work[work["change_type"] == "unchanged"].copy(),
        "count": len(work),
        "error": "",
    }


def portfolios_from_db(
    investor_names: list[str],
) -> tuple[dict[str, dict], dict[str, str], str | None]:
    """Rebuild session portfolios from persisted superstar_holdings rows."""
    raw = load_all_superstar_holdings_df()
    if raw.empty:
        return {}, {}, None

    work = enrich_superstar_classification(raw)
    work = hydrate_superstar_display_df(work)
    fetched_ts = load_superstar_fetched_at() or ""

    portfolios: dict[str, dict] = {}
    fetched_at: dict[str, str] = {}
    for name in investor_names:
        chunk = work[work["investor"] == name].copy()
        if chunk.empty:
            portfolios[name] = portfolio_dict_from_df(pd.DataFrame())
            continue
        chunk = chunk.drop(columns=["investor"], errors="ignore")
        chunk = chunk.sort_values(
            ["holding_value_cr", "holding_percent"],
            ascending=[False, False],
            na_position="last",
        ).reset_index(drop=True)
        portfolios[name] = portfolio_dict_from_df(chunk)
        if fetched_ts:
            fetched_at[name] = fetched_ts

    return portfolios, fetched_at, fetched_ts or None


def _holder_badge(change_type: str, change_qtr: float | None) -> str:
    ct = safe_str(change_type).lower()
    if ct == "new":
        return "NEW"
    if ct == "increased":
        if change_qtr is not None:
            try:
                return f"↑{float(change_qtr):+.2f}%"
            except (TypeError, ValueError):
                return "↑"
        return "↑"
    if ct == "decreased":
        if change_qtr is not None:
            try:
                return f"↓{float(change_qtr):+.2f}%"
            except (TypeError, ValueError):
                return "↓"
        return "↓"
    return ""


def is_superstar_best_pick(holders: list[dict]) -> bool:
    """High-conviction superstar signal for PEAD cross-check."""
    if not holders:
        return False
    if len(holders) >= 2:
        return True
    for h in holders:
        ct = safe_str(h.get("change_type")).lower()
        if ct == "new":
            return True
        if ct == "increased":
            try:
                ch = float(h.get("change_qtr"))
                if ch > 0:
                    return True
            except (TypeError, ValueError):
                return True
    return False


def format_superstar_holders(holders: list[dict]) -> str:
    if not holders:
        return ""
    parts: list[str] = []
    for h in holders:
        inv = safe_str(h.get("investor"))
        if not inv:
            continue
        badge = _holder_badge(h.get("change_type"), h.get("change_qtr"))
        parts.append(f"{inv} {badge}".strip() if badge else inv)
    return " · ".join(parts)


def superstar_pead_map(tickers: list[str]) -> dict[str, dict]:
    """Per-ticker superstar data for PEAD dashboard rows."""
    raw = load_superstar_holdings_map(tickers)
    out: dict[str, dict] = {}
    for ticker, holders in raw.items():
        if not holders:
            continue
        out[ticker.upper()] = {
            "ss_holders": holders,
            "ss_holders_label": format_superstar_holders(holders),
            "ss_best": is_superstar_best_pick(holders),
            "ss_investor_count": len(holders),
        }
    return out


def enrich_superstar_classification(df: pd.DataFrame) -> pd.DataFrame:
    """Attach sector / industry / sub_sector from local classification DB."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    from stocks.listings.sector_display import apply_display_sector_mapping

    work = df.copy()
    work["ticker"] = work["symbol"]
    work["market"] = work["exchange"].apply(
        lambda x: "BSE" if safe_str(x).upper() == "BSE" else "NSE"
    )
    work = enrich_stocks_classification(work)
    return apply_display_sector_mapping(work)


def aggregate_all_portfolios(portfolios: dict) -> pd.DataFrame:
    """Merge every loaded investor portfolio into one classified DataFrame."""
    frames: list[pd.DataFrame] = []
    for inv_name, data in portfolios.items():
        if not isinstance(data, dict):
            continue
        chunk = data.get("all")
        if not isinstance(chunk, pd.DataFrame) or chunk.empty:
            continue
        row = chunk.copy()
        row["investor"] = inv_name
        frames.append(row)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    if "sector" in merged.columns and merged["sector"].astype(str).str.strip().ne("").any():
        return merged
    return enrich_superstar_classification(merged)


def all_investors_summary(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {
            "total_holdings": 0,
            "unique_symbols": 0,
            "investors": 0,
            "new_picks": 0,
            "increased": 0,
            "decreased": 0,
        }
    return {
        "total_holdings": len(df),
        "unique_symbols": int(df["symbol"].astype(str).str.upper().nunique()),
        "investors": int(df["investor"].nunique()),
        "new_picks": int((df["change_type"] == "new").sum()),
        "increased": int((df["change_type"] == "increased").sum()),
        "decreased": int((df["change_type"] == "decreased").sum()),
    }


def investor_activity(df: pd.DataFrame) -> pd.DataFrame:
    """Per-investor counts of holdings and quarterly changes."""
    if df is None or df.empty:
        return pd.DataFrame()
    rows: list[dict] = []
    for inv, grp in df.groupby("investor", sort=True):
        rows.append(
            {
                "investor": inv,
                "holdings": len(grp),
                "new_picks": int((grp["change_type"] == "new").sum()),
                "increased": int((grp["change_type"] == "increased").sum()),
                "decreased": int((grp["change_type"] == "decreased").sum()),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["new_picks", "increased", "holdings"],
        ascending=False,
    )


def new_picks_by_sector(df: pd.DataFrame) -> pd.DataFrame:
    """Group latest NEW picks by sector and sub-sector with investor detail."""
    if df is None or df.empty:
        return pd.DataFrame()
    new_df = df[df["change_type"] == "new"].copy()
    if new_df.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for (sector, sub_sector), grp in new_df.groupby(
        ["sector", "sub_sector"], dropna=False, sort=False
    ):
        detail_parts: list[str] = []
        for _, row in grp.sort_values("investor").iterrows():
            sym = safe_str(row.get("symbol")).upper()
            inv = safe_str(row.get("investor"))
            detail_parts.append(f"{sym} ({inv})")
        investors = sorted(grp["investor"].unique())
        rows.append(
            {
                "sector": safe_str(sector) or "—",
                "sub_sector": safe_str(sub_sector) or "—",
                "new_picks": len(grp),
                "investors": len(investors),
                "investor_list": ", ".join(investors),
                "stocks": " · ".join(detail_parts),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["new_picks", "investors"],
        ascending=False,
    )


def top_sectors_new_picks(df: pd.DataFrame, *, top_n: int = 10) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    new_df = df[df["change_type"] == "new"]
    if new_df.empty:
        return pd.DataFrame()
    out = (
        new_df.groupby("sector", dropna=False)
        .agg(
            new_picks=("symbol", "count"),
            investors=("investor", "nunique"),
            sub_sectors=("sub_sector", "nunique"),
        )
        .reset_index()
    )
    out["sector"] = out["sector"].apply(lambda s: safe_str(s) or "—")
    return out.sort_values("new_picks", ascending=False).head(top_n)


def common_stocks(df: pd.DataFrame, *, min_investors: int = 2) -> pd.DataFrame:
    """Stocks held by multiple ace investors — consensus holdings."""
    if df is None or df.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    grouped = df.groupby(df["symbol"].astype(str).str.upper(), sort=False)
    for symbol, grp in grouped:
        if not symbol:
            continue
        investors = sorted(grp["investor"].unique())
        if len(investors) < min_investors:
            continue

        activity_parts: list[str] = []
        for _, row in grp.sort_values("investor").iterrows():
            inv = safe_str(row.get("investor"))
            ct = safe_str(row.get("change_type")).lower()
            if ct == "new":
                activity_parts.append(f"{inv} NEW")
            elif ct == "increased":
                ch = row.get("change_qtr")
                if ch is not None and not pd.isna(ch):
                    activity_parts.append(f"{inv} +{float(ch):.2f}%")
                else:
                    activity_parts.append(f"{inv} ↑")
            elif ct == "decreased":
                ch = row.get("change_qtr")
                if ch is not None and not pd.isna(ch):
                    activity_parts.append(f"{inv} {float(ch):.2f}%")
                else:
                    activity_parts.append(f"{inv} ↓")
            else:
                activity_parts.append(inv)

        first = grp.iloc[0]
        value_cr = grp["holding_value_cr"].dropna()
        rows.append(
            {
                "symbol": symbol,
                "company_name": safe_str(first.get("company_name")),
                "exchange": safe_str(first.get("exchange")) or "NSE",
                "screener_slug": safe_str(first.get("screener_slug")),
                "sector": safe_str(first.get("sector")) or "—",
                "industry": safe_str(first.get("industry") or first.get("sub_sector")) or "—",
                "sub_sector": safe_str(first.get("sub_sector")) or "—",
                "investor_count": len(investors),
                "new_count": int((grp["change_type"] == "new").sum()),
                "increased_count": int((grp["change_type"] == "increased").sum()),
                "investors": ", ".join(investors),
                "activity": " · ".join(activity_parts),
                "combined_value_cr": round(float(value_cr.sum()), 2) if not value_cr.empty else None,
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["investor_count", "new_count", "increased_count", "combined_value_cr"],
        ascending=False,
    )


def consensus_momentum(df: pd.DataFrame, *, min_investors: int = 2) -> pd.DataFrame:
    """Stocks where multiple investors added or increased in the same quarter."""
    if df is None or df.empty:
        return pd.DataFrame()
    active = df[df["change_type"].isin(["new", "increased"])].copy()
    if active.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for symbol, grp in active.groupby(active["symbol"].astype(str).str.upper(), sort=False):
        if not symbol:
            continue
        investors = sorted(grp["investor"].unique())
        if len(investors) < min_investors:
            continue
        first = grp.iloc[0]
        activity = format_superstar_holders(
            [
                {
                    "investor": row["investor"],
                    "change_type": row.get("change_type"),
                    "change_qtr": row.get("change_qtr"),
                }
                for _, row in grp.iterrows()
            ]
        )
        rows.append(
            {
                "symbol": symbol,
                "company_name": safe_str(first.get("company_name")),
                "exchange": safe_str(first.get("exchange")) or "NSE",
                "screener_slug": safe_str(first.get("screener_slug")),
                "sector": safe_str(first.get("sector")) or "—",
                "industry": safe_str(first.get("industry") or first.get("sub_sector")) or "—",
                "sub_sector": safe_str(first.get("sub_sector")) or "—",
                "active_investors": len(investors),
                "new_count": int((grp["change_type"] == "new").sum()),
                "increased_count": int((grp["change_type"] == "increased").sum()),
                "activity": activity,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["active_investors", "new_count", "increased_count"],
        ascending=False,
    )
