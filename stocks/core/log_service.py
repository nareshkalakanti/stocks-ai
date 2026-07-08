import logging
from pathlib import Path

from stocks.core.config import ERROR_LOG_FILE, LOGS_DIR

# Error categories for filtering in logs/errors.log
STOCK_NOT_FOUND = "STOCK_NOT_FOUND"
PRICE_ERROR = "PRICE_ERROR"
METRICS_ERROR = "METRICS_ERROR"
ANALYSIS_ERROR = "ANALYSIS_ERROR"
DATASET_ERROR = "DATASET_ERROR"
SENTIMENT_ERROR = "SENTIMENT_ERROR"
NEWS_ERROR = "NEWS_ERROR"
PREDICTION_ERROR = "PREDICTION_ERROR"

_logger: logging.Logger | None = None


def _ensure_log_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_error_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _ensure_log_dir()
    logger = logging.getLogger("stocks.errors")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.FileHandler(ERROR_LOG_FILE, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)

    _logger = logger
    return logger


def log_error(
    category: str,
    message: str,
    *,
    ticker: str | None = None,
    symbol: str | None = None,
    **extra: str,
) -> None:
    parts = [category]
    if ticker:
        parts.append(f"ticker={ticker}")
    if symbol:
        parts.append(f"symbol={symbol}")
    for key, value in extra.items():
        parts.append(f"{key}={value}")
    parts.append(f"msg={message}")
    get_error_logger().info(" | ".join(parts))


def read_recent_errors(limit: int = 50) -> list[str]:
    if not ERROR_LOG_FILE.exists():
        return []
    lines = ERROR_LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    return lines[-limit:][::-1]


def filter_errors(category: str | None = None, limit: int = 100) -> list[str]:
    lines = read_recent_errors(limit=500)
    if not category:
        return lines[:limit]
    filtered = [line for line in lines if f"{category} |" in line]
    return filtered[:limit]
