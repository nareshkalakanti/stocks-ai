"""NSE Sector Landscape — performance grid vs NIFTY 500."""

from __future__ import annotations

import streamlit as st

from stocks.core.config import HEADWIND_TAILWIND_MCAP_MIN_CR, INDIA_STOCKS_DATASET
from stocks.listings.classification_service import classification_sources_ok
from stocks.listings.stocks_data import load_india_stocks
from stocks.dashboards.report_html import embed_html_iframe
from stocks.scans.results_utils import analysis_universe
from stocks.strategies.intrinsic_value.service import filter_universe_by_db_mcap
from stocks.strategies.sector_landscape.html import (
    build_sector_landscape_html,
    landscape_iframe_height,
)
from stocks.strategies.sector_landscape.service import run_sector_landscape_scan


def _methodology_block() -> None:
    ok, sources = classification_sources_ok()
    source_line = ", ".join(s.replace(".db", "") for s in sources) if ok else "sqlite not found"

    with st.expander("How we built NSE sector & industry labels", expanded=False):
        st.markdown(
            f"""
**Three layers** power the taxonomy on this page:

1. **Fine NSE taxonomy** — `NSE.db` sqlite (`sector`, `industry`, `subsector`) is merged into every
   listing via `classification_service.enrich_stocks_classification()`. Sources: **{source_line}**.

2. **Display sectors** — Indian screener-style buckets via `sector_display.apply_display_sector_mapping()`.
   Example: NSE industry *Batteries* → display sector *Automobile & Ancillaries*; *CDMO* stays as
   industry under *Pharma*.

3. **Industry ≠ sector** — `effective_industry_label()` + `reconcile_industry_labels()` keep the finer
   NSE industry distinct from the broad display sector (fixes BSE/HF rows where both used to match).

**This dashboard**

- **NSE only** · stocks with SQLite market cap **≥ ₹{HEADWIND_TAILWIND_MCAP_MIN_CR:.0f} Cr**
- **Equal-weight index** per sector / industry from **1-year weekly** prices (rebased to 100)
- **Benchmark** — NIFTY 500 (`^CRSLDX` / ETF fallback) on the same timeline
- **Industry cards** use short sector + industry (e.g. *Pharma - CDMO*) for readability

Run **Scan** once; results stay in session until you scan again.
            """
        )


def render_sector_landscape() -> None:
    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    result = st.session_state.get("sl_result")

    if not result:
        st.markdown("### NSE Sector Landscape")

        nse = stocks[stocks["market"].astype(str).str.upper() == "NSE"]
        eligible, mcap_stats = filter_universe_by_db_mcap(
            analysis_universe(nse, limit=0),
            min_cr=HEADWIND_TAILWIND_MCAP_MIN_CR,
        )

        min_group = st.slider(
            "Min stocks per group",
            min_value=2,
            max_value=8,
            value=3,
            step=1,
            key="sl_min_group",
        )
        run_clicked = st.button("Run scan", type="primary", key="sl_run")

        if run_clicked:
            if eligible.empty:
                st.warning(
                    f"No NSE listings with cached market cap ≥ ₹{HEADWIND_TAILWIND_MCAP_MIN_CR:.0f} Cr. "
                    "Run PEAD or Refresh prices on Holdings first."
                )
                return

            progress = st.progress(0, text="Fetching 1Y weekly prices…")

            def _progress(done: int, total: int) -> None:
                progress.progress(done / max(total, 1), text=f"Scanning {done}/{total}…")

            try:
                scan_result = run_sector_landscape_scan(
                    eligible,
                    min_mcap_cr=HEADWIND_TAILWIND_MCAP_MIN_CR,
                    min_group_size=min_group,
                    progress_callback=_progress,
                )
            except Exception as exc:
                progress.empty()
                st.error(f"Scan failed: {exc}")
                return
            progress.empty()

            if scan_result.get("error"):
                st.error(scan_result["error"])
                return

            st.session_state.sl_result = {**scan_result, "min_group_size": min_group}
            st.rerun()

        st.info("Click **Run scan** to build the sector landscape (first run may take a few minutes).")
        return

    st.markdown("### NSE Sector Landscape")

    if result.get("error"):
        st.error(result["error"])
        return

    n_sectors = len(result.get("sector_groups") or [])
    n_industries = len(result.get("industry_groups") or [])
    min_group = int(result.get("min_group_size", 3))

    with st.expander("Scan settings", expanded=False):
        new_min = st.slider(
            "Min stocks per group",
            min_value=2,
            max_value=8,
            value=min_group,
            step=1,
            key="sl_min_group_rerun",
        )
        if st.button("Run scan again", type="primary", key="sl_rerun"):
            nse = stocks[stocks["market"].astype(str).str.upper() == "NSE"]
            eligible, _ = filter_universe_by_db_mcap(
                analysis_universe(nse, limit=0),
                min_cr=HEADWIND_TAILWIND_MCAP_MIN_CR,
            )
            if eligible.empty:
                st.warning(
                    f"No NSE listings with cached market cap ≥ ₹{HEADWIND_TAILWIND_MCAP_MIN_CR:.0f} Cr. "
                    "Run PEAD or Refresh prices on Holdings first."
                )
            else:
                progress = st.progress(0, text="Fetching 1Y weekly prices…")

                def _progress(done: int, total: int) -> None:
                    progress.progress(done / max(total, 1), text=f"Scanning {done}/{total}…")

                try:
                    scan_result = run_sector_landscape_scan(
                        eligible,
                        min_mcap_cr=HEADWIND_TAILWIND_MCAP_MIN_CR,
                        min_group_size=new_min,
                        progress_callback=_progress,
                    )
                except Exception as exc:
                    progress.empty()
                    st.error(f"Scan failed: {exc}")
                else:
                    progress.empty()
                    if scan_result.get("error"):
                        st.error(scan_result["error"])
                    else:
                        st.session_state.sl_result = {**scan_result, "min_group_size": new_min}
                        st.rerun()

    embed_html = build_sector_landscape_html(
        result,
        title="NSE Sector Landscape",
        standalone=False,
    )
    group_count = n_sectors + n_industries
    embed_html_iframe(
        embed_html,
        height=landscape_iframe_height(group_count, panel_open=True),
    )
