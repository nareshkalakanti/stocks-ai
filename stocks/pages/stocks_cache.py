"""Cached India listings load — shared across Strategy / PEAD / Governance pages."""

from __future__ import annotations

import streamlit as st

from stocks.core.config import STOCKS_CACHE_HOURS
from stocks.listings.stocks_data import load_india_stocks


@st.cache_data(ttl=STOCKS_CACHE_HOURS * 3600, show_spinner=False)
def load_stocks_cached() -> "object":
    """Return listings DataFrame; TTL matches ``STOCKS_CACHE_HOURS`` (default 24h)."""
    return load_india_stocks()
