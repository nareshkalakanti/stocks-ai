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
    """Render HTML inline in the app (no temp files or file:// URLs).

    Large dashboards must use Streamlit's iframe embed. Markdown ``srcdoc`` is
    only safe for tiny HTML; PEAD/H&T boards are far too large.
    """
    _ = key  # reserved for callers
    h = _embed_height(height)

    # Prefer markdown srcdoc only for small HTML that needs top navigation.
    if allow_top_navigation and len(html_content) < 40_000:
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

    import streamlit as st

    # Streamlit 1.58+: st.iframe replaces components.v1.html.
    if hasattr(st, "iframe"):
        st.iframe(html_content, width="stretch", height=h)
        return

    import streamlit.components.v1 as components

    components.html(html_content, height=h, scrolling=True)
