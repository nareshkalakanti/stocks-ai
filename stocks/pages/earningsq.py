"""EarningsQ — NSE-only live financial results tab."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.dashboards.report_html import embed_html_iframe
from stocks.strategies.earningsq.html import build_earningsq_html, earningsq_iframe_height
from stocks.strategies.earningsq.scores import annotate_quality
from stocks.strategies.earningsq.service import attach_sector_mcap, run_earningsq_scan

_CACHE_KEY = "earningsq_df_v3"
_STATS_KEY = "earningsq_scan_stats_v1"
_HTML_KEY = "earningsq_html_v7"


def _apply_view(df: pd.DataFrame, *, min_surprise: float, sort_by: str) -> pd.DataFrame:
    if df is None or (hasattr(df, "empty") and df.empty):
        return df
    stats = dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
    view = attach_sector_mcap(df)
    view = annotate_quality(view)
    if "surprise_score" in view.columns:
        s = pd.to_numeric(view["surprise_score"], errors="coerce")
        view = view[s.notna() & (s > float(min_surprise))].copy()
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
        "Live NSE result announcements — not a full-universe scan; "
        "only stocks that filed results in the lookback."
    )

    with st.expander("How to use (30 seconds)", expanded=False):
        st.markdown(
            """
1. **Top picks** = surprise beat + profit growth + price not fading.
2. **Strong** badge = prefer these first.
3. **Caution** = big surprise but stock fell — dig deeper before acting.
4. Use search / chips in the report to filter; raise **Surprise >** to cut noise.
5. Coverage: NSE equity announcements in lookback → result prints → unique tickers scored.
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
                    help="Hide prints below this surprise score (0 = keep all positive-ish).",
                )
            )
        with c3:
            with_returns = st.checkbox(
                "Fetch price reaction",
                value=bool(st.session_state.get("earningsq_with_returns", True)),
                key="earningsq_with_returns",
                help="1D / 1W moves from the print (slower, but needed for Return score).",
            )

    refresh = st.button("Refresh NSE", type="primary")
    sort_by = "Best overall"

    cached = st.session_state.get(_CACHE_KEY)
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
            df = run_earningsq_scan(
                lookback_days=lookback,
                min_surprise=-5.0,  # filter in UI so sort/settings stay interactive
                with_returns=with_returns,
                use_fixtures_if_empty=True,
                progress_callback=_progress,
            )
        except Exception as exc:
            progress.empty()
            st.error(f"EarningsQ scan failed: {exc}")
            return
        progress.empty()
        st.session_state[_CACHE_KEY] = df
        st.session_state[_STATS_KEY] = dict(getattr(df, "attrs", {}) or {}).get("scan_stats") or {}
        st.session_state.pop(_HTML_KEY, None)
    else:
        df = cached

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
        uni = int(stats.get("nse_equity_universe") or 0)
        extra = ""
        if raw or uni:
            extra = f" (NSE feed: {raw:,} announcements"
            if uni:
                extra += f" · {uni:,} listed equities"
            extra += ")"
        st.warning(f"No NSE financial-result prints in this lookback{extra}.")
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
    result_n = int(stats.get("result_prints") or stats.get("unique_tickers") or 0)
    uniq_n = int(stats.get("unique_tickers") or 0)
    uni_n = int(stats.get("nse_equity_universe") or 0)
    scored_n = int(stats.get("scored") or (len(df) if df is not None else 0))

    cover_bits = [f"{len(view):,} in view", f"{strong_n:,} strong"]
    if uniq_n:
        cover_bits.append(f"{uniq_n:,} scored")
    with st.expander("Coverage · " + " · ".join(cover_bits), expanded=False):
        s1, s2, s3, s4 = st.columns(4)
        s1.metric(
            "NSE announcements",
            f"{raw_n:,}" if raw_n else "—",
            help=f"All equity corporate announcements in last {lookback}d (before result filter).",
        )
        s2.metric(
            "Result prints",
            f"{result_n:,}" if result_n else f"{uniq_n:,}",
            help="Announcements classified as financial results (pre-dedupe).",
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
