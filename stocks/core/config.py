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
# ff = FinanciallyFree-style signed score; percentile = universe ranks; absolute = 0–100 per-row
PEAD2_SCORE_MODE = os.getenv("PEAD2_SCORE_MODE", "ff").strip().lower()
PEAD_RESULT_LAG_DAYS = int(os.getenv("PEAD_RESULT_LAG_DAYS", "45"))
PEAD2_DAILY_RET_CAP = float(os.getenv("PEAD2_DAILY_RET_CAP", "19.99"))
PEAD2_RECENT_DAYS_DEFAULT = int(os.getenv("PEAD2_RECENT_DAYS_DEFAULT", "30"))
PEAD2_RECENT_DAY_OPTIONS = tuple(
    int(x.strip())
    for x in os.getenv("PEAD2_RECENT_DAY_OPTIONS", "7,15,30,60").split(",")
    if x.strip().isdigit()
) or (7, 15, 30, 60)
PEAD2_RECENT_MAX_FETCH = int(os.getenv("PEAD2_RECENT_MAX_FETCH", "300"))
PEAD2_CALC_VERSION = 22

PEAD_FACTOR_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
PEAD_FACTOR_SUE_WEIGHT = float(os.getenv("PEAD_FACTOR_SUE_WEIGHT", "0.65"))
PEAD_FACTOR_PEG_GROWTH_FLOOR = float(os.getenv("PEAD_FACTOR_PEG_GROWTH_FLOOR", "5"))
PEAD_FACTOR_FRESH_DAYS = int(os.getenv("PEAD_FACTOR_FRESH_DAYS", "10"))
# PEG-aware PEAD strategy (separate tab — not PEAD 2 defaults).
PEAD_PEG_MAX = float(os.getenv("PEAD_PEG_MAX", "2.0"))
PEAD_PEG_REQUIRE_POSITIVE = os.getenv("PEAD_PEG_REQUIRE_POSITIVE", "true").lower() in (
    "1",
    "true",
    "yes",
)
PEAD_PEG_MAX_FORWARD_PE = float(os.getenv("PEAD_PEG_MAX_FORWARD_PE", "200"))

# Philip Fisher multibagger scorecard (separate strategy tab).
FISHER_MIN_SALES_YOY = float(os.getenv("FISHER_MIN_SALES_YOY", "10"))
FISHER_MIN_CF_PROFIT = float(os.getenv("FISHER_MIN_CF_PROFIT", "0.7"))
FISHER_MIN_CHECKS = int(os.getenv("FISHER_MIN_CHECKS", "7"))
FISHER_MCAP_MAX_CR = float(os.getenv("FISHER_MCAP_MAX_CR", "15000"))
FISHER_PE_MIN = float(os.getenv("FISHER_PE_MIN", "5"))
FISHER_PE_MAX = float(os.getenv("FISHER_PE_MAX", "60"))

# Distressed / surveillance turnaround (experimental monitoring).
DISTRESS_ASSUMED_DRAWDOWN_MIN = float(os.getenv("DISTRESS_ASSUMED_DRAWDOWN_MIN", "20"))
DISTRESS_MCAP_SWEET_MAX_CR = float(os.getenv("DISTRESS_MCAP_SWEET_MAX_CR", "500"))
DISTRESS_CACHE_HOURS = int(os.getenv("DISTRESS_CACHE_HOURS", "24"))

# LotusDew Napkin Investing: near-term (~30%) vs terminal (~70%) value split.
NAPKIN_NEAR_WEIGHT = float(os.getenv("NAPKIN_NEAR_WEIGHT", "0.30"))
NAPKIN_HORIZON_YEARS = int(os.getenv("NAPKIN_HORIZON_YEARS", "5"))
NAPKIN_ASSUMED_GROWTH_PCT = float(os.getenv("NAPKIN_ASSUMED_GROWTH_PCT", "15"))

# Growth strategy — quantitative screen (annual statements via yfinance).
GROWTH_MAX_DEBT_EQUITY = float(os.getenv("GROWTH_MAX_DEBT_EQUITY", "2"))
GROWTH_MIN_SALES_CAGR = float(os.getenv("GROWTH_MIN_SALES_CAGR", "15"))
GROWTH_MIN_PROFIT_CAGR = float(os.getenv("GROWTH_MIN_PROFIT_CAGR", "15"))
GROWTH_MIN_OPERATING_MARGIN = float(os.getenv("GROWTH_MIN_OPERATING_MARGIN", "15"))
GROWTH_MIN_ROE = float(os.getenv("GROWTH_MIN_ROE", "15"))
GROWTH_MIN_CHECKS = int(os.getenv("GROWTH_MIN_CHECKS", "4"))
GROWTH_CACHE_HOURS = int(os.getenv("GROWTH_CACHE_HOURS", "24"))
GROWTH_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS

# Cash Quality — CROIC / CCC / OCF vs EBITDA (annual yfinance statements).
CASH_QUALITY_MIN_CASH_TO_TAX = float(os.getenv("CASH_QUALITY_MIN_CASH_TO_TAX", "0.6"))
CASH_QUALITY_MIN_CROIC = float(os.getenv("CASH_QUALITY_MIN_CROIC", "0.2"))
CASH_QUALITY_MAX_CCC_YEARS = float(os.getenv("CASH_QUALITY_MAX_CCC_YEARS", "1"))
CASH_QUALITY_MIN_OCF_EBITDA_GROWTH = float(
    os.getenv("CASH_QUALITY_MIN_OCF_EBITDA_GROWTH", "0.6")
)
CASH_QUALITY_MIN_CHECKS = int(os.getenv("CASH_QUALITY_MIN_CHECKS", "3"))
CASH_QUALITY_LOOKBACK_YEARS = int(os.getenv("CASH_QUALITY_LOOKBACK_YEARS", "5"))
CASH_QUALITY_CACHE_HOURS = int(os.getenv("CASH_QUALITY_CACHE_HOURS", "24"))
CASH_QUALITY_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS

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
VALUATION_FORMULA_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
INTRINSIC_VALUE_MAX_WORKERS = YFINANCE_THROTTLED_MAX_WORKERS
INTRINSIC_VALUE_CACHE_HOURS = int(os.getenv("INTRINSIC_VALUE_CACHE_HOURS", "24"))
HEADWIND_SCAN_CACHE_HOURS = int(os.getenv("HEADWIND_SCAN_CACHE_HOURS", "24"))
# H&T board reads IV SQLite with a longer TTL so sector views aren't limited to today's fetches.
HEADWIND_IV_CACHE_HOURS = int(os.getenv("HEADWIND_IV_CACHE_HOURS", "168"))

GOOGLE_NEWS_CACHE_HOURS = int(os.getenv("GOOGLE_NEWS_CACHE_HOURS", "12"))
GOOGLE_NEWS_PER_TICKER = int(os.getenv("GOOGLE_NEWS_PER_TICKER", "5"))
GOOGLE_NEWS_MAX_FETCH = int(os.getenv("GOOGLE_NEWS_MAX_FETCH", "200"))
GOOGLE_NEWS_MAX_WORKERS = int(os.getenv("GOOGLE_NEWS_MAX_WORKERS", "8"))

MERGER_DEMERGER_LOOKBACK_YEARS = int(os.getenv("MERGER_DEMERGER_LOOKBACK_YEARS", "15"))
MERGER_DEMERGER_CACHE_HOURS = int(os.getenv("MERGER_DEMERGER_CACHE_HOURS", "24"))
MERGER_DEMERGER_ENRICH_CACHE_HOURS = int(os.getenv("MERGER_DEMERGER_ENRICH_CACHE_HOURS", "168"))
MERGER_DEMERGER_ENRICH_MAX_WORKERS = int(os.getenv("MERGER_DEMERGER_ENRICH_MAX_WORKERS", "4"))
NSE_RESULT_DATES_CACHE_HOURS = int(os.getenv("NSE_RESULT_DATES_CACHE_HOURS", "168"))

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


def get_hf_token() -> str | None:
    token = os.getenv("HF_TOKEN", "").strip()
    return token or None
