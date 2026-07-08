"""ValuePickrGPT — forum thread analysis via HF chat completion."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pandas as pd
from huggingface_hub import InferenceClient

from stocks.core.database import load_valuepickr_analysis, save_valuepickr_analysis
from stocks.core.text_utils import response_text, safe_str
from stocks.valuepickr.forum import fetch_topic_meta, fetch_topic_posts, parse_topic_url

VALUEPICKR_GPT_SYSTEM = """You are ValuePickrGPT. Your role is to analyse forum discussions on the ValuePickr Forum and perform time-wise sentiment analysis of a company from a long-term investment perspective.

When given forum posts, respond ONLY with valid JSON (no markdown fences) using this schema:
{
  "company": "string",
  "strengths": ["up to 10 bullet strings — long-term investment strengths"],
  "weaknesses": ["up to 10 bullet strings — long-term investment weaknesses/risks"],
  "monthly_sentiment": [
    {
      "month": "YYYY-MM",
      "score": 1-100,
      "keywords": ["phrases that drove the score"],
      "note": "one sentence summary"
    }
  ],
  "summary_2025": ["enumerated points from 2025 discussion only"]
}

Rules:
- Sentiment score 100 = most positive for long-term investors; 1 = most negative.
- Cover every month from the thread start through July 2025 (inclusive). Skip months with no posts.
- strengths and weaknesses: max 10 items each, enumerated insights from the full thread.
- summary_2025: only posts dated in 2025; max 10 points.
- Be specific — cite business factors (growth, margins, governance, valuation, moat, risks).
"""

ANALYSIS_CACHE_HOURS = 168


def _month_key(ts: str | None) -> str | None:
    if not ts:
        return None
    try:
        return pd.Timestamp(ts).strftime("%Y-%m")
    except Exception:
        return None


def posts_by_month(posts: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {}
    for p in posts:
        key = _month_key(p.get("created_at"))
        if not key:
            continue
        buckets.setdefault(key, []).append(p)
    return buckets


def _truncate(text: str, limit: int = 400) -> str:
    text = safe_str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def build_analysis_prompt(
    title: str,
    posts: list[dict],
    *,
    max_chars: int = 28000,
) -> str:
    """Compact monthly digest for the LLM."""
    by_month = posts_by_month(posts)
    lines = [f"Thread title: {title}", f"Total posts supplied: {len(posts)}", ""]
    used = 0
    for month in sorted(by_month.keys()):
        chunk_posts = by_month[month]
        header = f"## {month} ({len(chunk_posts)} posts)"
        block_lines = [header]
        for p in chunk_posts[:12]:
            line = (
                f"- @{p.get('username','?')} ({str(p.get('created_at',''))[:10]}): "
                f"{_truncate(p.get('text',''), 350)}"
            )
            block_lines.append(line)
        if len(chunk_posts) > 12:
            block_lines.append(f"- … plus {len(chunk_posts) - 12} more posts this month")
        block = "\n".join(block_lines) + "\n"
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines)


def _parse_gpt_json(raw: str) -> dict | None:
    text = response_text(raw).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def render_analysis_markdown(data: dict) -> str:
    company = safe_str(data.get("company")) or "Company"
    md = [f"## ValuePickrGPT — {company}", ""]

    strengths = data.get("strengths") or []
    if strengths:
        md.append("### Strengths (long-term)")
        for i, s in enumerate(strengths[:10], 1):
            md.append(f"{i}. {s}")
        md.append("")

    weaknesses = data.get("weaknesses") or []
    if weaknesses:
        md.append("### Weaknesses / risks (long-term)")
        for i, w in enumerate(weaknesses[:10], 1):
            md.append(f"{i}. {w}")
        md.append("")

    monthly = data.get("monthly_sentiment") or []
    if monthly:
        md.append("### Monthly sentiment (1–100)")
        md.append("| Month | Score | Keywords / drivers | Note |")
        md.append("|-------|------:|--------------------|------|")
        for row in monthly:
            month = safe_str(row.get("month"))
            score = row.get("score", "—")
            kws = ", ".join(row.get("keywords") or []) or "—"
            note = safe_str(row.get("note")) or "—"
            md.append(f"| {month} | {score} | {kws} | {note} |")
        md.append("")

    summary_2025 = data.get("summary_2025") or []
    if summary_2025:
        md.append("### 2025 discussion summary")
        for i, point in enumerate(summary_2025[:10], 1):
            md.append(f"{i}. {point}")

    return "\n".join(md)


def analyze_thread_with_gpt(
    client: InferenceClient,
    model: str,
    *,
    url: str,
    max_tokens: int = 4096,
    temperature: float = 0.25,
    use_cache: bool = True,
) -> dict:
    topic_id, _slug = parse_topic_url(url)
    if topic_id is None:
        raise ValueError("Could not parse topic id from URL")

    if use_cache:
        cached = load_valuepickr_analysis(topic_id, max_hours=ANALYSIS_CACHE_HOURS)
        if cached:
            return cached

    meta = fetch_topic_meta(topic_id)
    if not meta:
        raise ValueError(f"Topic {topic_id} not found on ValuePickr")

    posts = fetch_topic_posts(topic_id)
    if not posts:
        raise ValueError("No posts returned for this thread")

    title = meta.get("title") or f"Topic {topic_id}"
    user_prompt = build_analysis_prompt(title, posts)

    response = client.chat_completion(
        messages=[
            {"role": "system", "content": VALUEPICKR_GPT_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = ""
    if response.choices:
        content = response_text(response.choices[0].message.content)

    parsed = _parse_gpt_json(content)
    if not parsed:
        raise ValueError("Model did not return valid JSON. Try again or use a stronger chat model.")

    analysis_md = render_analysis_markdown(parsed)
    result = {
        "topic_id": topic_id,
        "url": meta.get("url") or url,
        "title": title,
        "company": safe_str(parsed.get("company")) or title,
        "analysis_md": analysis_md,
        "strengths": parsed.get("strengths") or [],
        "weaknesses": parsed.get("weaknesses") or [],
        "monthly_sentiment": parsed.get("monthly_sentiment") or [],
        "summary_2025": parsed.get("summary_2025") or [],
        "posts_count": len(posts),
        "analyzed_through": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    save_valuepickr_analysis(result)
    return result
