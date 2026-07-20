"""Streamlit embed for in-app HTML dashboards."""

from __future__ import annotations

import html as html_mod


def _embed_height(height: int | str) -> int:
    if height == "content":
        return 800
    return int(height)


def embed_html_iframe(
    html_content: str,
    *,
    height: int | str = "content",
    key: str | None = None,
    allow_top_navigation: bool = False,
) -> None:
    """Render HTML inline in the app (no temp files or file:// URLs)."""
    _ = key  # reserved for callers; components.html has no key param
    h = _embed_height(height)
    if allow_top_navigation:
        import streamlit as st

        sandbox = (
            "allow-scripts allow-same-origin allow-forms allow-popups allow-downloads "
            "allow-top-navigation-by-user-activation"
        )
        srcdoc = html_mod.escape(html_content, quote=True)
        st.markdown(
            f'<iframe srcdoc="{srcdoc}" sandbox="{sandbox}" scrolling="yes" '
            f'style="width:100%;height:{h}px;border:none;display:block;" '
            f'title="dashboard"></iframe>',
            unsafe_allow_html=True,
        )
        return

    import streamlit.components.v1 as components

    components.html(html_content, height=h, scrolling=True)
