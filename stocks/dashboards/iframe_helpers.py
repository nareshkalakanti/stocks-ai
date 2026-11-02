"""Streamlit embed for in-app HTML dashboards."""

from __future__ import annotations

import html as html_mod
import hashlib
from pathlib import Path

from stocks.core.config import DATA_DIR

_DASHBOARD_CACHE_DIR = DATA_DIR / "dashboard_cache"
# Large PEAD boards blow past reliable srcdoc/websocket limits — file embed is safer.
_LARGE_HTML_BYTES = 750_000


def _embed_height(height: int | str) -> int:
    if height == "content":
        return 800
    return int(height)


def _write_dashboard_html(html_content: str, *, stem: str | None = None) -> Path:
    _DASHBOARD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(html_content.encode("utf-8", errors="ignore")).hexdigest()[:12]
    name = f"{stem or 'dash'}_{digest}.html"
    path = _DASHBOARD_CACHE_DIR / name
    if not path.is_file() or path.stat().st_size != len(html_content.encode("utf-8")):
        path.write_text(html_content, encoding="utf-8")
    return path


def embed_html_iframe(
    html_content: str,
    *,
    height: int | str = "content",
    key: str | None = None,
    allow_top_navigation: bool = False,
    static_stem: str | None = None,
) -> None:
    """Render HTML via ``st.iframe`` (file for large boards) or ``components.html``."""
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

    use_file = len(html_content) >= _LARGE_HTML_BYTES
    if hasattr(st, "iframe"):
        try:
            if use_file:
                path = _write_dashboard_html(html_content, stem=static_stem or key or "dash")
                st.iframe(path, height=h, **iframe_width_kw())
            else:
                st.iframe(html_content, height=h, **iframe_width_kw())
            return
        except Exception:
            # Fall through to components.html
            pass

    import streamlit.components.v1 as components

    components.html(html_content, height=h, scrolling=True)
