"""Streamlit embed for in-app HTML dashboards."""

from __future__ import annotations


def _embed_height(height: int | str) -> int:
    if height == "content":
        return 800
    return int(height)


def embed_html_iframe(
    html_content: str,
    *,
    height: int | str = "content",
    key: str | None = None,
) -> None:
    """Render HTML inline in the app (no temp files or file:// URLs)."""
    import streamlit.components.v1 as components

    _ = key  # reserved for callers; components.html has no key param
    components.html(html_content, height=_embed_height(height), scrolling=True)
