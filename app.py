import streamlit as st

from stocks.core.streamlit_compat import normalize_radio_session_state
from stocks.market.yfinance_utils import install_yfinance_noise_filters

install_yfinance_noise_filters()
from stocks.core.database import ensure_db, init_db
from stocks.governance.db import init_governance_db, ensure_governance_db_seeded
from stocks.pages.sector_landscape import render_sector_landscape
from stocks.pages.strategy import render_strategy
from stocks.pages.superstars import render_superstars
from stocks.pages.valuepickr import render_valuepickr
from stocks.pages.demerger import render_demerger
from stocks.pages.earningsq import render_earningsq
from stocks.pages.watching import render_watching
from stocks.shared.early_edge import ensure_early_edge_seeded
from stocks.scans.holdings_playlist import HOLDINGS_PLAYLIST_LABEL
from stocks.shared.fund_watchlists import (
    NEGEN_PLAYLIST_LABEL,
    NIVESHAAY_PLAYLIST_LABEL,
)

st.set_page_config(
    page_title="AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_db()
init_governance_db()
ensure_governance_db_seeded()
ensure_early_edge_seeded()

_SIDEBAR_PAGES = [
    "Strategy",
    "EarningsQ",
    "Sector Landscape",
    "SuperStars",
    "Watching",
    "ValuePickr",
    "Demergers",
]
# v8: Holdings + Fund Watchlists merged into Watching
_SIDEBAR_KEY = "app_sidebar_page_v8"

normalize_radio_session_state(_SIDEBAR_KEY, _SIDEBAR_PAGES)

# Migrate removed sidebar pages → Watching with the right list selected.
_prev = st.session_state.get(_SIDEBAR_KEY)
if _prev == "Holdings":
    st.session_state[_SIDEBAR_KEY] = "Watching"
    st.session_state["watching_list"] = HOLDINGS_PLAYLIST_LABEL
elif _prev == "Fund Watchlists":
    st.session_state[_SIDEBAR_KEY] = "Watching"
    st.session_state["watching_list"] = NEGEN_PLAYLIST_LABEL

with st.sidebar:
    page = st.radio(
        "Menu",
        _SIDEBAR_PAGES,
        label_visibility="collapsed",
        key=_SIDEBAR_KEY,
    )

if page == "Strategy":
    render_strategy()
elif page == "EarningsQ":
    render_earningsq()
elif page == "Sector Landscape":
    render_sector_landscape()
elif page == "SuperStars":
    render_superstars()
elif page == "Watching":
    render_watching()
elif page == "ValuePickr":
    render_valuepickr()
elif page == "Demergers":
    render_demerger()
