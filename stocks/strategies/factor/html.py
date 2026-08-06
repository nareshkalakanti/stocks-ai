"""HTML report for Chen-style factor composite scan."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

FACTOR_JS_COLS = [
    {"id": "factor_rank", "label": "#", "fmt": "int"},
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "composite", "label": "Composite", "fmt": "num3"},
    {"id": "mom_21", "label": "Mom 21d", "fmt": "pct2"},
    {"id": "value_proxy", "label": "Value", "fmt": "num3"},
    {"id": "vol_factor", "label": "Vol", "fmt": "num3"},
    {"id": "sector_rel_mom", "label": "Sect-rel", "fmt": "num3"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
]

_EXTRA = (
    "composite",
    "mom_21",
    "mom_63",
    "mom_126",
    "value_proxy",
    "vol_factor",
    "sector_rel_mom",
    "mom_21_z",
    "value_proxy_z",
    "vol_factor_z",
    "sector_rel_mom_z",
    "price",
    "factor_rank",
    "score",
)


def _fmt_ic(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    try:
        return f"{float(val):+.3f}"
    except (TypeError, ValueError):
        return "—"


def build_factor_html(
    df: pd.DataFrame,
    *,
    standalone: bool = True,
    validation: dict | None = None,
) -> str:
    stats = validation or dict(getattr(df, "attrs", {}) or {}).get("factor_validation") or {}
    bits = [
        f"train IC {_fmt_ic(stats.get('train_mean_ic'))}",
        f"test IC {_fmt_ic(stats.get('test_mean_ic'))}",
        f"test ICIR {_fmt_ic(stats.get('test_icir'))}",
        f"rand {_fmt_ic(stats.get('random_baseline_ic'))}",
    ]
    title = (
        "Factor — composite (mom + value − vol + sector-rel) · "
        + " · ".join(bits)
    )
    if df is None:
        work = pd.DataFrame()
    elif isinstance(df, pd.DataFrame):
        work = df.copy()
    else:
        work = pd.DataFrame(df)
    # pct2 expects percent units for mom_21 (stored as fraction)
    if not work.empty and "mom_21" in work.columns:
        mom = work["mom_21"]
        if isinstance(mom, pd.DataFrame):
            mom = mom.iloc[:, 0]
        work = work.copy()
        work["mom_21"] = pd.to_numeric(mom, errors="coerce") * 100.0

    section = build_interactive_section(
        "factor",
        title,
        work,
        FACTOR_JS_COLS,
        kind="factor",
        open_section=True,
        expand_hint="Click row — website · quarterly · TV",
        fetch_news=True,
        extra_cols=_EXTRA,
        meta_label="stocks",
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def factor_iframe_height(row_count: int) -> int:
    return min(4800, max(620, 420 + min(row_count, 120) * 24))
