"""Streamlit embed for in-app HTML dashboards.

Large boards (>~350KB) cannot reliably ride Streamlit's websocket, so they are
written to a runtime-only ``static/`` cache and loaded via ``/app/static/...``
(requires ``server.enableStaticServing = true``). That folder is gitignored —
it is not part of the product tree.
"""

from __future__ import annotations

import html as html_mod
import hashlib
from pathlib import Path

# Streamlit serves only app-root ./static at /app/static/ (runtime cache).
_STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
_STATIC_URL_PREFIX = "/app/static/"
_KEEP_PER_STEM = 1
_STATIC_MIN_BYTES = 350_000


def _embed_height(height: int | str) -> int:
    if height == "content":
        return 800
    return int(height)


def _prune_static(stem: str, *, keep: int = _KEEP_PER_STEM) -> None:
    stale = sorted(
        _STATIC_DIR.glob(f"{stem}-*.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in stale[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def _write_static_html(html_content: str, *, stem: str = "dashboard") -> str | None:
    """Write HTML into the runtime static cache; return /app/static/... URL."""
    try:
        _STATIC_DIR.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(html_content.encode("utf-8", errors="ignore")).hexdigest()[:10]
        name = f"{stem}-{digest}.html"
        path = _STATIC_DIR / name
        if not path.is_file():
            path.write_text(html_content, encoding="utf-8")
        _prune_static(stem)
        return f"{_STATIC_URL_PREFIX}{name}"
    except OSError:
        return None


def embed_html_iframe(
    html_content: str,
    *,
    height: int | str = "content",
    key: str | None = None,
    allow_top_navigation: bool = False,
    static_stem: str | None = "dashboard",
) -> None:
    """Render HTML inline in the app (no committed assets)."""
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

    from stocks.core.streamlit_compat import iframe_width_kw

    use_static = static_stem and len(html_content) >= _STATIC_MIN_BYTES
    if use_static:
        url = _write_static_html(html_content, stem=str(static_stem))
        if url and hasattr(st, "iframe"):
            st.iframe(url, height=h, **iframe_width_kw())
            return

    if hasattr(st, "iframe") and len(html_content) < 1_800_000:
        st.iframe(html_content, height=h, **iframe_width_kw())
        return

    import streamlit.components.v1 as components

    components.html(html_content, height=h, scrolling=True)
