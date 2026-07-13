import streamlit as st

from stocks.market.yfinance_utils import install_yfinance_noise_filters

install_yfinance_noise_filters()
from stocks.core.database import init_db
from stocks.pages.headwind_tailwind import render_headwind_tailwind
from stocks.pages.holdings import render_holdings
from stocks.pages.sector_landscape import render_sector_landscape
from stocks.pages.strategy import render_strategy
from stocks.pages.superstars import render_superstars
from stocks.pages.valuepickr import render_valuepickr
from stocks.pages.demerger import render_demerger

st.set_page_config(
    page_title="AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

with st.sidebar:
    page = st.radio(
        "Menu",
        [
            "Strategy",
            "H&T",
            "Sector Landscape",
            "SuperStars",
            "Holdings",
            "ValuePickr",
            "Demergers",
        ],
        label_visibility="collapsed",
    )

if page == "Strategy":
    render_strategy()
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
elif page == "Demergers":
    render_demerger()
