import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
DB_PATH = DATA_DIR / "stocks_ai.db"
STOCK_NOTES_PATH = DATA_DIR / "stock_notes.json"
ERROR_LOG_FILE = LOGS_DIR / "errors.log"

INDIA_STOCKS_DATASET = "kjhq/India-Stock-Symbols-and-Metadata"

load_dotenv(ENV_PATH)

STOCK_ANALYSIS_SQLITE_DIR = Path(
    os.getenv(
        "STOCK_ANALYSIS_SQLITE_DIR",
        "/Users/nareshkalakanti/Documents/stocks/stock-analysis/sqlite",
    )
)

METRICS_CACHE_HOURS = int(os.getenv("METRICS_CACHE_HOURS", "4"))
FUNDAMENTALS_CACHE_HOURS = int(os.getenv("FUNDAMENTALS_CACHE_HOURS", "24"))
MARKET_CAP_CACHE_HOURS = int(
    os.getenv("MARKET_CAP_CACHE_HOURS", str(max(FUNDAMENTALS_CACHE_HOURS, 168)))
)
# yfinance pacing (see yfinance_limits.py and README)
YFINANCE_REQUEST_DELAY = float(os.getenv("YFINANCE_REQUEST_DELAY", "0.45"))  # Fundamentals only
STRATEGY_MAX_WORKERS_CAP = int(os.getenv("STRATEGY_MAX_WORKERS_CAP", "32"))
STRATEGY_MAX_WORKERS = int(os.getenv("STRATEGY_MAX_WORKERS", str(STRATEGY_MAX_WORKERS_CAP)))
YFINANCE_THROTTLED_MAX_WORKERS = int(
    os.getenv("YFINANCE_THROTTLED_MAX_WORKERS", str(STRATEGY_MAX_WORKERS))
)
FUNDAMENTALS_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
FUNDAMENTALS_TOP_N = int(os.getenv("FUNDAMENTALS_TOP_N", "35"))
ROCE_EV_MIN_ROCE_PCT = float(os.getenv("ROCE_EV_MIN_ROCE_PCT", "15"))
ROCE_EV_MAX_EV_EBITDA = float(os.getenv("ROCE_EV_MAX_EV_EBITDA", "15"))
ROCE_EV_TOP_N = int(os.getenv("ROCE_EV_TOP_N", "0"))
MIN_MARKET_CAP_CR = float(os.getenv("MIN_MARKET_CAP_CR", "300"))
SCAN_MCAP_MIN_CR = float(os.getenv("SCAN_MCAP_MIN_CR", "300"))
# Headwind / Tailwind market board — lower floor, no upper cap.
HEADWIND_TAILWIND_MCAP_MIN_CR = float(os.getenv("HEADWIND_TAILWIND_MCAP_MIN_CR", "200"))
SCAN_MCAP_MAX_CR = float(os.getenv("SCAN_MCAP_MAX_CR", "3000"))
# Bulk-fetch market cap before scan only when universe is small; large scans filter per ticker.
SCAN_MCAP_PREFETCH_LIMIT = int(os.getenv("SCAN_MCAP_PREFETCH_LIMIT", "300"))
SCAN_UNIVERSE_MAX_WITHOUT_SECTOR = int(os.getenv("SCAN_UNIVERSE_MAX_WITHOUT_SECTOR", "400"))

# Market-cap tiers (INR Crores). Upper bound is exclusive except Large-cap (open-ended).
CAP_TIERS: list[dict[str, str | float | None]] = [
    {"id": "all", "label": "All caps", "min": None, "max": None},
    {
        "id": "range_100_3000",
        "label": "300–3,000 Cr",
        "min": SCAN_MCAP_MIN_CR,
        "max": SCAN_MCAP_MAX_CR + 0.01,
    },
    {"id": "nano", "label": "Nano-cap (< 100 Cr)", "min": 0, "max": 100},
    {"id": "micro", "label": "Micro-cap (100–500 Cr)", "min": 100, "max": 500},
    {"id": "small", "label": "Small-cap (500–5,000 Cr)", "min": 500, "max": 5000},
    {"id": "mid", "label": "Mid-cap (5,000–20,000 Cr)", "min": 5000, "max": 20000},
    {"id": "large", "label": "Large-cap (≥ 20,000 Cr)", "min": 20000, "max": None},
]
DEFAULT_CAP_TIER = os.getenv("DEFAULT_CAP_TIER", "all")
STRATEGY_BB_WORKERS_MIN = int(os.getenv("STRATEGY_BB_WORKERS_MIN", "4"))
STRATEGY_BB_WORKERS_MAX = int(os.getenv("STRATEGY_BB_WORKERS_MAX", "16"))
STRATEGY_TEST_LIMIT = int(os.getenv("STRATEGY_TEST_LIMIT", "100"))
STRATEGY_YFINANCE_TIMEOUT = int(os.getenv("STRATEGY_YFINANCE_TIMEOUT", "10"))
STRATEGY_FUTURE_TIMEOUT = int(os.getenv("STRATEGY_FUTURE_TIMEOUT", "0"))
# Max concurrent Yahoo HTTP calls (shared by Strategy + throttled scans; prevents Invalid Crumb)
STRATEGY_YFINANCE_MAX_INFLIGHT = int(
    os.getenv("STRATEGY_YFINANCE_MAX_INFLIGHT", str(min(16, STRATEGY_MAX_WORKERS_CAP)))
)

PEAD_DRIFT_DAYS = int(os.getenv("PEAD_DRIFT_DAYS", "63"))
PEAD_MIN_QUARTERS = int(os.getenv("PEAD_MIN_QUARTERS", "1"))
PEAD_CACHE_HOURS = int(os.getenv("PEAD_CACHE_HOURS", "24"))
PEAD_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
PEAD_MIN_STREAK = int(os.getenv("PEAD_MIN_STREAK", "1"))
PEAD_MAX_STREAK = int(os.getenv("PEAD_MAX_STREAK", "3"))
PEAD_MIN_HISTORY_QUARTERS = int(os.getenv("PEAD_MIN_HISTORY_QUARTERS", "8"))
PEAD_MIN_YOY_SALES_PCT = float(os.getenv("PEAD_MIN_YOY_SALES_PCT", "0"))
PEAD_REQUIRE_IMPROVING_YOY = os.getenv("PEAD_REQUIRE_IMPROVING_YOY", "true").lower() in (
    "1",
    "true",
    "yes",
)
PEAD_REQUIRE_OPM_ATH = os.getenv("PEAD_REQUIRE_OPM_ATH", "true").lower() in (
    "1",
    "true",
    "yes",
)
PEAD_REQUIRE_OPM_IMPROVING = os.getenv("PEAD_REQUIRE_OPM_IMPROVING", "true").lower() in (
    "1",
    "true",
    "yes",
)
PEAD_REQUIRE_EPS_ATH = os.getenv("PEAD_REQUIRE_EPS_ATH", "true").lower() in (
    "1",
    "true",
    "yes",
)
PEAD2_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
PEAD2_MIN_QUARTERS = int(os.getenv("PEAD2_MIN_QUARTERS", "4"))
PEAD2_SALES_BUST_QOQ_MIN = float(os.getenv("PEAD2_SALES_BUST_QOQ_MIN", "25"))
PEAD2_SALES_BUST_STREAK = int(os.getenv("PEAD2_SALES_BUST_STREAK", "2"))
PEAD2_CACHE_HOURS = int(os.getenv("PEAD2_CACHE_HOURS", "24"))
HEADWIND_PEAD_CACHE_HOURS = int(os.getenv("HEADWIND_PEAD_CACHE_HOURS", "168"))
HEADWIND_PEAD_BACKFILL_MAX = int(os.getenv("HEADWIND_PEAD_BACKFILL_MAX", "50"))
# Post-earnings return window: 0 = drift to latest close; >0 = cap at N trading days.
PEAD2_DRIFT_DAYS = int(os.getenv("PEAD2_DRIFT_DAYS", "0"))
# percentile = FF-style universe ranks (returns + growth + forward PE); absolute = per-row growth caps
PEAD2_SCORE_MODE = os.getenv("PEAD2_SCORE_MODE", "percentile").strip().lower()
PEAD2_CALC_VERSION = 9

PEAD_FACTOR_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
PEAD_FACTOR_SUE_WEIGHT = float(os.getenv("PEAD_FACTOR_SUE_WEIGHT", "0.65"))
PEAD_FACTOR_PEG_GROWTH_FLOOR = float(os.getenv("PEAD_FACTOR_PEG_GROWTH_FLOOR", "5"))
PEAD_FACTOR_FRESH_DAYS = int(os.getenv("PEAD_FACTOR_FRESH_DAYS", "10"))

# Reject distorted Yahoo EPS rows (low YoY base, NP/EPS share-count drift).
EARNINGS_MIN_PRIOR_EPS = float(os.getenv("EARNINGS_MIN_PRIOR_EPS", "0.10"))
EARNINGS_MAX_SHARE_RATIO = float(os.getenv("EARNINGS_MAX_SHARE_RATIO", "1.35"))
EARNINGS_MAX_EPS_YOY_PCT = float(os.getenv("EARNINGS_MAX_EPS_YOY_PCT", "200"))

VALUEPICKR_BASE_URL = os.getenv("VALUEPICKR_BASE_URL", "https://forum.valuepickr.com").rstrip("/")
VALUEPICKR_CATEGORY_ID = int(os.getenv("VALUEPICKR_CATEGORY_ID", "11"))
VALUEPICKR_MAX_PAGES = int(os.getenv("VALUEPICKR_MAX_PAGES", "5"))
VALUEPICKR_CACHE_HOURS = int(os.getenv("VALUEPICKR_CACHE_HOURS", "6"))
SUPERSTAR_CACHE_HOURS = int(os.getenv("SUPERSTAR_CACHE_HOURS", "24"))
CWIP_REJECT_INCREASE = os.getenv("CWIP_REJECT_INCREASE", "true").lower() in (
    "1",
    "true",
    "yes",
)
CWIP_MAX_INCREASE_PCT = float(os.getenv("CWIP_MAX_INCREASE_PCT", "0"))
CWIP_STRICT = os.getenv("CWIP_STRICT", "true").lower() in ("1", "true", "yes")
CWIP_TREND_QUARTERS = int(os.getenv("CWIP_TREND_QUARTERS", "3"))
CWIP_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
FORMULA_100X_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
VALUATION_FORMULA_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
INTRINSIC_VALUE_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
INTRINSIC_VALUE_CACHE_HOURS = int(os.getenv("INTRINSIC_VALUE_CACHE_HOURS", "24"))
HEADWIND_SCAN_CACHE_HOURS = int(os.getenv("HEADWIND_SCAN_CACHE_HOURS", "24"))

EARNINGS_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
EARNINGS_JUMP_MIN = float(os.getenv("EARNINGS_JUMP_MIN", "1.5"))
EARNINGS_TRAIL_QUARTERS = int(os.getenv("EARNINGS_TRAIL_QUARTERS", "3"))
EARNINGS_MAX_STREAK = int(os.getenv("EARNINGS_MAX_STREAK", "2"))
EARNINGS_MIN_MARGIN_ROOM_PP = float(os.getenv("EARNINGS_MIN_MARGIN_ROOM_PP", "2.0"))
EARNINGS_MIN_GAP_PCT = float(os.getenv("EARNINGS_MIN_GAP_PCT", "2.0"))
EARNINGS_MIN_VOL_RATIO = float(os.getenv("EARNINGS_MIN_VOL_RATIO", "2.0"))
EARNINGS_REQUIRE_PRICE = os.getenv("EARNINGS_REQUIRE_PRICE", "true").lower() in (
    "1",
    "true",
    "yes",
)

TURTLE_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
TURTLE_CONSOLIDATION_MIN_YEARS = float(os.getenv("TURTLE_CONSOLIDATION_MIN_YEARS", "10"))
TURTLE_CONSOLIDATION_MAX_YEARS = float(os.getenv("TURTLE_CONSOLIDATION_MAX_YEARS", "15"))
TURTLE_MIN_QUARTERS_PAT = int(os.getenv("TURTLE_MIN_QUARTERS_PAT", "4"))
TURTLE_PAT_LOOKBACK_QUARTERS = int(os.getenv("TURTLE_PAT_LOOKBACK_QUARTERS", "12"))
TURTLE_RS_OUTPERFORM_WEEKS = int(os.getenv("TURTLE_RS_OUTPERFORM_WEEKS", "52"))

import stocks.market.yfinance_limits as _yfinance_limits  # noqa: E402

_yfinance_limits.configure_yfinance_limits(max_inflight=STRATEGY_YFINANCE_MAX_INFLIGHT)


def yfinance_worker_count(job_count: int, max_workers: int | None = None) -> int:
    """Parallel workers for throttled yfinance scans (PEAD, Earnings, Turtle, Fundamentals)."""
    limit = max_workers if max_workers is not None else YFINANCE_THROTTLED_MAX_WORKERS
    return max(1, min(limit, STRATEGY_MAX_WORKERS_CAP, job_count))


def cap_tier_labels() -> list[str]:
    return [str(t["label"]) for t in CAP_TIERS]


def cap_tier_id_from_label(label: str) -> str:
    for t in CAP_TIERS:
        if t["label"] == label:
            return str(t["id"])
    return "all"
STOCKS_CACHE_HOURS = int(os.getenv("STOCKS_CACHE_HOURS", "24"))
REPORTS_CACHE_HOURS = int(os.getenv("REPORTS_CACHE_HOURS", "12"))

DEFAULT_TOP_N = int(os.getenv("DEFAULT_TOP_N", "10"))
MAX_TOP_N = int(os.getenv("MAX_TOP_N", "50"))
TOP_N_OPTIONS = [5, 10, 15, 20, 25, 30, 40, 50]


def tokens_for_top_n(top_n: int, user_max: int) -> int:
    """Ensure enough output tokens for a JSON array of `top_n` stock picks."""
    needed = top_n * 96 + 128
    return min(4096, max(user_max, needed))


DEFAULT_UNIVERSE_LIMIT = int(os.getenv("DEFAULT_UNIVERSE_LIMIT", "80"))
BATCH_UNIVERSE_LIMIT = 0  # scan all tickers in batches
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "80"))
BATCH_PICKS_PER_BATCH = int(os.getenv("BATCH_PICKS_PER_BATCH", "5"))
BATCH_SCORE_SIZE = int(os.getenv("BATCH_SCORE_SIZE", "35"))
LARGE_RUN_BATCH_WARN = int(os.getenv("LARGE_RUN_BATCH_WARN", "10"))
ANALYSIS_MODES: list[tuple[str, str]] = [
    ("picks", "Top picks"),
    ("all", "All filtered — score every stock"),
]
DEFAULT_ANALYSIS_MODE = os.getenv("DEFAULT_ANALYSIS_MODE", "picks")
UNIVERSE_LIMIT_OPTIONS: list[tuple[int, str]] = [
    (80, "80 — fast"),
    (150, "150"),
    (300, "300"),
    (500, "500"),
    (BATCH_UNIVERSE_LIMIT, "All — batched (full universe)"),
]

# Verified on HF Inference API chat_completion (router.huggingface.co).
VERIFIED_CHAT_MODELS = [
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen3-4B-Instruct-2507",
    "meta-llama/Meta-Llama-3-8B-Instruct",
]

# Chat models for stock screening via HF Inference API (Research page).
RECOMMENDED_LLM_MODELS = VERIFIED_CHAT_MODELS.copy()

# Time-series / price forecasting models.
LSTM_PREDICTION_MODEL = "SelvaprakashV/stock-prediction-model"
CHRONOS_PREDICTION_MODEL = "amazon/chronos-2"
DEFAULT_PREDICTION_MODEL = CHRONOS_PREDICTION_MODEL
PREDICTION_MODEL_FILE = "stock_dl_model.h5"
PREDICTION_HORIZON_DAYS = int(os.getenv("PREDICTION_HORIZON_DAYS", "5"))
PREDICTION_MODELS = [CHRONOS_PREDICTION_MODEL, LSTM_PREDICTION_MODEL]

RECOMMENDED_TS_MODELS = [
    {
        "id": CHRONOS_PREDICTION_MODEL,
        "note": "Zero-shot close forecast (120M) — default on Market Research · first run downloads weights",
    },
    {
        "id": LSTM_PREDICTION_MODEL,
        "note": "LSTM close forecast — TensorFlow local inference (NSE/BSE via yfinance)",
    },
    {
        "id": "Salesforce/moirai-2.0-R-small",
        "note": "Moirai-2 decoder transformer — probabilistic forecasts; CC-BY-NC-4.0 (non-commercial)",
    },
    {
        "id": "google/timesfm-2.5-200m-pytorch",
        "note": "TimesFM-2.5 (~200M, 16k context) — strong zero-shot; pip install timesfm[torch]",
    },
    {"id": "NeoQuasar/Kronos-base", "note": "Candlestick forecasting, global exchanges"},
    {"id": "Vincent05R/FinCast", "note": "Financial TS foundation, quantile outputs"},
    {"id": "mldi-lab/Kairos_50m", "note": "Lightweight zero-shot forecasting"},
    {"id": "bytedance-research/Timer-S1", "note": "Long-horizon TS (GPU/server)"},
]

# Sentiment models for financial news (HF text_classification).
DEFAULT_SENTIMENT_MODEL = "Vansh180/FinBERT-India-v1"
SENTIMENT_MODELS = [
    "Vansh180/FinBERT-India-v1",
    "kdave/FineTuned_Finbert",
    "StephanAkkerman/FinTwitBERT-sentiment",
    "ProsusAI/finbert",
]

RECOMMENDED_SENTIMENT_MODELS = [
    {
        "id": "Vansh180/FinBERT-India-v1",
        "note": "FinBERT fine-tuned on Indian financial news — positive/neutral/negative (primary)",
    },
    {
        "id": "kdave/FineTuned_Finbert",
        "note": "Indian stock market news sentiment — built on yiyanghkust/finbert-tone",
    },
    {"id": "StephanAkkerman/FinTwitBERT-sentiment", "note": "Finance/social BULLISH/BEARISH/NEUTRAL"},
    {"id": "ProsusAI/finbert", "note": "General financial sentiment fallback"},
    {
        "id": "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis",
        "note": "Fast headline sentiment (local / optional)",
    },
]

# Local / custom inference only — not on HF Inference API chat_completion.
RECOMMENDED_LOCAL_LLM_MODELS = [
    {
        "id": "bhaskartripathi/GPT_Neo_Market_Analysis",
        "note": "IndicFinGPT — GPT-Neo-125M on top Nifty/BSE names; bold Sharpe/Sortino claims, no independent benchmark — treat cautiously",
    },
]

MODEL_RECOMMENDATIONS: dict[str, str] = {
    "Qwen/Qwen2.5-7B-Instruct": "Primary — reliable JSON output and Indian sector reasoning",
    "Qwen/Qwen3-4B-Instruct-2507": "Newer Qwen3 — fast and works on HF Inference API",
    "meta-llama/Meta-Llama-3-8B-Instruct": "Llama 3 alternative — accept HF license first",
}

DEFAULT_MODELS = RECOMMENDED_LLM_MODELS.copy()


def load_models(*, include_unverified: bool = True) -> list[str]:
    env_models = os.getenv("HF_MODELS", "")
    if env_models.strip():
        models = [m.strip() for m in env_models.split(",") if m.strip()]
    else:
        models = DEFAULT_MODELS.copy()

    default = os.getenv("HF_MODEL", "").strip()
    if default and default not in models:
        models.insert(0, default)
    elif default:
        models.remove(default)
        models.insert(0, default)

    if include_unverified:
        return models

    from stocks.core.model_checker import working_models
    from stocks.shared.hf import get_client

    verified = working_models(get_client(), models)
    return verified or models[:1]


def get_hf_token() -> str | None:
    token = os.getenv("HF_TOKEN", "").strip()
    return token or None
