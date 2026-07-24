"""Governance — NSE board scan (index universes) + shared-director graph."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.config import (
    CAP_TIERS,
    INDIA_STOCKS_DATASET,
    STRATEGY_MAX_WORKERS,
    STRATEGY_MAX_WORKERS_CAP,
    cap_tier_id_from_label,
    cap_tier_labels,
)
from stocks.core.text_utils import safe_str
from stocks.governance.scan import pending_governance_jobs, run_governance_scan
from stocks.market.fundamentals_service import filter_listings_by_cap_tier
from stocks.governance.service import (
    clear_all_governance_data,
    clear_scan_log,
    clear_scan_log_for_tickers,
    companies_with_boards,
    directors_for_ticker,
    enrich_governance_company_classification,
    governance_stats,
    holdings_governance_coverage,
    init_governance_db,
    multi_board_directors,
    overlaps_for_ticker,
    save_company_board,
    seats_for_person,
    seed_curated_boards,
)
from stocks.listings.stocks_data import load_india_stocks, market_options
from stocks.market.nse_index_constituents import (
    NIFTY_INDEXES,
    ensure_all_nifty_indexes,
)
from stocks.scans.holdings_playlist import (
    HOLDINGS_PLAYLIST_LABEL,
    holdings_playlist_listings,
)
from stocks.scans.results_utils import analysis_universe
from stocks.scans.scan_playlists import format_market_option
from stocks.scans.stock_filters import StockFilters, apply_stock_filters
from stocks.market.nse_sme_listings import NSE_SME_MARKET

_UNDER5K_HOLDINGS_LABEL = "≤5k + Holdings"
_DEFAULT_GOV_MARKET = "All"
_DEFAULT_GOV_CAP_LABEL = "≤ 5,000 Cr (0–5k)"
_BATCH_SIZE = 20
_NSE_GOV_MARKETS = frozenset({"NSE", "NSE SME"})


def _gov_cap_tier_id() -> str:
    label = safe_str(st.session_state.get("gov_cap_tier")) or _DEFAULT_GOV_CAP_LABEL
    return cap_tier_id_from_label(label)


def _gov_market_options(stocks: pd.DataFrame) -> list[str]:
    """Same Market list as other scan pages, plus ≤5k + Holdings near the top."""
    # All · Holdings · Nifty… · D&S · … · NSE · BSE · …
    base = market_options(stocks, include_scan_playlists=True)
    opts: list[str] = []
    if "All" in base:
        opts.append("All")
    if _UNDER5K_HOLDINGS_LABEL not in opts:
        opts.append(_UNDER5K_HOLDINGS_LABEL)
    for m in base:
        if m not in opts:
            opts.append(m)
    return opts


def _union_universes(*frames: pd.DataFrame) -> pd.DataFrame:
    parts = [f for f in frames if f is not None and not f.empty]
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)
    if "ticker" not in out.columns:
        return out
    out["ticker"] = out["ticker"].astype(str).str.upper()
    return out.drop_duplicates(subset=["ticker"]).reset_index(drop=True)


def _default_market_session(options: list[str]) -> None:
    if st.session_state.get("gov_holdings_scan"):
        return
    key = "gov_sf_market"
    # Prefer All (full dataset) when migrating from the short Governance list.
    if not st.session_state.get("gov_market_all_v1"):
        if _DEFAULT_GOV_MARKET in options:
            st.session_state[key] = _DEFAULT_GOV_MARKET
        st.session_state["gov_market_all_v1"] = True
        st.session_state["gov_cap_tier"] = _DEFAULT_GOV_CAP_LABEL
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key] = (
            _DEFAULT_GOV_MARKET if _DEFAULT_GOV_MARKET in options else options[0]
        )


def _universe_ticker_set(universe: pd.DataFrame) -> set[str]:
    if universe is None or universe.empty or "ticker" not in universe.columns:
        return set()
    return {safe_str(t).upper() for t in universe["ticker"].tolist() if safe_str(t)}


def _scope_companies_to_universe(
    companies: pd.DataFrame, tickers: set[str]
) -> pd.DataFrame:
    if companies.empty or not tickers:
        return companies.iloc[0:0].copy() if not companies.empty else companies
    return companies[
        companies["ticker"].astype(str).str.upper().isin(tickers)
    ].reset_index(drop=True)


def _scope_multi_to_universe(multi: pd.DataFrame, tickers: set[str]) -> pd.DataFrame:
    if multi.empty or not tickers:
        return multi.iloc[0:0].copy() if not multi.empty else multi
    rows: list[dict] = []
    for _, row in multi.iterrows():
        raw = safe_str(row.get("tickers"))
        seats = {safe_str(t).upper() for t in raw.split(",") if safe_str(t)}
        in_uni = sorted(seats & tickers)
        if len(in_uni) < 2:
            continue
        item = dict(row)
        item["board_count"] = len(in_uni)
        item["tickers"] = ", ".join(in_uni)
        rows.append(item)
    if not rows:
        return multi.iloc[0:0].copy()
    return (
        pd.DataFrame(rows)
        .sort_values(by=["board_count", "name"], ascending=[False, True], kind="mergesort")
        .reset_index(drop=True)
    )


def _build_universe(
    stocks: pd.DataFrame,
    market: str,
    *,
    cap_tier_id: str = "all",
) -> pd.DataFrame:
    market_key = safe_str(market)

    # ≤5k Cr NSE (+ SME) names ∪ full holdings — Cap ignored (band + book baked in).
    if market_key == _UNDER5K_HOLDINGS_LABEL:
        under_nse = _build_universe(stocks, "NSE", cap_tier_id="under_5k")
        under_sme = _build_universe(stocks, NSE_SME_MARKET, cap_tier_id="under_5k")
        holds = _build_universe(stocks, HOLDINGS_PLAYLIST_LABEL, cap_tier_id="all")
        return _union_universes(under_nse, under_sme, holds)

    filters = StockFilters(market=market, sectors=[], industries=[], search="")
    filtered = apply_stock_filters(stocks, filters)
    if "market" in filtered.columns:
        mk = filtered["market"].astype(str).str.upper()
        market_u = market_key.upper()
        if market_u == "NSE SME":
            filtered = filtered[mk == "NSE SME"]
        elif market_u == "NSE":
            filtered = filtered[mk == "NSE"]
        else:
            # All / indexes / playlists: keep mainboard + SME for DIN scans.
            filtered = filtered[mk.isin(_NSE_GOV_MARKETS)]
    universe = analysis_universe(filtered, limit=0)
    tier = cap_tier_id if cap_tier_id not in ("", None) else "all"
    if tier in ("all",) or universe.empty:
        return universe
    _listings, tier_uni, _ex, _miss = filter_listings_by_cap_tier(
        filtered if not filtered.empty else stocks,
        tier,
    )
    # Keep only tickers that survive the cap band (known mcap in range).
    if tier_uni is None or tier_uni.empty:
        return universe.iloc[0:0].copy()
    keep = set(tier_uni["ticker"].astype(str).str.upper())
    return universe[
        universe["ticker"].astype(str).str.upper().isin(keep)
    ].reset_index(drop=True)


def render_governance(*, show_title: bool = True) -> None:
    init_governance_db()
    if show_title:
        st.markdown("### Governance")
    st.markdown(
        "**Scan & see DIN**  \n"
        "1. **Market** = **All** (same list as other scans) + **Cap** = **≤ 5,000 Cr** "
        "(default) → **Scan**. DIN filings are NSE-only, so BSE names are skipped.  \n"
        "2. Or pick **≤5k + Holdings** to force-include your full book.  \n"
        "3. **Companies** tab → **DIN** column."
    )

    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    market_opts = _gov_market_options(stocks)
    _default_market_session(market_opts)

    if not st.session_state.get("gov_indexes_warmed"):
        try:
            from stocks.market.nse_index_constituents import ensure_index_constituents

            ensure_index_constituents("NIFTY_500", force=False)
        except Exception:
            pass
        st.session_state["gov_indexes_warmed"] = True

    stats = governance_stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Companies", stats["companies"])
    with c2:
        st.metric("With DIN", stats.get("directors_with_din", 0))
    with c3:
        st.metric("Directors", stats["directors"])
    with c4:
        st.metric("Shared (2+)", stats["multi_board_directors"])
    if stats["companies"] and int(stats.get("directors_with_din") or 0) < max(
        8, stats["companies"] // 10
    ):
        st.warning(
            "Most boards are still name-only (old Yahoo scan). "
            "**Restart Streamlit**, then click **Scan** — Pending will upgrade them via NSE DIN."
        )

    cap_labels = cap_tier_labels()
    if "gov_cap_tier" not in st.session_state or st.session_state.gov_cap_tier not in cap_labels:
        st.session_state.gov_cap_tier = (
            _DEFAULT_GOV_CAP_LABEL
            if _DEFAULT_GOV_CAP_LABEL in cap_labels
            else cap_labels[0]
        )

    row = st.columns([1.7, 1.5, 1.0, 0.65, 0.65])
    with row[0]:
        market = st.selectbox(
            "Market",
            market_opts,
            key="gov_sf_market",
            format_func=lambda m: (
                f"{m} (≤5k ∪ book)"
                if m == _UNDER5K_HOLDINGS_LABEL
                else format_market_option(stocks, m)
            ),
        )
    with row[1]:
        st.selectbox(
            "Cap",
            cap_labels,
            key="gov_cap_tier",
            help="Filter by cached market cap (₹ Cr). Default ≤ 5,000 Cr.",
        )
    market_label = (
        HOLDINGS_PLAYLIST_LABEL
        if st.session_state.get("gov_holdings_scan")
        else market
    )
    cap_tier_id = _gov_cap_tier_id()
    # Cap ignored for Holdings and ≤5k+Holdings (band/book baked into Market).
    effective_cap = (
        "all"
        if market_label in {HOLDINGS_PLAYLIST_LABEL, _UNDER5K_HOLDINGS_LABEL}
        else cap_tier_id
    )
    universe = _build_universe(stocks, market_label, cap_tier_id=effective_cap)
    pending_n = len(pending_governance_jobs(universe, skip_scanned=True))
    with row[2]:
        st.metric("Pending", pending_n)
    with row[3]:
        run_clicked = st.button("Scan", type="primary", use_container_width=True)
    with row[4]:
        stop_clicked = st.button("Stop", use_container_width=True)

    if safe_str(market_label).upper() == "BSE":
        st.warning(
            "DIN boards come from **NSE** filings — BSE-only Market will not save boards. "
            "Use **All** or **NSE** (plus Cap)."
        )
    elif market_label == _UNDER5K_HOLDINGS_LABEL:
        st.caption(
            f"Universe **{len(universe):,}** = NSE ≤ ₹5,000 Cr ∪ Holdings "
            "(Cap ignored — already included)"
        )
    elif effective_cap != "all":
        tier = next((t for t in CAP_TIERS if t["id"] == effective_cap), None)
        band = (
            f"{tier['min']:g}–{float(tier['max']) - 0.01:g} Cr"
            if tier and tier.get("max") is not None
            else (st.session_state.gov_cap_tier or "")
        )
        nse_note = (
            " · DIN scan uses **NSE** names only"
            if market_label == "All"
            else ""
        )
        st.caption(
            f"Universe **{len(universe):,}** in **{band}** "
            f"(known mcap) · {market_label}{nse_note}"
        )
    elif market_label == HOLDINGS_PLAYLIST_LABEL:
        st.caption(
            f"Universe **{len(universe):,}** holdings (Cap ignored for portfolio scan)"
        )
    elif market_label == "All":
        st.caption(
            f"Universe **{len(universe):,}** NSE names from All "
            f"(BSE/NYSE skipped — no NSE DIN filings)"
        )

    workers = int(
        st.session_state.get("gov_workers")
        or min(STRATEGY_MAX_WORKERS, 4)
    )
    batch_size = _BATCH_SIZE
    if "gov_workers" not in st.session_state:
        st.session_state["gov_workers"] = workers

    with st.expander("More", expanded=False):
        m1, m2, m3 = st.columns(3)
        with m1:
            workers = int(
                st.number_input(
                    "Workers",
                    min_value=1,
                    max_value=STRATEGY_MAX_WORKERS_CAP,
                    step=1,
                    key="gov_workers",
                )
            )
            if st.button("Refresh indexes", use_container_width=True):
                with st.spinner("Fetching Nifty lists…"):
                    results = ensure_all_nifty_indexes(force=True)
                bits = [
                    f"{NIFTY_INDEXES[r['index_id']]['label']} {r['count']}"
                    for r in results
                ]
                st.success(" · ".join(bits))
                st.rerun()
        with m2:
            if st.button("Scan holdings", use_container_width=True):
                cov = holdings_governance_coverage()
                missing = list(cov.get("missing") or [])
                if missing:
                    clear_scan_log_for_tickers(missing, only_empty_failed=True)
                hold_uni = analysis_universe(
                    holdings_playlist_listings(stocks), limit=0
                )
                if hold_uni.empty:
                    st.warning("No holdings.")
                else:
                    st.session_state.gov_sf_market = HOLDINGS_PLAYLIST_LABEL
                    st.session_state.gov_auto_scan = True
                    st.session_state.gov_auto_totals = {
                        "saved": 0,
                        "skipped_empty": 0,
                        "skipped_protected": 0,
                        "failed": 0,
                        "batches": 0,
                    }
                    st.session_state.gov_holdings_scan = True
                    st.rerun()
            if st.button("Load DIN seed", use_container_width=True):
                n = seed_curated_boards(force=False)
                st.success(f"Added {n}.") if n else st.info("Already loaded.")
                st.rerun()
        with m3:
            if st.button("Enrich sectors", use_container_width=True):
                n = enrich_governance_company_classification(only_missing=True)
                st.success(f"Updated {n:,}.")
                st.rerun()
            if st.button("Clear DB", use_container_width=True):
                cleared = clear_all_governance_data()
                st.success(
                    f"Cleared {cleared['companies']:,} companies. "
                    "Pick an index and Scan."
                )
                st.rerun()
            if st.button("Retry empties", use_container_width=True):
                n = clear_scan_log(only_empty_failed=True)
                st.info(f"Cleared {n:,} empty/failed attempts.")
                st.rerun()

        cov = holdings_governance_coverage()
        if cov.get("total"):
            st.caption(
                f"Holdings coverage **{cov['with_board']}/{cov['total']}**"
                + (
                    f" · {len(cov.get('missing') or [])} missing"
                    if cov.get("missing")
                    else ""
                )
            )

    # Force holdings universe while a holdings scan is running (full book, Cap ignored).
    if st.session_state.get("gov_holdings_scan"):
        universe = _build_universe(
            stocks, HOLDINGS_PLAYLIST_LABEL, cap_tier_id="all"
        )
        pending_n = len(pending_governance_jobs(universe, skip_scanned=True))
        market_label = HOLDINGS_PLAYLIST_LABEL

    if stop_clicked:
        st.session_state.pop("gov_auto_scan", None)
        st.session_state.pop("gov_auto_totals", None)
        st.session_state.pop("gov_holdings_scan", None)
        st.warning("Stopped.")

    if run_clicked:
        st.session_state.pop("gov_holdings_scan", None)
        if universe.empty:
            st.warning("No stocks in this market.")
        else:
            st.session_state.gov_auto_scan = True
            st.session_state.gov_auto_totals = {
                "saved": 0,
                "skipped_empty": 0,
                "skipped_protected": 0,
                "failed": 0,
                "batches": 0,
            }
            st.rerun()

    if st.session_state.get("gov_auto_scan"):
        if universe.empty:
            st.session_state.pop("gov_auto_scan", None)
            st.session_state.pop("gov_holdings_scan", None)
            st.warning("No stocks in this market.")
        else:
            progress = st.progress(0, text="Scanning…")
            status = st.empty()
            totals = st.session_state.get("gov_auto_totals") or {
                "saved": 0,
                "skipped_empty": 0,
                "skipped_protected": 0,
                "failed": 0,
                "batches": 0,
            }

            def _progress(done: int, total: int, ticker: str) -> None:
                if total <= 0:
                    progress.progress(1.0, text="Done")
                    return
                progress.progress(
                    min(done / total, 1.0),
                    text=f"{done:,}/{total:,} · {ticker}",
                )

            try:
                result = run_governance_scan(
                    universe,
                    batch_size=int(batch_size),
                    max_workers=int(workers),
                    skip_scanned=True,
                    progress_callback=_progress,
                )
            except Exception as exc:
                progress.empty()
                st.session_state.pop("gov_auto_scan", None)
                st.session_state.pop("gov_holdings_scan", None)
                st.error(f"Scan failed: {exc}")
                return

            progress.empty()
            totals["saved"] += int(result.get("saved") or 0)
            totals["skipped_empty"] += int(result.get("skipped_empty") or 0)
            totals["skipped_protected"] += int(result.get("skipped_protected") or 0)
            totals["failed"] += int(result.get("failed") or 0)
            totals["batches"] += 1
            st.session_state.gov_auto_totals = totals
            st.session_state.gov_last_scan = result

            universe_n = int(result.get("universe") or len(universe))
            pending_after = int(result.get("pending_after") or 0)
            din_now = governance_stats().get("directors_with_din", 0)
            src = result.get("source") or "nse_governance"
            status.caption(
                f"Batch {totals['batches']} · {src} · saved {totals['saved']:,} · "
                f"empty {totals['skipped_empty']:,} · "
                f"pending {pending_after:,}/{universe_n:,} · DIN directors {din_now:,}"
            )

            if result.get("done") or pending_after <= 0:
                st.session_state.pop("gov_auto_scan", None)
                st.session_state.pop("gov_holdings_scan", None)
                st.success(
                    f"Done — {totals['saved']:,} saved via {src} · "
                    f"{totals['skipped_empty']:,} empty · "
                    f"{totals['failed']:,} failed · "
                    f"{din_now:,} directors with DIN"
                )
            else:
                st.rerun()

    tab_company, tab_shared, tab_add = st.tabs(["Companies", "Shared", "Add DIN"])
    scope_tickers = _universe_ticker_set(universe)
    with tab_company:
        _render_company_tab(scope_tickers=scope_tickers, scope_label=market_label)
    with tab_shared:
        _render_shared_tab(scope_tickers=scope_tickers, scope_label=market_label)
    with tab_add:
        _render_add_tab()


def _render_company_tab(
    *,
    scope_tickers: set[str] | None = None,
    scope_label: str = "",
) -> None:
    companies = companies_with_boards()
    if scope_tickers is not None:
        companies = _scope_companies_to_universe(companies, scope_tickers)
    if companies.empty:
        st.info(
            f"Nothing in **{scope_label or 'DB'}** yet — click **Scan** above, "
            "then pick a company here to see DIN."
            if scope_label
            else "Nothing in DB yet — click **Scan** above, then pick a company here to see DIN."
        )
        return

    st.caption(
        f"{len(companies):,} companies · {scope_label} · "
        "pick one to see board **DIN** numbers"
    )
    labels = {
        str(r.ticker): f"{r.ticker} — {r.name} ({int(r.director_count)})"
        for r in companies.itertuples()
    }
    tickers = list(labels.keys())
    pick_key = "gov_company_pick"
    if st.session_state.get(pick_key) not in tickers:
        st.session_state[pick_key] = tickers[0]
    choice = st.selectbox(
        "Company",
        tickers,
        format_func=lambda t: labels[t],
        key=pick_key,
    )
    board = directors_for_ticker(choice)
    if board.empty:
        st.warning("No directors for this ticker.")
        return

    show = board.copy()
    show["DIN"] = show["din"].fillna("")
    din_n = int(show["DIN"].astype(str).str.strip().ne("").sum())
    st.caption(
        f"**{choice}** board · {din_n}/{len(show)} seats with DIN "
        f"(blank DIN = name-only / incomplete filing)"
    )
    st.dataframe(
        show.rename(
            columns={
                "name": "Director",
                "designation": "Role",
                "category": "Category",
                "source": "Source",
                "as_of": "As of",
                "board_count": "Boards",
            }
        )[["DIN", "Director", "Role", "Category", "As of", "Boards", "Source"]],
        use_container_width=True,
        hide_index=True,
    )

    overlaps = overlaps_for_ticker(choice)
    if scope_tickers is not None and not overlaps.empty:
        overlaps = overlaps[
            overlaps["also_ticker"].astype(str).str.upper().isin(scope_tickers)
        ].reset_index(drop=True)
    st.markdown("**Also on**")
    if overlaps.empty:
        st.caption("No shared seats in this universe yet.")
    else:
        st.dataframe(
            overlaps.rename(
                columns={
                    "din": "DIN",
                    "director": "Director",
                    "here_as": "Here",
                    "also_ticker": "Ticker",
                    "also_company": "Company",
                    "also_as": "There",
                }
            )[["DIN", "Director", "Here", "Ticker", "Company", "There"]],
            use_container_width=True,
            hide_index=True,
        )


def _render_shared_tab(
    *,
    scope_tickers: set[str] | None = None,
    scope_label: str = "",
) -> None:
    multi = multi_board_directors(min_boards=2)
    if scope_tickers is not None:
        multi = _scope_multi_to_universe(multi, scope_tickers)
    if multi.empty:
        st.info(
            f"No shared directors in **{scope_label}** yet."
            if scope_label
            else "No shared directors yet."
        )
        return

    st.caption(f"{len(multi):,} directors · {scope_label}")
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
    pick = st.selectbox("Detail", list(options.keys()), key="gov_shared_pick")
    seats = seats_for_person(options[pick])
    if scope_tickers is not None and not seats.empty:
        seats = seats[
            seats["ticker"].astype(str).str.upper().isin(scope_tickers)
        ].reset_index(drop=True)
    st.dataframe(
        seats.rename(
            columns={
                "ticker": "Ticker",
                "company_name": "Company",
                "designation": "Role",
                "category": "Category",
                "source": "Source",
                "as_of": "As of",
            }
        )[["Ticker", "Company", "Role", "Category", "As of", "Source"]],
        use_container_width=True,
        hide_index=True,
    )


def _render_add_tab() -> None:
    st.caption("Add one board from AGM / CG filings — DIN preferred.")
    with st.form("gov_add_board"):
        col_a, col_b = st.columns(2)
        with col_a:
            ticker = st.text_input("Ticker", placeholder="RELIANCE").strip().upper()
            name = st.text_input("Company name").strip()
            cin = st.text_input("CIN (optional)").strip()
        with col_b:
            isin = st.text_input("ISIN (optional)").strip()
            as_of = st.text_input("As of", placeholder="2025-08-08").strip()
            source = st.text_input("Source", value="manual").strip() or "manual"

        raw = st.text_area(
            "DIN | Name | Role | Category",
            height=140,
            placeholder=(
                "00041610 | Rajesh C. Parikh | Chairman & Managing Director | Executive"
            ),
        )
        submitted = st.form_submit_button("Save", type="primary")

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
            errors.append(f"Line {i}: need DIN | Name | Role")
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
        st.error("Ticker and company name required.")
        return
    if not seats:
        st.error("Add at least one director.")
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
