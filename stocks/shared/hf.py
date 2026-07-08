from huggingface_hub import InferenceClient

from stocks.core.config import get_hf_token


def is_valid_model_id(model_id: str) -> bool:
    if not model_id or model_id.startswith("hf_"):
        return False
    return "/" in model_id


def get_client() -> InferenceClient | None:
    token = get_hf_token()
    if not token:
        return None
    return InferenceClient(token=token)
