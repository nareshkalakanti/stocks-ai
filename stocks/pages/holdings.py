import pandas as pd
import streamlit as st

from stocks.shared.portfolio import enrich_holdings, load_holdings, seed_default_holdings

_CACHE_KEY = "holdings_priced_v3"


def _holdings_display_df(priced: pd.DataFrame) -> pd.DataFrame:
    df = priced.copy()
    if "momentum_rank" in df.columns:
        df = df.sort_values("momentum_rank", ascending=True, na_position="last")
    elif "momentum_pct" in df.columns:
        df = df.sort_values("momentum_pct", ascending=False, na_position="last")
        df["momentum_rank"] = range(1, len(df) + 1)

    rename = {
        "momentum_rank": "Rank",
        "ticker": "Ticker",
        "name": "Company",
        "momentum_pct": "Momentum %",
        "current_price": "Price",
        "price_1y": "Price 1Y",
        "price_1m": "Price 1M",
        "industry": "Industry",
        "screener_link": "Screener",
        "tv_link": "TradingView",
    }
    present = [c for c in rename if c in df.columns]
    return df[present].rename(columns=rename).reset_index(drop=True)


def render_holdings() -> None:
    st.markdown("### Holdings")

    holdings = load_holdings(seed_if_empty=True)

    if holdings.empty:
        st.warning("No holdings in database.")
        if st.button("Load default portfolio"):
            seed_default_holdings(force=True)
            st.rerun()
        return

    if st.button("Refresh prices", type="primary"):
        st.session_state.pop(_CACHE_KEY, None)
        st.session_state.pop("holdings_priced_v2", None)
        st.rerun()

    st.caption(
        "Sorted by **Rank** (highest 12M momentum with 1M lag first). "
        "**Momentum %** = (Price 1M ÷ Price 1Y − 1) × 100."
    )

    if _CACHE_KEY not in st.session_state:
        with st.spinner("Fetching prices and momentum (2y history per stock)…"):
            priced = enrich_holdings(holdings, use_cache=True)
        st.session_state[_CACHE_KEY] = priced
    else:
        priced = st.session_state[_CACHE_KEY]

    priced_count = (
        int(priced["current_price"].notna().sum()) if "current_price" in priced.columns else 0
    )
    momentum_count = (
        int(priced["momentum_pct"].notna().sum()) if "momentum_pct" in priced.columns else 0
    )

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Stocks", len(priced))
    with m2:
        st.metric("Priced", priced_count)
    with m3:
        st.metric("With momentum", momentum_count)

    display = _holdings_display_df(priced)
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d"),
            "Momentum %": st.column_config.NumberColumn(format="%.2f"),
            "Price": st.column_config.NumberColumn(format="%.2f"),
            "Price 1Y": st.column_config.NumberColumn(format="%.2f"),
            "Price 1M": st.column_config.NumberColumn(format="%.2f"),
            "Screener": st.column_config.LinkColumn(display_text="Open"),
            "TradingView": st.column_config.LinkColumn(display_text="Chart"),
        },
    )
