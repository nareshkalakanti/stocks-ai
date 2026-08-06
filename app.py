import streamlit as st

from stocks.core.streamlit_compat import normalize_radio_session_state
from stocks.market.yfinance_utils import install_yfinance_noise_filters

install_yfinance_noise_filters()
from stocks.core.database import ensure_db
from stocks.governance.db import init_governance_db, ensure_governance_db_seeded
from stocks.pages.strategy import render_strategy
from stocks.pages.superstars import render_superstars
from stocks.pages.data_hub import render_data
from stocks.shared.early_edge import ensure_early_edge_seeded

st.set_page_config(
    page_title="AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_db()
ensure_governance_db_seeded()
init_governance_db()
ensure_early_edge_seeded()

_SIDEBAR_PAGES = [
    "Strategy",
    "SuperStars",
    "Data",
]
# v9: EarningsQ + Watching moved under Strategy (like Governance / Gmap)
_SIDEBAR_KEY = "app_sidebar_page_v9"
_STRATEGY_SECTION_KEY = "strategy_section_v3"

normalize_radio_session_state(_SIDEBAR_KEY, _SIDEBAR_PAGES)

# Migrate removed sidebar pages → Strategy (or Data).
_prev = st.session_state.get(_SIDEBAR_KEY)
_legacy = st.session_state.get("app_sidebar_page_v8")
if _prev in {"EarningsQ", "Watching"}:
    target = _prev
    st.session_state[_SIDEBAR_KEY] = "Strategy"
    st.session_state[_STRATEGY_SECTION_KEY] = target
elif _legacy in {"EarningsQ", "Watching"} and _prev not in _SIDEBAR_PAGES:
    st.session_state[_SIDEBAR_KEY] = "Strategy"
    st.session_state[_STRATEGY_SECTION_KEY] = _legacy
elif _prev in {"IPO", "ValuePickr", "Demergers", "Sector Landscape"}:
    st.session_state[_SIDEBAR_KEY] = "Strategy"

with st.sidebar:
    page = st.radio(
        "Menu",
        _SIDEBAR_PAGES,
        label_visibility="collapsed",
        key=_SIDEBAR_KEY,
    )

if page == "Strategy":
    render_strategy()
elif page == "SuperStars":
    render_superstars()
elif page == "Data":
    render_data()
