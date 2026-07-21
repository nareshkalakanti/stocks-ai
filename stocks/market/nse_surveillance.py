"""NSE ASM / GSM surveillance lists + distress seed tickers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pandas as pd
import requests

from stocks.core.config import BASE_DIR
from stocks.core.log_service import log_error
from stocks.core.text_utils import safe_str

_SEED_PATH = BASE_DIR / "data" / "distress_seed.json"
_CACHE_PATH = BASE_DIR / "data" / "nse_surveillance_cache.json"
_TIMEOUT_SEC = 15
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_POCKETFUL_URLS = (
    "https://www.pocketful.in/tools/asm-gsm-list",
    "https://www.pocketful.in/tools/asm-list",
    "https://www.pocketful.in/tools/gsm-list",
)

_NSE_CSV_URLS = (
    "https://nsearchives.nseindia.com/content/equities/LongTerm_ASM.csv",
    "https://nsearchives.nseindia.com/content/equities/ShortTerm_ASM.csv",
    "https://nsearchives.nseindia.com/content/equities/GSMList.csv",
)


def load_distress_seed_tickers() -> list[str]:
    """Always-on monitoring set (user-provided reverse-engineering anchors)."""
    if not _SEED_PATH.exists():
        return []
    try:
        payload = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    tickers = payload.get("tickers") if isinstance(payload, dict) else payload
    if not isinstance(tickers, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in tickers:
        t = safe_str(raw).upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def _parse_surveillance_csv(text: str, *, default_type: str) -> list[dict]:
    rows: list[dict] = []
    if not text or not text.strip():
        return rows
    try:
        df = pd.read_csv(pd.io.common.StringIO(text))
    except Exception:
        return rows
    if df.empty:
        return rows
    cols = {str(c).strip().lower(): c for c in df.columns}
    sym_col = next(
        (cols[k] for k in ("symbol", "scrip code", "scrip", "ticker") if k in cols),
        None,
    )
    if sym_col is None:
        return rows
    stage_col = next(
        (cols[k] for k in ("asm stage", "stage", "gsm stage") if k in cols),
        None,
    )
    name_col = next(
        (cols[k] for k in ("company name", "security name", "name") if k in cols),
        None,
    )
    for _, row in df.iterrows():
        ticker = safe_str(row.get(sym_col)).upper()
        if not ticker or ticker in {"SYMBOL", "SCRIP"}:
            continue
        stage = safe_str(row.get(stage_col)) if stage_col else ""
        name = safe_str(row.get(name_col)) if name_col else ""
        kind = _classify_surv_type(default_type, stage)
        rows.append(
            {
                "ticker": ticker,
                "name": name or None,
                "surv_type": kind,
                "surv_stage": stage or None,
                "source": "nse",
            }
        )
    return rows


def _classify_surv_type(default_type: str, stage: str) -> str:
    stage_u = (stage or "").upper()
    if "GSM" in stage_u:
        return "GSM"
    if "LTASM" in stage_u or "LONG" in stage_u:
        return "LTASM"
    if "STASM" in stage_u or "SHORT" in stage_u:
        return "STASM"
    if "ASM" in stage_u:
        return "ASM"
    return default_type


def _parse_pocketful_html(text: str) -> list[dict]:
    """Parse ASM/GSM HTML tables from Pocketful tools pages."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(text, "html.parser")
    rows: list[dict] = []
    for table in soup.find_all("table"):
        header: list[str] = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if not cells:
                continue
            upper = [c.upper() for c in cells]
            if "SYMBOL" in upper and ("TYPE" in upper or "STAGE" in upper):
                header = upper
                continue
            if not header or len(cells) < 4:
                continue
            try:
                sym_i = header.index("SYMBOL")
                type_i = header.index("TYPE") if "TYPE" in header else 3
                stage_i = header.index("STAGE") if "STAGE" in header else 4
                name_i = header.index("COMPANY NAME") if "COMPANY NAME" in header else 0
            except ValueError:
                continue
            if max(sym_i, type_i, stage_i, name_i) >= len(cells):
                continue
            ticker = safe_str(cells[sym_i]).upper()
            if not re.fullmatch(r"[A-Z0-9]{1,20}", ticker):
                continue
            typ = safe_str(cells[type_i]).upper() or "ASM"
            stage = safe_str(cells[stage_i])
            name = safe_str(cells[name_i])
            rows.append(
                {
                    "ticker": ticker,
                    "name": name or None,
                    "surv_type": _classify_surv_type(typ, f"{typ} {stage}"),
                    "surv_stage": stage or None,
                    "source": "pocketful",
                }
            )
    return rows


def _fetch_pocketful_rows(session: requests.Session) -> list[dict]:
    collected: list[dict] = []
    for url in _POCKETFUL_URLS:
        try:
            resp = session.get(url, timeout=_TIMEOUT_SEC)
            if resp.status_code != 200 or len(resp.content) < 500:
                continue
            collected.extend(_parse_pocketful_html(resp.text))
        except Exception as exc:
            try:
                log_error("pocketful_surveillance_fetch_failed", str(exc), url=url)
            except Exception:
                pass
    return collected


def _fetch_nse_csv_rows(session: requests.Session) -> list[dict]:
    collected: list[dict] = []
    for url in _NSE_CSV_URLS:
        default = "GSM" if "GSM" in url.upper() else "ASM"
        if "LongTerm" in url or "Long" in url:
            default = "LTASM"
        elif "ShortTerm" in url or "Short" in url:
            default = "STASM"
        try:
            resp = session.get(
                url,
                timeout=8,
                headers={"Referer": "https://www.nseindia.com/"},
            )
            if resp.status_code != 200 or len(resp.content) < 40:
                continue
            collected.extend(_parse_surveillance_csv(resp.text, default_type=default))
        except Exception:
            continue
    return collected


def _load_cache() -> list[dict]:
    if not _CACHE_PATH.exists():
        return []
    try:
        payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else None
    return list(rows) if isinstance(rows, list) else []


def _save_cache(rows: list[dict]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps(
                {
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "rows": rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        try:
            log_error("surveillance_cache_save_failed", str(exc))
        except Exception:
            pass


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    """Prefer exchange labels, then pocketful, then other."""
    rank = {"nse": 0, "pocketful": 1, "seed": 2, "proxy": 3}
    by_ticker: dict[str, dict] = {}
    ordered = sorted(rows, key=lambda r: rank.get(str(r.get("source")), 9))
    for row in ordered:
        t = row["ticker"]
        if t not in by_ticker:
            by_ticker[t] = row
    return list(by_ticker.values())


def fetch_nse_surveillance_rows(*, force: bool = False) -> list[dict]:
    """
    Best-effort ASM/GSM download (Pocketful HTML, then NSE CSV).

    Falls back to on-disk cache when live sources are unreachable.
    """
    cached = _load_cache()
    if cached and not force:
        try:
            payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            fetched = pd.Timestamp(payload.get("fetched_at"))
            age_h = (pd.Timestamp.utcnow() - fetched.tz_localize(None)).total_seconds() / 3600
            if age_h < 24:
                return cached
        except Exception:
            pass

    session = _session()
    collected: list[dict] = []
    collected.extend(_fetch_pocketful_rows(session))
    if len(collected) < 20:
        collected.extend(_fetch_nse_csv_rows(session))

    if collected:
        rows = _dedupe_rows(collected)
        _save_cache(rows)
        return rows
    return cached


def distress_proxy_rows_from_pead_cache(*, limit: int = 400) -> list[dict]:
    """
    Expand the universe from local PEAD2 cache when exchange lists are thin.

    Picks names that look like the seed set: earnings stress and/or stressed PE,
    optionally with sales holding up better than EPS (early turnaround tell).
    """
    try:
        from stocks.core.database import load_all_pead2_cache_payloads
        from stocks.strategies.pead2.service import _expand_lag_rows
    except Exception:
        return []

    try:
        blobs = load_all_pead2_cache_payloads(max_hours=999999)
    except Exception:
        return []
    if not blobs:
        return []

    rows = _expand_lag_rows(blobs, quarter_lag=0)
    if not rows:
        return []

    scored: list[tuple[float, dict]] = []
    for row in rows:
        ticker = safe_str(row.get("ticker")).upper()
        if not ticker:
            continue
        eps = pd.to_numeric(row.get("eps_yoy"), errors="coerce")
        sales = pd.to_numeric(row.get("sales_yoy"), errors="coerce")
        pe = pd.to_numeric(row.get("forward_pe"), errors="coerce")
        if pe is None or pd.isna(pe):
            pe = pd.to_numeric(row.get("pe_ratio"), errors="coerce")
        returns = pd.to_numeric(row.get("returns_pct"), errors="coerce")

        distress = False
        weight = 0.0
        if eps is not None and not pd.isna(eps) and float(eps) < 0:
            distress = True
            weight += min(abs(float(eps)), 100) / 100.0
        if pe is not None and not pd.isna(pe) and (float(pe) >= 80 or float(pe) >= 900):
            distress = True
            weight += 0.5
        if sales is not None and not pd.isna(sales) and float(sales) < -20:
            distress = True
            weight += 0.2
        if not distress:
            continue
        # Prefer sales holding vs EPS collapse / positive tape (seed-like recovery).
        if (
            sales is not None
            and not pd.isna(sales)
            and eps is not None
            and not pd.isna(eps)
            and float(sales) > float(eps) + 5
        ):
            weight += 0.8
        if returns is not None and not pd.isna(returns) and float(returns) > 0:
            weight += 0.4
        scored.append(
            (
                weight,
                {
                    "ticker": ticker,
                    "name": safe_str(row.get("name")) or None,
                    "surv_type": "PROXY",
                    "surv_stage": "distress-like",
                    "source": "proxy",
                },
            )
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict] = []
    seen: set[str] = set()
    for _, row in scored:
        t = row["ticker"]
        if t in seen:
            continue
        seen.add(t)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def surveillance_universe_frame(
    listings: pd.DataFrame,
    *,
    force_refresh: bool = False,
    include_seed: bool = True,
    include_proxy: bool = True,
) -> pd.DataFrame:
    """
    Listings on surveillance lists, distress seeds, and (if needed) PEAD proxies.

    Seed tickers are always retained for monitoring.
    """
    if listings is None or listings.empty or "ticker" not in listings.columns:
        return pd.DataFrame()

    work = listings.drop_duplicates("ticker").copy()
    work["ticker"] = work["ticker"].astype(str).str.strip().str.upper()

    surv_rows = fetch_nse_surveillance_rows(force=force_refresh)
    # If exchange lists are thin, expand with distress-like PEAD cache names.
    if include_proxy and len(surv_rows) < 80:
        surv_rows = _dedupe_rows(surv_rows + distress_proxy_rows_from_pead_cache())

    surv_df = (
        pd.DataFrame(surv_rows)
        if surv_rows
        else pd.DataFrame(columns=["ticker", "name", "surv_type", "surv_stage", "source"])
    )
    if not surv_df.empty:
        surv_df["ticker"] = surv_df["ticker"].astype(str).str.strip().str.upper()

    seed = load_distress_seed_tickers() if include_seed else []
    seed_df = pd.DataFrame(
        {
            "ticker": seed,
            "surv_type": ["SEED"] * len(seed),
            "surv_stage": ["monitor"] * len(seed),
            "source": ["seed"] * len(seed),
        }
    )

    flags = pd.concat([surv_df, seed_df], ignore_index=True) if len(seed_df) else surv_df
    if flags.empty:
        return pd.DataFrame()

    flags["_rank"] = flags["source"].map(
        {"nse": 0, "pocketful": 1, "seed": 2, "proxy": 3}
    ).fillna(9)
    flags = flags.sort_values(["ticker", "_rank"]).drop_duplicates("ticker", keep="first")
    flags = flags.drop(columns=["_rank"])

    merged = work.merge(
        flags[["ticker", "surv_type", "surv_stage", "source"]],
        on="ticker",
        how="inner",
    )
    if seed:
        have = set(merged["ticker"].astype(str).str.upper())
        missing = [t for t in seed if t not in have]
        if missing:
            extra = work[work["ticker"].isin(missing)].copy()
            extra["surv_type"] = "SEED"
            extra["surv_stage"] = "monitor"
            extra["source"] = "seed"
            merged = pd.concat([merged, extra], ignore_index=True)
    return merged.drop_duplicates("ticker").reset_index(drop=True)


__all__ = [
    "distress_proxy_rows_from_pead_cache",
    "fetch_nse_surveillance_rows",
    "load_distress_seed_tickers",
    "surveillance_universe_frame",
]
