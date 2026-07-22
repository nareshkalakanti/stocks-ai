"""Alpha Hide — SARVADA-style multi-bagger discovery (phases + 5 ingredients)."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import (
    ALPHA_HIDE_MAX_EV_EBITDA,
    ALPHA_HIDE_MAX_PE,
    ALPHA_HIDE_MCAP_MAX_CR,
    ALPHA_HIDE_MCAP_MIN_CR,
    ALPHA_HIDE_MIN_DRAWDOWN_PCT,
    ALPHA_HIDE_MIN_INGREDIENTS,
    ALPHA_HIDE_MIN_PROMOTER_DELTA,
    ALPHA_HIDE_MIN_SALES_CAGR,
    ALPHA_HIDE_PHASE1_MAX_CR,
    ALPHA_HIDE_PHASE2_MAX_CR,
)
from stocks.strategies.earnings.strategy import NET_INCOME_FIELDS
from stocks.strategies.inst_entry.strategy import _sales_cagr_pct
from stocks.strategies.micro_value.strategy import price_to_sales
from stocks.strategies.valuation_formula.strategy import _first_row


def recognition_phase(market_cap_cr: float | None) -> str | None:
    """Phase I Neglect / II Validation / III Adoption (Raas SARVADA bands)."""
    if market_cap_cr is None or pd.isna(market_cap_cr):
        return None
    cap = float(market_cap_cr)
    if cap < ALPHA_HIDE_MCAP_MIN_CR or cap > ALPHA_HIDE_MCAP_MAX_CR:
        # Still tag adoption if in 1k–5k for display of near-misses.
        if ALPHA_HIDE_PHASE2_MAX_CR < cap <= 5000:
            return "III"
        return None
    if cap <= ALPHA_HIDE_PHASE1_MAX_CR:
        return "I"
    if cap <= ALPHA_HIDE_PHASE2_MAX_CR:
        return "II"
    return None


def in_alpha_hide_universe(market_cap_cr: float | None) -> bool:
    if market_cap_cr is None or pd.isna(market_cap_cr):
        return False
    cap = float(market_cap_cr)
    return ALPHA_HIDE_MCAP_MIN_CR <= cap <= ALPHA_HIDE_MCAP_MAX_CR


def _drawdown_from_high(info: dict | None, price: float | None) -> float | None:
    info = info or {}
    high = info.get("fiftyTwoWeekHigh")
    px = price
    if px is None:
        raw = info.get("regularMarketPrice") or info.get("currentPrice")
        px = float(raw) if raw is not None and not pd.isna(raw) else None
    if high is None or pd.isna(high) or px is None or float(high) <= 0:
        return None
    return round((1.0 - float(px) / float(high)) * 100, 1)


def _profit_positive(info: dict | None, financials: pd.DataFrame | None) -> bool | None:
    info = info or {}
    ni = info.get("netIncomeToCommon")
    if ni is not None and not pd.isna(ni):
        return float(ni) > 0
    series = _first_row(financials, NET_INCOME_FIELDS)
    if series is None or series.empty:
        return None
    return float(series.sort_index(ascending=False).iloc[0]) > 0


def _sales_acceleration(
    financials: pd.DataFrame | None,
    sales_cagr: float | None,
) -> bool | None:
    """Latest YoY sales growth above multi-year CAGR → soft inflection proxy."""
    from stocks.strategies.valuation_formula.strategy import REVENUE_FIELDS

    rev = _first_row(financials, REVENUE_FIELDS)
    if rev is None or rev.empty or len(rev.dropna()) < 2:
        return None
    s = rev.dropna().astype(float).sort_index(ascending=False)
    latest, prior = float(s.iloc[0]), float(s.iloc[1])
    if prior <= 0:
        return None
    yoy = (latest / prior - 1.0) * 100
    if sales_cagr is None or pd.isna(sales_cagr):
        return yoy >= ALPHA_HIDE_MIN_SALES_CAGR
    return yoy >= float(sales_cagr)


def compute_alpha_hide_metrics(
    info: dict | None,
    financials: pd.DataFrame | None = None,
    *,
    market_cap_cr: float | None = None,
    price: float | None = None,
) -> dict:
    info = info or {}
    mcap_raw = info.get("marketCap")
    mcap = float(mcap_raw) if mcap_raw is not None and not pd.isna(mcap_raw) else None
    if market_cap_cr is not None and not pd.isna(market_cap_cr) and mcap is None:
        mcap = float(market_cap_cr) * 1e7

    pe = info.get("trailingPE")
    pe_f = round(float(pe), 1) if pe is not None and not pd.isna(pe) else None
    ev = info.get("enterpriseToEbitda")
    ev_f = round(float(ev), 2) if ev is not None and not pd.isna(ev) else None
    sales_cagr = _sales_cagr_pct(financials)

    return {
        "phase": recognition_phase(market_cap_cr),
        "price_to_sales": price_to_sales(info, financials, market_cap=mcap),
        "pe_ratio": pe_f,
        "ev_ebitda": ev_f,
        "sales_cagr": sales_cagr,
        "drawdown_pct": _drawdown_from_high(info, price),
        "profit_positive": _profit_positive(info, financials),
        "sales_accel": _sales_acceleration(financials, sales_cagr),
    }


def ingredient_checks(row: pd.Series | dict) -> tuple[list[str], list[str], dict]:
    """
    Five SARVADA ingredients (quant proxies).

    Must-pass pair for scoring: Valuation + Growth when enough ingredients hit.
    """
    passed: list[str] = []
    failed: list[str] = []
    flags: dict = {}

    pe = pd.to_numeric(row.get("pe_ratio"), errors="coerce")
    ev = pd.to_numeric(row.get("ev_ebitda"), errors="coerce")
    val_ok = (
        (pe is not None and not pd.isna(pe) and 0 < float(pe) < ALPHA_HIDE_MAX_PE)
        or (
            ev is not None
            and not pd.isna(ev)
            and 0 < float(ev) < ALPHA_HIDE_MAX_EV_EBITDA
        )
    )
    if val_ok:
        passed.append("Valuation")
    else:
        failed.append("Valuation")
    flags["ing_valuation"] = val_ok

    dd = pd.to_numeric(row.get("drawdown_pct"), errors="coerce")
    contrarian_ok = (
        dd is not None and not pd.isna(dd) and float(dd) >= ALPHA_HIDE_MIN_DRAWDOWN_PCT
    )
    if contrarian_ok:
        passed.append("Contrarian")
    else:
        failed.append("Contrarian")
    flags["ing_contrarian"] = contrarian_ok

    cagr = pd.to_numeric(row.get("sales_cagr"), errors="coerce")
    profit_ok = row.get("profit_positive") is True
    growth_ok = (
        cagr is not None
        and not pd.isna(cagr)
        and float(cagr) >= ALPHA_HIDE_MIN_SALES_CAGR
        and profit_ok
    )
    if growth_ok:
        passed.append("Growth")
    else:
        failed.append("Growth")
    flags["ing_growth"] = growth_ok

    accel = row.get("sales_accel")
    demerger = bool(row.get("demerger_flag"))
    inflection_ok = (accel is True) or demerger
    if inflection_ok:
        passed.append("Inflection")
    else:
        failed.append("Inflection")
    flags["ing_inflection"] = inflection_ok

    prom_delta = pd.to_numeric(row.get("promoter_pct_delta"), errors="coerce")
    inst_delta = pd.to_numeric(row.get("institutional_pct_delta"), errors="coerce")
    promoter_ok = (
        prom_delta is not None
        and not pd.isna(prom_delta)
        and float(prom_delta) >= ALPHA_HIDE_MIN_PROMOTER_DELTA
    ) or (
        inst_delta is not None
        and not pd.isna(inst_delta)
        and float(inst_delta) > 0
    )
    if promoter_ok:
        passed.append("Promoter")
    else:
        failed.append("Promoter")
    flags["ing_promoter"] = promoter_ok

    return passed, failed, flags


def score_alpha_hide(df: pd.DataFrame) -> pd.DataFrame:
    """
    Keep Phase I/II names with enough ingredients; Valuation+Growth required.

    Rank cheaper valuation then higher sales CAGR (discovery order, not blend).
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df

    out = df.copy()
    keep: list[bool] = []
    labels: list[str] = []
    n_pass_list: list[int] = []
    for _, row in out.iterrows():
        phase = safe_phase(row.get("phase"))
        in_uni = in_alpha_hide_universe(
            pd.to_numeric(row.get("market_cap_cr"), errors="coerce")
        )
        passed, failed, flags = ingredient_checks(row)
        n = len(passed)
        labels.append(f"{n}/5")
        n_pass_list.append(n)
        must = flags["ing_valuation"] and flags["ing_growth"]
        keep.append(
            bool(
                in_uni
                and phase in ("I", "II")
                and n >= ALPHA_HIDE_MIN_INGREDIENTS
                and must
            )
        )

    # Apply ingredient flags as columns
    val_f, con_f, gro_f, inf_f, pro_f = [], [], [], [], []
    for _, row in out.iterrows():
        _, _, flags = ingredient_checks(row)
        val_f.append(flags["ing_valuation"])
        con_f.append(flags["ing_contrarian"])
        gro_f.append(flags["ing_growth"])
        inf_f.append(flags["ing_inflection"])
        pro_f.append(flags["ing_promoter"])

    out["ah_ingredients"] = labels
    out["ah_n_pass"] = n_pass_list
    out["ing_valuation"] = val_f
    out["ing_contrarian"] = con_f
    out["ing_growth"] = gro_f
    out["ing_inflection"] = inf_f
    out["ing_promoter"] = pro_f
    out = out[keep].copy()
    if out.empty:
        return out

    # Sort key: prefer cheaper PE/EV, then growth
    out["_val_rank"] = out.apply(_valuation_sort_key, axis=1)
    out = out.sort_values(
        ["phase", "ah_n_pass", "_val_rank", "sales_cagr"],
        ascending=[True, False, True, False],
        na_position="last",
    ).reset_index(drop=True)
    out = out.drop(columns=["_val_rank"], errors="ignore")
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def safe_phase(val) -> str:
    return str(val or "").strip().upper()


def _valuation_sort_key(row: pd.Series) -> float:
    pe = pd.to_numeric(row.get("pe_ratio"), errors="coerce")
    ev = pd.to_numeric(row.get("ev_ebitda"), errors="coerce")
    pts = pd.to_numeric(row.get("price_to_sales"), errors="coerce")
    candidates = []
    if pe is not None and not pd.isna(pe) and float(pe) > 0:
        candidates.append(float(pe))
    if ev is not None and not pd.isna(ev) and float(ev) > 0:
        candidates.append(float(ev))
    if pts is not None and not pd.isna(pts) and float(pts) > 0:
        candidates.append(float(pts) * 10)  # scale P/S toward PE-ish
    return min(candidates) if candidates else 999.0


def ten_bagger_math_caption(
    *,
    sales_cagr: float = 20.0,
    pe_entry: float = 8.0,
    pe_exit: float = 20.0,
    years: int = 5,
) -> str:
    """Raas-style illustration: (1+g)^n × (PE_exit/PE_entry)."""
    scale = (1 + sales_cagr / 100) ** years
    rerate = pe_exit / pe_entry if pe_entry else 0
    total = scale * rerate
    return (
        f"10× math (illustrative): ({1 + sales_cagr / 100:.2f})^{years} × "
        f"({pe_exit:g}/{pe_entry:g}) ≈ {scale:.2f} × {rerate:.2f} ≈ **{total:.1f}×** "
        "(+ catalyst → 8–10× territory)."
    )


def format_alpha_hide_export_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        ("rank", "rank"),
        ("ticker", "ticker"),
        ("name", "name"),
        ("phase", "phase"),
        ("ah_ingredients", "ingredients"),
        ("pe_ratio", "pe"),
        ("ev_ebitda", "ev_ebitda"),
        ("price_to_sales", "mcap_to_sales"),
        ("sales_cagr", "sales_cagr"),
        ("drawdown_pct", "drawdown_pct"),
        ("promoter_pct_delta", "promoter_delta_pp"),
        ("institutional_pct_delta", "inst_delta_pp"),
        ("demerger_flag", "demerger"),
        ("market_cap_cr", "market_cap_cr"),
        ("sector", "sector"),
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=[a for _, a in cols])
    out = pd.DataFrame()
    for src, alias in cols:
        out[alias] = df[src] if src in df.columns else pd.NA
    return out


def alpha_hide_caption() -> str:
    return (
        f"**Alpha Hide** (SARVADA-style) — Phase I/II under ₹{ALPHA_HIDE_MCAP_MAX_CR:g} Cr. "
        f"Ingredients: **PE&lt;{ALPHA_HIDE_MAX_PE:g} or EV/EBITDA&lt;{ALPHA_HIDE_MAX_EV_EBITDA:g}**, "
        f"drawdown≥{ALPHA_HIDE_MIN_DRAWDOWN_PCT:g}%, sales CAGR≥{ALPHA_HIDE_MIN_SALES_CAGR:g}%, "
        f"inflection (accel/demerger), promoter/inst buying. "
        f"Need ≥{ALPHA_HIDE_MIN_INGREDIENTS} incl. Valuation+Growth. "
        + ten_bagger_math_caption()
    )


__all__ = [
    "alpha_hide_caption",
    "compute_alpha_hide_metrics",
    "format_alpha_hide_export_df",
    "in_alpha_hide_universe",
    "ingredient_checks",
    "recognition_phase",
    "score_alpha_hide",
    "ten_bagger_math_caption",
]
