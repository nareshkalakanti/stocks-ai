"""JSON helpers — normalize pandas / numpy values for stdlib ``json``."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def is_nullish(val: Any) -> bool:
    if val is None:
        return True
    if val is pd.NA:
        return True
    try:
        return bool(pd.isna(val))
    except (TypeError, ValueError):
        return False


def json_safe_scalar(val: Any) -> Any:
    """Convert a scalar to a JSON-friendly value (``None`` for missing)."""
    if is_nullish(val):
        return None
    if isinstance(val, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(val).strftime("%Y-%m-%d")
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if isinstance(val, (np.floating, float)):
        return float(val)
    if isinstance(val, (np.integer, int)) and not isinstance(val, bool):
        return int(val)
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    return str(val)


def json_safe_obj(val: Any) -> Any:
    """Recursively normalize dicts / lists for ``json.dumps``."""
    if isinstance(val, dict):
        return {str(k): json_safe_obj(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [json_safe_obj(v) for v in val]
    return json_safe_scalar(val)


def json_dumps(obj: Any, **kwargs: Any) -> str:
    """``json.dumps`` after normalizing pandas scalars."""
    return json.dumps(json_safe_obj(obj), **kwargs)
