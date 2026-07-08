import streamlit as st

from stocks.core.config import load_models
from stocks.market.yfinance_utils import install_yfinance_noise_filters

install_yfinance_noise_filters()
from stocks.core.database import init_db
from stocks.shared.hf import get_client
from stocks.pages.headwind_tailwind import render_headwind_tailwind
from stocks.pages.holdings import render_holdings
from stocks.pages.pead2 import render_pead2
from stocks.pages.sector_landscape import render_sector_landscape
from stocks.pages.settings import init_session_state, render_settings
from stocks.pages.superstars import render_superstars
from stocks.pages.valuepickr import render_valuepickr
from stocks.pages.strategy import render_strategy

st.set_page_config(
    page_title="Stocks AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

client = get_client()
models = load_models()
init_session_state(models)

with st.sidebar:
    page = st.radio(
        "Menu",
        [
            "Settings",
            "Strategy",
            "PEAD",
            "H&T",
            "Sector Landscape",
            "SuperStars",
            "Holdings",
            "ValuePickr",
        ],
        label_visibility="collapsed",
    )

if page == "Settings":
    render_settings(client, models)
elif page == "Strategy":
    render_strategy()
elif page == "PEAD":
    render_pead2()
elif page == "H&T":
    render_headwind_tailwind()
elif page == "Sector Landscape":
    render_sector_landscape()
elif page == "SuperStars":
    render_superstars()
elif page == "Holdings":
    render_holdings()
elif page == "ValuePickr":
    render_valuepickr()
