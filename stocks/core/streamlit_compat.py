"""Small helpers for Streamlit version / session-state quirks."""

from __future__ import annotations


def normalize_radio_session_state(key: str, options: list[str]) -> None:
    """
    After Streamlit upgrades, radio widget state can be a stale index (``0`` / ``"0"``)
    or an old ``int_value`` wire format — which crashes widget registration
    (``TypeError: '1' has type str, but expected one of: int``).

    Coerce index-like values to option labels; drop anything else invalid.
    """
    import streamlit as st

    if key not in st.session_state:
        return
    val = st.session_state[key]
    if val in options:
        return
    idx: int | None = None
    if isinstance(val, bool):
        # bool is a subclass of int — treat as invalid for radio labels
        st.session_state.pop(key, None)
        return
    if isinstance(val, int):
        idx = val
    elif isinstance(val, str) and val.isdigit():
        idx = int(val)
    if idx is not None and 0 <= idx < len(options):
        st.session_state[key] = options[idx]
        return
    # Unknown / corrupt — clear so the widget re-inits cleanly
    st.session_state.pop(key, None)


def iframe_width_kw() -> dict:
    """Full-width ``st.iframe`` across Streamlit 1.42–1.60+."""
    import inspect

    import streamlit as st

    if not hasattr(st, "iframe"):
        return {}
    params = inspect.signature(st.iframe).parameters
    if "width" in params:
        return {"width": "stretch"}
    if "use_container_width" in params:
        return {"use_container_width": True}
    return {}
