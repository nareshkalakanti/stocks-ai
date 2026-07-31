"""Streamlit pagination bar for large Watching lists (NSE / NSE SME)."""

from __future__ import annotations

import streamlit as st

from stocks.core.text_utils import safe_str

_PAGINATION_CSS = """
<style>
  .watch-pager-shell {
    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    margin: 0 0 10px;
  }
  .watch-pager-shell.bottom { margin: 10px 0 0; }
  .watch-pager-stats {
    display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
    gap: 6px 12px; margin-bottom: 8px;
  }
  .watch-pager-stats .primary {
    font-size: 13px; font-weight: 650; color: #111827;
  }
  .watch-pager-stats .primary b { color: #9f1239; font-weight: 800; }
  .watch-pager-stats .secondary {
    font-size: 11px; color: #6b7280; font-weight: 500;
  }
  .watch-pager-nav {
    display: flex; flex-wrap: wrap; align-items: center; justify-content: center;
    gap: 6px; padding: 8px 10px; background: #f8fafc;
    border: 1px solid #e5e7eb; border-radius: 10px;
  }
  .watch-pager-badge {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 88px; padding: 6px 12px; border-radius: 999px;
    background: #fff; border: 1px solid #fecdd3; color: #9f1239;
    font-size: 13px; font-weight: 800; letter-spacing: -0.01em;
    box-shadow: 0 1px 2px rgba(159, 18, 57, 0.06);
  }
  .watch-pager-badge span { color: #6b7280; font-weight: 600; margin: 0 4px; }
</style>
"""


def inject_watching_pagination_css() -> None:
    if st.session_state.get("_watching_pagination_css"):
        return
    st.markdown(_PAGINATION_CSS, unsafe_allow_html=True)
    st.session_state["_watching_pagination_css"] = True


def render_watching_pagination(
    list_label: str,
    *,
    page: int,
    total_pages: int,
    total_rows: int,
    page_size: int,
    page_key: str,
    position: str = "top",
) -> None:
    """Bordered pager: First / Prev · Page X of Y · jump · Next / Last."""
    inject_watching_pagination_css()

    start = (page - 1) * page_size + 1 if total_rows else 0
    end = min(page * page_size, total_rows)
    pos = safe_str(position) or "top"
    slug = list_label.lower().replace(" ", "_")

    st.markdown(
        f'<div class="watch-pager-shell {pos}">'
        f'<div class="watch-pager-stats">'
        f'<div class="primary">Showing <b>{start:,}–{end:,}</b> of <b>{total_rows:,}</b> names</div>'
        f'<div class="secondary">{page_size} per page · {list_label}</div>'
        f"</div></div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        nav = st.columns(
            [0.62, 0.62, 1.35, 0.85, 0.48, 0.62, 0.62],
            vertical_alignment="center",
            gap="small",
        )
        with nav[0]:
            if st.button(
                "⏮ First",
                use_container_width=True,
                disabled=page <= 1,
                key=f"watch_pager_first_{slug}_{pos}",
            ):
                st.session_state[page_key] = 1
                st.rerun()
        with nav[1]:
            if st.button(
                "← Prev",
                use_container_width=True,
                disabled=page <= 1,
                key=f"watch_pager_prev_{slug}_{pos}",
            ):
                st.session_state[page_key] = page - 1
                st.rerun()
        with nav[2]:
            st.markdown(
                f'<div class="watch-pager-nav" style="margin:0;border:0;background:transparent;padding:0;">'
                f'<div class="watch-pager-badge">Page {page:,} <span>of</span> {total_pages:,}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with nav[3]:
            jump_to = st.number_input(
                "Page",
                min_value=1,
                max_value=max(1, total_pages),
                value=page,
                step=1,
                key=f"watch_pager_jump_{slug}_{pos}",
                label_visibility="collapsed",
            )
        with nav[4]:
            if st.button(
                "Go",
                use_container_width=True,
                key=f"watch_pager_go_{slug}_{pos}",
            ):
                target = max(1, min(int(jump_to), total_pages))
                if target != page:
                    st.session_state[page_key] = target
                    st.rerun()
        with nav[5]:
            if st.button(
                "Next →",
                use_container_width=True,
                disabled=page >= total_pages,
                key=f"watch_pager_next_{slug}_{pos}",
            ):
                st.session_state[page_key] = page + 1
                st.rerun()
        with nav[6]:
            if st.button(
                "Last ⏭",
                use_container_width=True,
                disabled=page >= total_pages,
                key=f"watch_pager_last_{slug}_{pos}",
            ):
                st.session_state[page_key] = total_pages
                st.rerun()
