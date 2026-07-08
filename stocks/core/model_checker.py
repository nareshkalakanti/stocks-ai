import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from huggingface_hub import InferenceClient

from stocks.core.config import DATA_DIR, get_hf_token
from stocks.core.text_utils import response_text

MODEL_CHECKS_FILE = DATA_DIR / "model_checks.json"
CHECK_TTL_HOURS = 24

_PROBE_MESSAGES = [
    {"role": "system", "content": "You respond only with valid JSON arrays."},
    {
        "role": "user",
        "content": 'Return [{"ticker":"RELIANCE","score":8,"reason":"test"}] as JSON only.',
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_cache() -> dict:
    if not MODEL_CHECKS_FILE.exists():
        return {}
    try:
        return json.loads(MODEL_CHECKS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_CHECKS_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _cache_fresh(entry: dict | None) -> bool:
    if not entry:
        return False
    checked_at = entry.get("checked_at")
    if not checked_at:
        return False
    try:
        ts = datetime.fromisoformat(checked_at)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return _utc_now() - ts < timedelta(hours=CHECK_TTL_HOURS)


def check_chat_model(client: InferenceClient, model: str) -> tuple[bool, str]:
    try:
        response = client.chat_completion(
            messages=_PROBE_MESSAGES,
            model=model,
            max_tokens=128,
            temperature=0.1,
        )
        content = ""
        if response.choices:
            content = response_text(response.choices[0].message.content)
        if not content:
            return False, "Empty response from model"
        return True, "OK"
    except Exception as exc:
        message = str(exc)
        if "not a chat model" in message:
            return False, "Not a chat model on HF Inference API"
        if "model_not_supported" in message:
            return False, "Model not supported on HF Inference API"
        if "500 Internal Server Error" in message:
            return False, "Server error (try again later)"
        if len(message) > 120:
            message = message[:120] + "..."
        return False, message


def get_model_status(
    client: InferenceClient | None,
    model: str,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    cache = _load_cache()
    entry = cache.get(model)
    if not force and _cache_fresh(entry):
        return bool(entry.get("ok")), str(entry.get("message", ""))

    if client is None:
        return False, "HF_TOKEN not configured"

    ok, message = check_chat_model(client, model)
    cache[model] = {
        "ok": ok,
        "message": message,
        "checked_at": _utc_now().isoformat(),
    }
    _save_cache(cache)
    return ok, message


def check_models(
    client: InferenceClient | None,
    models: list[str],
    *,
    force: bool = False,
) -> dict[str, dict[str, str | bool]]:
    results: dict[str, dict[str, str | bool]] = {}
    for model in models:
        ok, message = get_model_status(client, model, force=force)
        results[model] = {"ok": ok, "message": message}
    return results


def working_models(
    client: InferenceClient | None,
    models: list[str],
    *,
    force: bool = False,
) -> list[str]:
    statuses = check_models(client, models, force=force)
    return [model for model in models if statuses[model]["ok"]]
