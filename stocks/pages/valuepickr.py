"""ValuePickr — Stock Opportunities + ValuePickrGPT thread analysis."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from stocks.core.config import (
    INDIA_STOCKS_DATASET,
    VALUEPICKR_BASE_URL,
    VALUEPICKR_CACHE_HOURS,
    VALUEPICKR_MAX_PAGES,
)
from stocks.core.database import load_valuepickr_opportunities_latest
from stocks.listings.stocks_data import load_india_stocks
from stocks.pages.settings import get_selected_model
from stocks.shared.hf import get_client
from stocks.valuepickr.forum import VP_SUBCATEGORIES
from stocks.valuepickr.gpt import analyze_thread_with_gpt
from stocks.valuepickr.opportunities import latest_scan_label, prepare_opportunities_table


def _format_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols = [
        "rank",
        "smart_rank",
        "title",
        "company",
        "ticker",
        "subcategory",
        "replies",
        "views",
        "likes",
        "last_posted_at",
        "url",
    ]
    present = [c for c in cols if c in df.columns]
    out = df[present].copy()
    rename = {
        "rank": "Rank",
        "smart_rank": "Score",
        "title": "Thread",
        "company": "Company",
        "ticker": "Ticker",
        "subcategory": "Subcategory",
        "replies": "Contributions",
        "views": "Views",
        "likes": "Likes",
        "last_posted_at": "Last post",
        "url": "URL",
    }
    return out.rename(columns=rename)


def render_valuepickr() -> None:
    st.markdown("### ValuePickr")
    st.caption(
        f"[ValuePickr Forum](https://www.valuepickr.com/) · "
        f"[Stock Opportunities]({VALUEPICKR_BASE_URL}/c/stock-opportunities/11) · "
        "Discussions ranked by smart score · **ValuePickrGPT** for thread deep-dive"
    )

    tab_opp, tab_gpt = st.tabs(["Stock Opportunities", "ValuePickrGPT"])

    with tab_opp:
        _render_opportunities()

    with tab_gpt:
        _render_gpt()


def _render_opportunities() -> None:
    try:
        stocks = load_india_stocks()
    except Exception as exc:
        st.error(f"Could not load dataset `{INDIA_STOCKS_DATASET}`: {exc}")
        return

    c1, c2 = st.columns([1, 3])
    with c1:
        refresh = st.button("Fetch / Refresh", type="primary", use_container_width=True)
    with c2:
        subcat = st.selectbox(
            "Subcategory",
            ["All"] + [v for k, v in VP_SUBCATEGORIES.items() if k != 11],
            label_visibility="collapsed",
        )

    cache_key = "valuepickr_opportunities_v1"
    if refresh:
        st.session_state.pop(cache_key, None)

    if cache_key not in st.session_state:
        with st.spinner(
            f"Fetching active discussions ({VALUEPICKR_MAX_PAGES} pages per subcategory)..."
        ):
            try:
                df = prepare_opportunities_table(
                    stocks,
                    max_pages=VALUEPICKR_MAX_PAGES,
                    use_cache=not refresh,
                )
            except Exception as exc:
                st.error(f"Fetch failed: {exc}")
                df = load_valuepickr_opportunities_latest()
            st.session_state[cache_key] = df
    else:
        df = st.session_state[cache_key]

    if df is None or df.empty:
        fallback = load_valuepickr_opportunities_latest()
        if fallback is not None and not fallback.empty:
            df = fallback
        else:
            st.info("Click **Fetch / Refresh** to load Stock Opportunities from the forum.")
            return

    scan_date = latest_scan_label(df)
    listed_n = int(df["ticker"].notna().sum()) if "ticker" in df.columns else 0
    m1, m2, m3 = st.columns(3)
    m1.metric("Scan date", scan_date)
    m2.metric("Threads", len(df))
    m3.metric("Listed matches", listed_n)

    work = df.copy()
    if subcat != "All" and "subcategory" in work.columns:
        work = work[work["subcategory"].astype(str) == subcat]

    if work.empty:
        st.warning(f"No threads in **{subcat}**.")
        return

    st.dataframe(
        _format_df_for_display(work),
        use_container_width=True,
        hide_index=True,
        column_config={
            "URL": st.column_config.LinkColumn("VP link", display_text="Open"),
            "Score": st.column_config.NumberColumn(format="%.1f"),
        },
    )

    st.caption(
        f"Cache TTL {VALUEPICKR_CACHE_HOURS}h · "
        "Contributions = reply count · Sorted by smart rank (activity + engagement + listing match)"
    )


def _render_gpt() -> None:
    client = get_client()
    if client is None:
        st.warning("Set **HF_TOKEN** in `.env` and pick a chat model in **Settings**.")
        return

    default_url = st.session_state.get("valuepickr_gpt_url", "")
    url = st.text_input(
        "ValuePickr thread URL",
        value=default_url,
        placeholder="https://forum.valuepickr.com/t/company-name/slug/12345",
    )
    analyze = st.button("Analyze with ValuePickrGPT", type="primary")

    st.markdown(
        """
ValuePickrGPT reports:
1. **Strengths & weaknesses** (≤10 each) for long-term investing  
2. **Monthly sentiment** table (score 1–100 + keywords) through July 2025  
3. **2025 discussion** summary  
        """
    )

    if not analyze:
        return
    if not url.strip():
        st.error("Paste a ValuePickr thread URL.")
        return

    st.session_state["valuepickr_gpt_url"] = url.strip()
    model = get_selected_model()
    max_tokens = int(st.session_state.get("max_tokens", 4096))
    temperature = float(st.session_state.get("temperature", 0.25))

    with st.spinner(f"Fetching posts and analysing with {model}…"):
        try:
            result = analyze_thread_with_gpt(
                client,
                model,
                url=url.strip(),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            st.error(str(exc))
            return

    st.success(
        f"Analysed **{result.get('posts_count', 0)}** posts · "
        f"{result.get('company') or result.get('title')}"
    )
    st.markdown(result.get("analysis_md") or "")
