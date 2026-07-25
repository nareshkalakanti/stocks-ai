"""Streamlit helpers that stay usable when the process hits EMFILE."""

from __future__ import annotations

import streamlit as st


def show_error(message: str) -> None:
    """Show an error without relying on Streamlit emoji imports (can fail at EMFILE)."""
    try:
        st.error(message)
    except OSError:
        st.markdown(f"**Error:** {message}")
