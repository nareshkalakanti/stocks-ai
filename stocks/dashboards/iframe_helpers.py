"""Streamlit iframe embed for in-app HTML dashboards."""

from __future__ import annotations

import tempfile
from pathlib import Path


def embed_html_iframe(html_content: str, *, height: int | str = "content") -> None:
    """Embed HTML dashboard in Streamlit (uses st.iframe, not deprecated components.html)."""
    import streamlit as st

    # Large dashboards render more reliably from a file than inline srcdoc.
    if isinstance(html_content, str) and len(html_content) > 80_000:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(html_content)
            live_path = Path(tmp.name)
        st.iframe(live_path, height=height, width="stretch")
        return

    st.iframe(html_content, height=height, width="stretch")
