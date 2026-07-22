"""Governance — NSE board scan (sector filters) + shared-director graph."""

from __future__ import annotations

import streamlit as st

from stocks.core.config import (
    GOVERNANCE_DB_PATH,
    INDIA_STOCKS_DATASET,
    STRATEGY_MAX_WORKERS,
    STRATEGY_MAX_WORKERS_CAP,
    cap_tier_id_from_label,
)
from stocks.core.text_utils import safe_str
from stocks.governance.scan import run_governance_scan
from stocks.governance.service import (
    companies_with_boards,
    directors_for_ticker,
    governance_stats,
    init_governance_db,
    multi_board_directors,
    overlaps_for_ticker,
    save_company_board,
    seats_for_person,
    seed_curated_boards,
)
from stocks.listings.stocks_data import load_india_stocks
from stocks.market.fundamentals_service import apply_cap_tier_filter
from stocks.scans.results_utils import analysis_universe
from stocks.scans.scan_toolbar import (
    SCAN_BTN_COL_WIDTH,
    WORKERS_COL_WIDTH,
    base_scan_extra_widths,
    render_base_scan_filters,
    scan_toolbar_row,
)
from stocks.scans.scan_universe import resolve_cap_tier_id
from stocks.scans.stock_filters import apply_stock_filters, filter_caption_suffix


def _force_nse_session() -> None:
    """Governance is NSE-only — default the shared filter market key."""
    key = "gov_sf_market"
    if key not in st.session_state:
        st.session_state[key] = "NSE"
    elif safe_str(st.session_state.get(key)).upper() not in ("NSE", ""):
        st.session_state[key] = "NSE"


def render_governance(*, show_title: bool = True) -> None:
    init_governance_db()
    if show_title:
        st.markdown("### Governance")
    st.caption(
        "NSE-only board roster. Scan a sector, save officers to "
        f"`{GOVERNANCE_DB_PATH.name}`, then find directors shared across companies. "
        "DIN-backed curated boards are protected from weak Yahoo overwrites."
    )

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    _force_nse_session()
    stats = governance_stats()
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Companies", stats["companies"])
    with m2:
        st.metric("Directors", stats["directors"])
    with m3:
        st.metric("With DIN", stats.get("directors_with_din", 0))
    with m4:
        st.metric("Seats", stats["seats"])
    with m5:
        st.metric("On 2+ boards", stats["multi_board_directors"])

    with scan_toolbar_row(
        *base_scan_extra_widths(0.55, WORKERS_COL_WIDTH, SCAN_BTN_COL_WIDTH)
    ) as row:
        filters, cap_tier_label_ui = render_base_scan_filters(
            stocks,
            row,
            key_prefix="gov_sf",
            cap_tier_key="gov_cap_tier",
        )
        with row[4]:
            max_tickers = st.number_input(
                "Max",
                min_value=5,
                max_value=200,
                value=40,
                step=5,
                help="Quality cap — how many NSE names to fetch this run.",
            )
        with row[5]:
            workers = st.number_input(
                "Workers",
                min_value=1,
                max_value=STRATEGY_MAX_WORKERS_CAP,
                value=min(STRATEGY_MAX_WORKERS, 4),
                step=1,
            )
        with row[6]:
            run_clicked = st.button("Run", type="primary", use_container_width=True)

    # Lock to NSE regardless of playlist/market control.
    filtered = apply_stock_filters(stocks, filters)
    filtered = filtered[filtered["market"].astype(str).str.upper() == "NSE"]
    cap_tier_id = resolve_cap_tier_id(
        filters.market,
        cap_tier_id_from_label(cap_tier_label_ui),
    )
    filtered, _excluded = apply_cap_tier_filter(filtered, cap_tier_id)
    universe = analysis_universe(filtered, limit=0)

    st.caption(
        f"NSE universe **{len(universe):,}**"
        f"{filter_caption_suffix(filters)} · cap `{cap_tier_label_ui}` · "
        f"scan up to **{int(max_tickers)}**"
    )

    seed_cols = st.columns(2)
    with seed_cols[0]:
        if st.button("Load curated seed", use_container_width=True):
            n = seed_curated_boards(force=False)
            st.success(f"Added {n} curated board(s).") if n else st.info(
                "Curated boards already present."
            )
            st.rerun()
    with seed_cols[1]:
        if st.button("Reload curated seed", use_container_width=True):
            n = seed_curated_boards(force=True)
            st.success(f"Refreshed {n} curated board(s).")
            st.rerun()

    if run_clicked:
        if universe.empty:
            st.warning("No NSE stocks match the current filters.")
        else:
            progress = st.progress(0, text="Governance — starting…")

            def _progress(done: int, total: int) -> None:
                if total <= 0:
                    progress.progress(1.0, text="Done")
                    return
                progress.progress(
                    min(done / total, 1.0),
                    text=f"Board fetch {done:,}/{total:,}…",
                )

            try:
                result = run_governance_scan(
                    universe,
                    max_tickers=int(max_tickers),
                    max_workers=int(workers),
                    progress_callback=_progress,
                )
            except Exception as exc:
                progress.empty()
                st.error(f"Governance scan failed: {exc}")
                return
            progress.empty()
            st.session_state["gov_last_scan"] = result
            st.success(
                f"Scanned {result['scanned']:,} · saved {result['saved']:,} · "
                f"no officers {result['skipped_empty']:,} · "
                f"kept DIN boards {result['skipped_protected']:,} · "
                f"failed {result['failed']:,}"
            )
            st.rerun()

    last = st.session_state.get("gov_last_scan")
    if isinstance(last, dict) and last.get("saved_tickers"):
        st.caption("Last save: " + ", ".join(last["saved_tickers"][:20]))

    tab_company, tab_shared, tab_add = st.tabs(
        ["Company board", "Shared directors", "Add board"]
    )
    with tab_company:
        _render_company_tab()
    with tab_shared:
        _render_shared_tab()
    with tab_add:
        _render_add_tab()


def _render_company_tab() -> None:
    companies = companies_with_boards()
    if companies.empty:
        st.info("No boards in DB yet — run a sector scan or load curated seed.")
        return

    labels = {
        str(r.ticker): f"{r.ticker} — {r.name} ({int(r.director_count)})"
        for r in companies.itertuples()
    }
    tickers = list(labels.keys())
    default_ix = tickers.index("20MICRONS") if "20MICRONS" in tickers else 0
    choice = st.selectbox(
        "Company",
        tickers,
        index=default_ix,
        format_func=lambda t: labels[t],
        key="gov_company_pick",
    )
    board = directors_for_ticker(choice)
    if board.empty:
        st.warning("No directors stored for this ticker.")
        return

    show = board.copy()
    show["DIN"] = show["din"].fillna("")
    st.dataframe(
        show.rename(
            columns={
                "name": "Director",
                "designation": "Designation",
                "category": "Category",
                "source": "Source",
                "as_of": "As of",
                "board_count": "Boards in DB",
            }
        )[["DIN", "Director", "Designation", "Category", "As of", "Boards in DB", "Source"]],
        use_container_width=True,
        hide_index=True,
    )

    overlaps = overlaps_for_ticker(choice)
    st.markdown("#### Shared with other companies")
    if overlaps.empty:
        st.caption("No overlaps yet — scan related sector peers to find shared directors.")
    else:
        st.dataframe(
            overlaps.rename(
                columns={
                    "din": "DIN",
                    "director": "Director",
                    "here_as": "Role here",
                    "also_ticker": "Also ticker",
                    "also_company": "Also company",
                    "also_as": "Role there",
                }
            )[
                [
                    "DIN",
                    "Director",
                    "Role here",
                    "Also ticker",
                    "Also company",
                    "Role there",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


def _render_shared_tab() -> None:
    multi = multi_board_directors(min_boards=2)
    if multi.empty:
        st.info(
            "No shared directors yet. Run scans on overlapping sectors, or add "
            "boards that share a DIN / same officer name."
        )
        return

    st.dataframe(
        multi.rename(
            columns={
                "din": "DIN",
                "name": "Director",
                "board_count": "Boards",
                "tickers": "Tickers",
            }
        )[["DIN", "Director", "Boards", "Tickers"]],
        use_container_width=True,
        hide_index=True,
    )

    options = {
        f"{safe_str(r.din) or 'name'} — {r.name} ({int(r.board_count)})": str(r.person_id)
        for r in multi.itertuples()
    }
    pick = st.selectbox("Director detail", list(options.keys()), key="gov_shared_pick")
    seats = seats_for_person(options[pick])
    st.dataframe(
        seats.rename(
            columns={
                "ticker": "Ticker",
                "company_name": "Company",
                "designation": "Designation",
                "category": "Category",
                "source": "Source",
                "as_of": "As of",
            }
        )[["Ticker", "Company", "Designation", "Category", "As of", "Source"]],
        use_container_width=True,
        hide_index=True,
    )


def _render_add_tab() -> None:
    st.markdown(
        "Manual curated entry. Prefer **DIN | Name | Designation | Category** "
        "(DIN enables the strongest cross-company match)."
    )
    with st.form("gov_add_board"):
        col_a, col_b = st.columns(2)
        with col_a:
            ticker = st.text_input("Ticker (NSE)", placeholder="20MICRONS").strip().upper()
            name = st.text_input("Company name", placeholder="20 Microns Limited").strip()
            cin = st.text_input("CIN (optional)", placeholder="L99999GJ1987PLC009768").strip()
        with col_b:
            isin = st.text_input("ISIN (optional)", placeholder="INE144J01027").strip()
            as_of = st.text_input("As of (YYYY-MM-DD)", placeholder="2025-08-08").strip()
            source = st.text_input("Source", value="manual").strip() or "manual"

        st.markdown("Directors — one per line: `DIN | Name | Designation | Category`")
        raw = st.text_area(
            "Seats",
            height=180,
            placeholder=(
                "00041610 | Rajesh C. Parikh | Chairman & Managing Director | Executive\n"
                "00009900 | Swaminathan Sivaram | Independent Director | Independent"
            ),
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Save board", type="primary")

    if not submitted:
        return

    seats: list[dict] = []
    errors: list[str] = []
    for i, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3:
            errors.append(f"Line {i}: need DIN | Name | Designation [| Category]")
            continue
        seats.append(
            {
                "din": parts[0],
                "name": parts[1],
                "designation": parts[2],
                "category": parts[3] if len(parts) > 3 else "",
                "source": source,
                "as_of": as_of,
            }
        )

    if errors:
        for err in errors:
            st.error(err)
        return
    if not ticker or not name:
        st.error("Ticker and company name are required.")
        return
    if not seats:
        st.error("Add at least one director line.")
        return

    try:
        result = save_company_board(
            ticker=ticker,
            name=name,
            cin=cin or None,
            isin=isin or None,
            seats=seats,
            replace_seats=True,
            protect_din_board=False,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    st.success(f"Saved {result['ticker']} — {result['seats']} seats.")
    st.rerun()
