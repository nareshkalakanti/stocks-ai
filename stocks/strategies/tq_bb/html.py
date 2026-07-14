"""Interactive TQ / BB strategy HTML — expand row shows Google News only."""

from __future__ import annotations

import pandas as pd

from stocks.dashboards.interactive_table import build_interactive_section, wrap_interactive_page


_TQ_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "crossover_type", "label": "Crossover", "fmt": "text"},
    {"id": "timeframe", "label": "TF", "fmt": "text"},
    {"id": "date", "label": "Signal", "fmt": "date"},
]

_BB_JS_COLS = [
    {"id": "company", "label": "Stock", "fmt": "company"},
    {"id": "market", "label": "Mkt", "fmt": "text"},
    {"id": "sector", "label": "Sector", "fmt": "text"},
    {"id": "price", "label": "Price", "fmt": "num2"},
    {"id": "signal", "label": "Signal", "fmt": "text"},
    {"id": "timeframe", "label": "TF", "fmt": "text"},
    {"id": "date", "label": "Date", "fmt": "date"},
]


def build_strategy_dashboard_html(
    *,
    tq_df: pd.DataFrame | None = None,
    bb_df: pd.DataFrame | None = None,
    timeframe: str = "weekly",
    include_tq: bool = True,
    include_bb: bool = False,
    title: str = "Strategy scan",
    subtitle: str | None = None,
    standalone: bool = True,
) -> str:
    sections: list[str] = []
    if include_tq:
        sections.append(
            build_interactive_section(
                "tq",
                f"TQ — {timeframe} trend + RS vs NIFTY",
                tq_df if tq_df is not None else pd.DataFrame(),
                _TQ_JS_COLS,
                kind="tq",
                open_section=True,
            )
        )
    if include_bb:
        sections.append(
            build_interactive_section(
                "bb",
                f"Bollinger Bands ({timeframe})",
                bb_df if bb_df is not None else pd.DataFrame(),
                _BB_JS_COLS,
                kind="bb",
                open_section=not include_tq,
            )
        )

    return wrap_interactive_page(
        title=title,
        sections_html="".join(sections),
        standalone=standalone,
    )


def strategy_iframe_height(
    *,
    tq_rows: int = 0,
    bb_rows: int = 0,
    sections: int = 1,
) -> int:
    rows = max(tq_rows, bb_rows)
    base = 360 + sections * 120
    return min(2200, max(560, base + min(rows, 50) * 22))
