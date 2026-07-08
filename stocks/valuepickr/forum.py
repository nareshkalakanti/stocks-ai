"""ValuePickr Discourse forum API helpers."""

from __future__ import annotations

import re
from html import unescape

import requests

from stocks.core.config import VALUEPICKR_BASE_URL
from stocks.core.text_utils import safe_str

_USER_AGENT = (
    "Mozilla/5.0 (compatible; stocks-ai/1.0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Subcategories under Stock Opportunities (parent id 11).
VP_SUBCATEGORIES: dict[int, str] = {
    11: "Stock Opportunities",
    18: "Not-so-Hidden Gems",
    19: "Untested - but worth a good look",
    34: "My Top 5 Picks",
    36: "Techno-Funda Picks",
    37: "Special Situations",
    68: "Unlisted Shares",
    69: "SME Stocks",
}


def topic_url(topic_id: int, slug: str | None = None) -> str:
    slug = safe_str(slug) or f"topic-{topic_id}"
    return f"{VALUEPICKR_BASE_URL}/t/{slug}/{topic_id}"


def parse_topic_url(url: str) -> tuple[int | None, str | None]:
    """Extract topic id from a ValuePickr thread URL."""
    text = safe_str(url)
    if not text:
        return None, None
    m = re.search(r"/t/([^/]+)/(\d+)", text)
    if m:
        return int(m.group(2)), m.group(1)
    m = re.search(r"/t/(\d+)", text)
    if m:
        return int(m.group(1)), None
    return None, None


def strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return unescape(re.sub(r"\s+", " ", text)).strip()


def _get_json(path: str, *, params: dict | None = None, timeout: int = 20) -> dict | None:
    url = path if path.startswith("http") else f"{VALUEPICKR_BASE_URL}{path}"
    try:
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def fetch_category_topics(
    category_id: int,
    *,
    slug: str | None = None,
    max_pages: int = 5,
) -> list[dict]:
    """Active discussions from a category (Discourse JSON API)."""
    slug = safe_str(slug) or f"category-{category_id}"
    out: list[dict] = []
    for page in range(max_pages):
        data = _get_json(f"/c/{slug}/{category_id}.json", params={"page": page})
        if not data:
            break
        topics = data.get("topic_list", {}).get("topics") or []
        if not topics:
            break
        for t in topics:
            if t.get("archetype") != "regular":
                continue
            tid = int(t.get("id") or 0)
            if not tid:
                continue
            out.append(
                {
                    "topic_id": tid,
                    "title": safe_str(t.get("title")),
                    "slug": safe_str(t.get("slug")),
                    "url": topic_url(tid, t.get("slug")),
                    "posts_count": int(t.get("posts_count") or 0),
                    "reply_count": int(t.get("reply_count") or 0),
                    "views": int(t.get("views") or 0),
                    "likes": int(t.get("like_count") or 0),
                    "created_at": t.get("created_at"),
                    "last_posted_at": t.get("last_posted_at"),
                    "category_id": int(t.get("category_id") or category_id),
                    "subcategory": VP_SUBCATEGORIES.get(
                        int(t.get("category_id") or category_id),
                        VP_SUBCATEGORIES.get(category_id, "Stock Opportunities"),
                    ),
                }
            )
        if len(topics) < 30:
            break
    return out


def fetch_topic_meta(topic_id: int) -> dict | None:
    data = _get_json(f"/t/{topic_id}.json")
    if not data:
        return None
    return {
        "topic_id": topic_id,
        "title": safe_str(data.get("title")),
        "slug": safe_str(data.get("slug")),
        "url": topic_url(topic_id, data.get("slug")),
        "posts_count": int(data.get("posts_count") or 0),
        "views": int(data.get("views") or 0),
        "created_at": data.get("created_at"),
        "last_posted_at": data.get("last_posted_at"),
        "category_id": data.get("category_id"),
    }


def fetch_topic_posts(
    topic_id: int,
    *,
    max_pages: int = 30,
    max_posts: int = 600,
) -> list[dict]:
    """Paginated post stream (~20 posts per page)."""
    posts: list[dict] = []
    for page in range(max_pages):
        data = _get_json(f"/t/{topic_id}.json", params={"page": page})
        if not data:
            break
        batch = data.get("post_stream", {}).get("posts") or []
        if not batch:
            break
        for p in batch:
            posts.append(
                {
                    "post_id": int(p.get("id") or 0),
                    "post_number": int(p.get("post_number") or 0),
                    "username": safe_str(p.get("username")),
                    "created_at": p.get("created_at"),
                    "cooked": safe_str(p.get("cooked")),
                    "text": strip_html(p.get("cooked")),
                    "like_count": int(p.get("like_count") or 0),
                }
            )
        if len(batch) < 20 or len(posts) >= max_posts:
            break
    return posts[:max_posts]
