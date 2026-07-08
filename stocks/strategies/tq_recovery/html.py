"""HTML report for TQ W52 recovery scan — click row for snapshot + quarterly data."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page

TQ_RECOVERY_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "tq_w52", "label": "TQ W52", "fmt": "num4"},
    {"id": "tq_w52_prev", "label": "Prev", "fmt": "num4"},
    {"id": "tq_change", "label": "Δ W52", "fmt": "num4"},
    {"id": "tq_zone", "label": "Zone", "fmt": "text"},
    {"id": "short_term_rs", "label": "RS 13W", "fmt": "num4"},
    {"id": "recovery_score", "label": "Score", "fmt": "score"},
    {"id": "date", "label": "Week", "fmt": "date"},
]


def build_tq_recovery_html(
    df: pd.DataFrame,
    *,
    title: str = "TQ W52 Recovery",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    section = build_interactive_section(
        "tqrec",
        "TQ W52 — red → yellow (below zero)",
        df,
        TQ_RECOVERY_JS_COLS,
        kind="recovery",
        open_section=True,
    )
    return wrap_interactive_page(
        title="",
        sections_html=section,
        standalone=standalone,
    )


def tq_recovery_iframe_height(row_count: int) -> int:
    return min(2200, max(560, 400 + min(row_count, 50) * 22))
