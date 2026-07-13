"""Curated merger/demerger rows missing from the NSE corporate-actions feed.

Spin-off listings and group carve-outs often do not appear as NSE corp-action rows.
"""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str

# demerged_company / demerged_ticker = the new entity spun out (parent rows).
# parent_company / parent_ticker = the original listed parent (spin-off listing rows).
SUPPLEMENT_ROWS: list[dict] = [
    {
        "ticker": "KAMDHENU",
        "company": "Kamdhenu Limited",
        "action_type": "Demerger",
        "ex_date": "2022-09-06",
        "record_date": "2022-09-06",
        "ratio": "1:1",
        "demerged_company": "Kamdhenu Ventures Limited",
        "demerged_ticker": "KAMOPAINTS",
        "subject": "Demerger — paints business to Kamdhenu Ventures",
        "source": "NSE+Manual",
    },
    {
        "ticker": "KAMOPAINTS",
        "company": "Kamdhenu Ventures (Komo Paints)",
        "action_type": "Demerger",
        "ex_date": "2023-01-24",
        "record_date": "2022-09-09",
        "ratio": "1:1",
        "parent_company": "Kamdhenu Limited",
        "parent_ticker": "KAMDHENU",
        "subject": "Demerged entity listed (paints business)",
        "source": "Manual",
    },
    {
        "ticker": "EPACKPEB",
        "company": "Epack Prefab Technologies Limited",
        "action_type": "Demerger",
        "ex_date": "2025-10-01",
        "record_date": "2025-09-30",
        "ratio": None,
        "parent_company": "EPACK Durable Limited",
        "parent_ticker": "EPACK",
        "subject": "Group prefab vertical listed via IPO (EPACK Group carve-out)",
        "source": "Manual",
    },
]

_ENRICH_BY_TICKER_DATE: dict[tuple[str, str], dict] = {
    (safe_str(r["ticker"]).upper(), safe_str(r.get("ex_date"))): r for r in SUPPLEMENT_ROWS
}

# Parent ticker -> demerged entity (for enriching bare NSE demerger rows).
_PARENT_TO_DEMERGED: dict[str, dict] = {
    safe_str(r["ticker"]).upper(): {
        "demerged_company": r.get("demerged_company"),
        "demerged_ticker": r.get("demerged_ticker"),
        "ratio": r.get("ratio"),
    }
    for r in SUPPLEMENT_ROWS
    if r.get("demerged_company")
}


def _finalize_counterparty(df: pd.DataFrame) -> pd.DataFrame:
    """Set counterparty_company/ticker for display (TradeBrains-style other leg)."""
    out = df.copy()
    for col in (
        "demerged_company",
        "demerged_ticker",
        "parent_company",
        "parent_ticker",
        "counterparty_company",
        "counterparty_ticker",
    ):
        if col not in out.columns:
            out[col] = None

    for idx, row in out.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        dem_t = safe_str(row.get("demerged_ticker")).upper()
        par_t = safe_str(row.get("parent_ticker")).upper()
        if dem_t and dem_t != ticker:
            out.at[idx, "counterparty_company"] = row.get("demerged_company")
            out.at[idx, "counterparty_ticker"] = dem_t
        elif par_t and par_t != ticker:
            out.at[idx, "counterparty_company"] = row.get("parent_company")
            out.at[idx, "counterparty_ticker"] = par_t
        elif safe_str(row.get("related_ticker")).upper() not in ("", ticker.upper()):
            out.at[idx, "counterparty_company"] = row.get("related_company")
            out.at[idx, "counterparty_ticker"] = row.get("related_ticker")

    return out


def assign_row_roles(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    roles: list[str] = []
    for _, row in out.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        parent = safe_str(row.get("parent_ticker")).upper()
        demerged = safe_str(row.get("demerged_ticker")).upper()
        if parent and parent != ticker:
            roles.append("Spin-off")
        elif demerged and demerged != ticker:
            roles.append("Parent")
        else:
            roles.append("")
    out["row_role"] = roles
    return out


def sort_demerger_groups(df: pd.DataFrame) -> pd.DataFrame:
    """Keep parent demerger rows adjacent to their spin-off listing rows."""
    if df.empty:
        return df
    work = assign_row_roles(df)
    keys: list[str] = []
    order: list[int] = []
    for idx, row in work.iterrows():
        ticker = safe_str(row.get("ticker")).upper()
        parent = safe_str(row.get("parent_ticker")).upper()
        demerged = safe_str(row.get("demerged_ticker")).upper()
        ex = row.get("ex_date")
        ex_ts = pd.to_datetime(ex, errors="coerce")
        ex_ord = -int(ex_ts.value) if pd.notna(ex_ts) else 0
        if parent:
            group = parent
            sub = 1
        elif demerged:
            group = ticker
            sub = 0
        else:
            group = ticker
            sub = 0
        keys.append(f"{group}|{sub}|{ex_ord}|{ticker}")
        order.append(idx)
    work["_sort"] = keys
    work = work.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
    return work


def apply_merger_demerger_supplements(df: pd.DataFrame) -> pd.DataFrame:
    """Merge curated rows and enrich NSE rows with demerged-entity names."""
    base = df.copy() if df is not None and not df.empty else pd.DataFrame()
    for col in (
        "ticker",
        "company",
        "action_type",
        "ex_date",
        "record_date",
        "ratio",
        "demerged_company",
        "demerged_ticker",
        "parent_company",
        "parent_ticker",
        "related_ticker",
        "related_company",
        "counterparty_company",
        "counterparty_ticker",
        "subject",
        "source",
    ):
        if col not in base.columns:
            base[col] = None

    if not base.empty:
        base["ticker"] = base["ticker"].astype(str).str.upper()
        if "ex_date" in base.columns:
            base["ex_date"] = pd.to_datetime(base["ex_date"], errors="coerce")
        for idx, row in base.iterrows():
            ticker = safe_str(row.get("ticker")).upper()
            ex = row.get("ex_date")
            ex_key = ex.date().isoformat() if pd.notna(ex) else ""
            enrich = _ENRICH_BY_TICKER_DATE.get((ticker, ex_key))
            if not enrich and safe_str(row.get("action_type")) == "Demerger":
                enrich = _PARENT_TO_DEMERGED.get(ticker)
            if enrich:
                for key in (
                    "ratio",
                    "demerged_company",
                    "demerged_ticker",
                    "parent_company",
                    "parent_ticker",
                    "related_ticker",
                    "related_company",
                ):
                    if not safe_str(base.at[idx, key]) and enrich.get(key):
                        base.at[idx, key] = enrich[key]

    supplement_df = pd.DataFrame(SUPPLEMENT_ROWS)
    if supplement_df.empty:
        return _finalize_counterparty(base)

    supplement_df["ticker"] = supplement_df["ticker"].astype(str).str.upper()
    supplement_df["ex_date"] = pd.to_datetime(supplement_df["ex_date"], errors="coerce")
    supplement_df["record_date"] = pd.to_datetime(supplement_df["record_date"], errors="coerce")

    if base.empty:
        out = supplement_df
    else:
        out = pd.concat([base, supplement_df], ignore_index=True)

    out = out.drop_duplicates(
        subset=["ticker", "ex_date", "action_type", "demerged_ticker", "parent_ticker"],
        keep="first",
    )
    out = out.sort_values(["ex_date", "company"], ascending=[False, True]).reset_index(drop=True)
    return sort_demerger_groups(_finalize_counterparty(out))
