"""EarningsQ — NSE-only live financial results tab."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.dashboards.report_html import embed_html_iframe
from stocks.core.text_utils import safe_str
from stocks.strategies.earningsq.html import build_earningsq_html, earningsq_iframe_height
from stocks.strategies.earningsq.scores import annotate_quality
from stocks.strategies.earningsq.service import (
    attach_sector_mcap,
    backfill_earningsq_metrics,
    metrics_missing_rate,
    rehydrate_earningsq_from_pead,
    run_earningsq_scan,
)
from stocks.shared.corp_tags import attach_corp_tags
from stocks.core.database import pead2_cache_summary

_CACHE_KEY = "earningsq_df_v7"
_STATS_KEY = "earningsq_scan_stats_v4"
_HTML_KEY = "earningsq_html_v11"
_BACKFILL_DONE_KEY = "earningsq_metrics_backfill_v2"
_PEAD_TS_KEY = "earningsq_pead_cache_ts"


def _apply_view(df: pd.DataFrame, *, min_surprise: float, sort_by: str) -> pd.DataFrame:
    if df is None or (hasattr(df, "empty") and df.empty):
        return df
    stats = dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
    view = attach_sector_mcap(df)
    view = attach_corp_tags(view)
    # Announcement feed market wins when ticker also on mainboard listings cache.
    if "market" in view.columns:
        m = view["market"].astype(str).str.upper()
        from_feed = m.eq("NSE SME") | m.str.contains("SME", na=False)
        if "is_sme" in view.columns:
            view["is_sme"] = view["is_sme"].fillna(False).astype(bool) | from_feed
        else:
            view["is_sme"] = from_feed
    view = annotate_quality(view)
    if "surprise_score" in view.columns:
        s = pd.to_numeric(view["surprise_score"], errors="coerce")
        # Unscored prints stay visible; Surprise > only drops scored misses.
        view = view[s.isna() | (s > float(min_surprise))].copy()
        view = annotate_quality(view)

    sort_by = (sort_by or "Best overall").strip()
    if sort_by == "Surprise" and "surprise_score" in view.columns:
        view = view.sort_values("surprise_score", ascending=False, kind="mergesort")
    elif sort_by == "Return" and "return_score" in view.columns:
        view = view.sort_values("return_score", ascending=False, kind="mergesort")
    elif sort_by == "Newest" and "broadcast_at" in view.columns:
        view = view.sort_values("broadcast_at", ascending=False, kind="mergesort")
    elif "blend_rank" in view.columns:
        view = view.sort_values("blend_rank", ascending=False, kind="mergesort")
    if stats:
        view.attrs["scan_stats"] = stats
    return view


def render_earningsq(*, show_title: bool = True) -> None:
    if show_title:
        st.markdown("### EarningsQ")
    st.caption(
        "Live NSE result announcements (mainboard + SME/Emerge) — not a full-universe scan; "
        "only stocks that filed results in the lookback. Surprise / NP YoY from PEAD cache "
        "or NSE Ind-AS XBRL when cache is empty."
    )

    with st.expander("How to use (30 seconds)", expanded=False):
        st.markdown(
            """
1. **Top picks** = surprise beat + profit growth + price not fading.
2. **Strong** badge = prefer these first.
3. **Caution** = big surprise but stock fell — dig deeper before acting.
4. Use search / chips in the report to filter; raise **Surprise >** to cut noise.
5. Coverage: NSE equity + SME announcements in lookback → result prints → unique tickers scored.
            """.strip()
        )

    with st.expander("Scan settings", expanded=False):
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            lookback = int(
                st.number_input(
                    "Lookback days",
                    min_value=1,
                    max_value=30,
                    value=int(st.session_state.get("earningsq_lookback") or 7),
                    step=1,
                    key="earningsq_lookback",
                    help="How far back to pull NSE financial-result announcements.",
                )
            )
        with c2:
            min_surprise = float(
                st.number_input(
                    "Surprise >",
                    min_value=-5.0,
                    max_value=20.0,
                    value=float(st.session_state.get("earningsq_min_surprise") or 0.0),
                    step=0.1,
                    key="earningsq_min_surprise",
                    help=(
                        "Hide scored prints at or below this surprise. "
                        "Unscored prints (no PEAD metrics yet) stay visible. "
                        "Use -5 to keep almost everything scored."
                    ),
                )
            )
        with c3:
            with_returns = st.checkbox(
                "Fetch price reaction",
                value=bool(st.session_state.get("earningsq_with_returns", True)),
                key="earningsq_with_returns",
                help="1D / 1W moves from the print (slower, but needed for Return score).",
            )

    b1, b2 = st.columns([1, 1.2])
    with b1:
        refresh = st.button("Refresh NSE", type="primary", width="stretch")
    with b2:
        fill_metrics = st.button(
            "Fill Surprise / YoY",
            width="stretch",
            help=(
                "Pull PEAD cache into this table, then backfill gaps via NSE XBRL / Yahoo "
                "(Surprise, Sales/Profit/EPS YoY, Return)."
            ),
        )
    sort_by = "Best overall"

    cached = st.session_state.get(_CACHE_KEY)
    if cached is None:
        # Migrate prior session caches so PEAD rehydrate can run without a full NSE refresh.
        for legacy in ("earningsq_df_v6", "earningsq_df_v5", "earningsq_df_v4"):
            legacy_df = st.session_state.get(legacy)
            if isinstance(legacy_df, pd.DataFrame) and not legacy_df.empty:
                cached = legacy_df
                st.session_state[_CACHE_KEY] = legacy_df
                break
    if refresh or cached is None:
        progress = st.progress(0, text="Fetching NSE equity announcements…")

        def _progress(done: int, total: int, ticker: str) -> None:
            if total <= 0:
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Scoring result prints {done:,}/{total:,} · {ticker}",
            )

        try:
            # Never silently fall back to demo fixtures on Refresh — that made
            # counts jump from ~3 → 100+ and looked random.
            df = run_earningsq_scan(
                lookback_days=lookback,
                min_surprise=-5.0,  # filter in UI so sort/settings stay interactive
                with_returns=with_returns,
                use_fixtures_if_empty=False,
                progress_callback=_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"EarningsQ scan failed: {exc}")
            return
        progress.empty()
        # Keep prior prints if NSE feed is empty (common when NSE rate-limits).
        if (
            (df is None or df.empty)
            and isinstance(cached, pd.DataFrame)
            and not cached.empty
        ):
            st.warning(
                "NSE returned no announcements this attempt — keeping the previous scan. "
                "Use **Fill Surprise / YoY** to backfill missing metrics."
            )
            df = cached
        else:
            st.session_state.pop(_BACKFILL_DONE_KEY, None)
        st.session_state[_CACHE_KEY] = df
        st.session_state[_STATS_KEY] = dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
        st.session_state.pop(_HTML_KEY, None)
    else:
        df = cached

    # After PEAD runs, pull growth into the current EarningsQ session (cheap).
    pead_summary = {}
    try:
        pead_summary = pead2_cache_summary() or {}
    except Exception:
        pead_summary = {}
    pead_ts = safe_str(pead_summary.get("pead_fetched_at") or "")
    pead_changed = bool(pead_ts) and pead_ts != st.session_state.get(_PEAD_TS_KEY)
    if isinstance(df, pd.DataFrame) and not df.empty and (
        pead_changed or metrics_missing_rate(df) >= 0.3
    ):
        df, n_pead = rehydrate_earningsq_from_pead(df, only_missing=True)
        if pead_ts:
            st.session_state[_PEAD_TS_KEY] = pead_ts
        if n_pead:
            st.session_state[_CACHE_KEY] = df
            st.session_state[_STATS_KEY] = (
                dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
            )
            st.session_state.pop(_HTML_KEY, None)
            st.caption(f"Pulled PEAD metrics into **{n_pead:,}** EarningsQ rows.")

    # Auto-backfill remaining gaps (NSE XBRL / Yahoo) once, or on button.
    need_fill = (
        isinstance(df, pd.DataFrame)
        and not df.empty
        and (
            fill_metrics
            or (
                metrics_missing_rate(df) >= 0.5
                and not st.session_state.get(_BACKFILL_DONE_KEY)
            )
        )
    )
    if need_fill:
        progress = st.progress(0, text="Filling Surprise / Sales / Profit / EPS YoY…")

        def _fill_progress(done: int, total: int, ticker: str) -> None:
            if total <= 0:
                return
            progress.progress(
                min(done / total, 1.0),
                text=f"Metrics {done:,}/{total:,} · {ticker}",
            )

        try:
            # Prefer PEAD first inside backfill path as well.
            df, _ = rehydrate_earningsq_from_pead(df, only_missing=True)
            df = backfill_earningsq_metrics(
                df,
                with_returns=with_returns,
                progress_callback=_fill_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"Metrics backfill failed: {exc}")
        else:
            progress.empty()
            st.session_state[_CACHE_KEY] = df
            st.session_state[_STATS_KEY] = (
                dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
            )
            st.session_state[_BACKFILL_DONE_KEY] = True
            st.session_state.pop(_HTML_KEY, None)
            filled = int(
                (st.session_state.get(_STATS_KEY) or {}).get("with_surprise") or 0
            )
            st.caption(f"Metrics filled — **{filled:,}** rows now have a Surprise score.")

    view = _apply_view(df, min_surprise=min_surprise, sort_by=sort_by)
    st.session_state.pop(_HTML_KEY, None)

    stats = (
        st.session_state.get(_STATS_KEY)
        or dict(getattr(df, "attrs", {}) or {}).get("scan_stats")
        or dict(getattr(view, "attrs", {}) or {}).get("scan_stats")
        or {}
    )

    if view is None or (hasattr(view, "empty") and view.empty):
        raw = int(stats.get("nse_announcements_raw") or 0)
        prints = int(stats.get("result_prints") or 0)
        uniq = int(stats.get("unique_tickers") or 0)
        scored = int(stats.get("scored") or 0)
        uni = int(stats.get("nse_equity_universe") or 0)
        if prints or uniq or scored:
            st.warning(
                f"NSE found **{prints or uniq:,}** result prints"
                + (f" ({uniq:,} tickers)" if uniq and prints and uniq != prints else "")
                + f", but none pass the current **Surprise >** filter "
                f"(or all lack surprise metrics). Lower Surprise > toward -5."
                + (f" Feed: {raw:,} announcements" if raw else "")
                + (f" · {uni:,} listed equities." if uni else ".")
            )
        else:
            extra = ""
            if raw or uni:
                extra = f" (NSE feed: {raw:,} announcements"
                if uni:
                    extra += f" · {uni:,} listed equities"
                extra += ")"
            st.warning(
                f"No NSE financial-result prints in this lookback{extra}. "
                "Outside peak result weeks this can be empty — try a longer lookback."
            )
        return

    src = ""
    if "feed_source" in view.columns and len(view):
        src = str(view.iloc[0].get("feed_source") or "")
    strong_n = int((view.get("quality_tag") == "strong").sum()) if "quality_tag" in view.columns else 0
    fade_n = int((view.get("quality_tag") == "fade").sum()) if "quality_tag" in view.columns else 0
    green_1d = 0
    if "ret_1d" in view.columns:
        r1 = pd.to_numeric(view["ret_1d"], errors="coerce")
        green_1d = int((r1 > 0).sum())

    raw_n = int(stats.get("nse_announcements_raw") or 0)
    eq_raw = int(stats.get("nse_equities_raw") or 0)
    sme_raw = int(stats.get("nse_sme_raw") or 0)
    result_n = int(stats.get("result_prints") or stats.get("unique_tickers") or 0)
    sme_prints = int(stats.get("sme_result_prints") or 0)
    uniq_n = int(stats.get("unique_tickers") or 0)
    uni_n = int(stats.get("nse_equity_universe") or 0)
    scored_n = int(stats.get("scored") or (len(df) if df is not None else 0))

    cover_bits = [f"{len(view):,} in view", f"{strong_n:,} strong"]
    if uniq_n:
        cover_bits.append(f"{uniq_n:,} scored")
    if sme_prints:
        cover_bits.append(f"{sme_prints:,} SME prints")
    with st.expander("Coverage · " + " · ".join(cover_bits), expanded=False):
        s1, s2, s3, s4 = st.columns(4)
        s1.metric(
            "NSE announcements",
            f"{raw_n:,}" if raw_n else "—",
            help=(
                f"Mainboard {eq_raw:,} + SME {sme_raw:,} corporate announcements "
                f"in last {lookback}d (before result filter)."
            ),
        )
        s2.metric(
            "Result prints",
            f"{result_n:,}" if result_n else f"{uniq_n:,}",
            help=(
                "Announcements classified as financial results (pre-dedupe). "
                f"SME result prints: {sme_prints:,}."
            ),
        )
        s3.metric(
            "Stocks scored",
            f"{uniq_n or scored_n:,}",
            help="Unique NSE tickers with a result print (latest print kept).",
        )
        s4.metric(
            "NSE listed",
            f"{uni_n:,}" if uni_n else "—",
            help="NSE mainboard equity universe size (EQUITY_L) — context only, not fully scanned.",
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("In view", f"{len(view):,}")
        m2.metric("Strong", f"{strong_n:,}")
        m3.metric("Caution", f"{fade_n:,}")
        m4.metric("Up 1D", f"{green_1d:,}")

        if src == "fixture":
            st.caption("Demo fixtures (NSE returned none for this window).")
        else:
            bits = [f"lookback {lookback}d", f"surprise > {min_surprise:g}"]
            if uni_n and uniq_n:
                bits.append(f"{uniq_n:,} of ~{uni_n:,} NSE equities had a result print")
            st.caption(" · ".join(bits))

    html = build_earningsq_html(
        view,
        title="EarningsQ",
        subtitle=f"{len(view)} in view · {strong_n} strong",
        standalone=False,
        scan_stats=stats,
    )
    st.session_state[_HTML_KEY] = html
    embed_html_iframe(html, height=earningsq_iframe_height(len(view)))

    export = view.copy()
    for col in ("quarters", "snapshot"):
        if col in export.columns:
            export = export.drop(columns=[col])
    st.download_button(
        "Download CSV",
        data=export.to_csv(index=False).encode("utf-8"),
        file_name="earningsq_nse.csv",
        mime="text/csv",
        key="earningsq_csv",
    )
