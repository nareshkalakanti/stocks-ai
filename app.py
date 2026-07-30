import streamlit as st

from stocks.core.streamlit_compat import normalize_radio_session_state
from stocks.market.yfinance_utils import install_yfinance_noise_filters

install_yfinance_noise_filters()
from stocks.core.database import ensure_db, init_db
from stocks.governance.db import init_governance_db
from stocks.pages.holdings import render_holdings
from stocks.pages.sector_landscape import render_sector_landscape
from stocks.pages.strategy import render_strategy
from stocks.pages.superstars import render_superstars
from stocks.pages.valuepickr import render_valuepickr
from stocks.pages.demerger import render_demerger
from stocks.pages.earningsq import render_earningsq
from stocks.pages.fund_watchlists import render_fund_watchlists

st.set_page_config(
    page_title="AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_db()
init_governance_db()

_SIDEBAR_PAGES = [
    "Strategy",
    "EarningsQ",
    "Sector Landscape",
    "SuperStars",
    "Holdings",
    "Fund Watchlists",
    "ValuePickr",
    "Demergers",
]
# v6: Fund Watchlists (Negen / Niveshaay)
_SIDEBAR_KEY = "app_sidebar_page_v6"

normalize_radio_session_state(_SIDEBAR_KEY, _SIDEBAR_PAGES)

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
elif page == "Holdings":
    render_holdings()
elif page == "Fund Watchlists":
    render_fund_watchlists()
elif page == "ValuePickr":
    render_valuepickr()
elif page == "Demergers":
    render_demerger()
