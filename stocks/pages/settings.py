import streamlit as st
from huggingface_hub import InferenceClient

from stocks.core.config import (
    DEFAULT_ANALYSIS_MODE,
    DEFAULT_SENTIMENT_MODEL,
    DEFAULT_TOP_N,
    DEFAULT_UNIVERSE_LIMIT,
    ERROR_LOG_FILE,
    FUNDAMENTALS_CACHE_HOURS,
    MARKET_CAP_CACHE_HOURS,
    MAX_TOP_N,
    METRICS_CACHE_HOURS,
    MODEL_RECOMMENDATIONS,
    RECOMMENDED_LOCAL_LLM_MODELS,
    RECOMMENDED_SENTIMENT_MODELS,
    RECOMMENDED_TS_MODELS,
    STOCKS_CACHE_HOURS,
    VERIFIED_CHAT_MODELS,
    load_models,
)
from stocks.core.database import db_stats, init_db
from stocks.shared.hf import get_client, is_valid_model_id
from stocks.core.log_service import (
    ANALYSIS_ERROR,
    DATASET_ERROR,
    METRICS_ERROR,
    PREDICTION_ERROR,
    PRICE_ERROR,
    SENTIMENT_ERROR,
    STOCK_NOT_FOUND,
    filter_errors,
    read_recent_errors,
)
from stocks.listings.stocks_data import load_india_stocks
from stocks.core.model_checker import check_models


def init_session_state(models: list[str]) -> None:
    if "model_choice" not in st.session_state:
        st.session_state.model_choice = models[0] if models else "Qwen/Qwen2.5-7B-Instruct"
    if "custom_model" not in st.session_state:
        st.session_state.custom_model = ""
    if "max_tokens" not in st.session_state:
        st.session_state.max_tokens = 2048
    if "top_n" not in st.session_state:
        st.session_state.top_n = DEFAULT_TOP_N
    if "temperature" not in st.session_state:
        st.session_state.temperature = 0.3
    if "sentiment_model" not in st.session_state:
        st.session_state.sentiment_model = DEFAULT_SENTIMENT_MODEL
    if "universe_limit" not in st.session_state:
        st.session_state.universe_limit = DEFAULT_UNIVERSE_LIMIT
    if "analysis_mode" not in st.session_state:
        st.session_state.analysis_mode = DEFAULT_ANALYSIS_MODE


def get_selected_model() -> str:
    custom = st.session_state.custom_model.strip()
    if custom and is_valid_model_id(custom):
        return custom
    return st.session_state.model_choice


def render_settings(client: InferenceClient | None, models: list[str]) -> None:
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.session_state.model_choice = st.selectbox(
            "Model",
            models,
            index=models.index(st.session_state.model_choice)
            if st.session_state.model_choice in models
            else 0,
        )

    with c2:
        st.session_state.custom_model = st.text_input(
            "Custom Model",
            value=st.session_state.custom_model,
            placeholder="org/model",
        )

    with c3:
        st.session_state.max_tokens = st.number_input(
            "Max Tokens",
            min_value=256,
            max_value=4096,
            value=st.session_state.max_tokens,
            step=256,
            help="Auto-increased at run time when Picks is high (e.g. 30–50).",
        )

    with c4:
        st.session_state.temperature = st.number_input(
            "Temperature",
            min_value=0.0,
            max_value=1.5,
            value=float(st.session_state.temperature),
            step=0.1,
            format="%.1f",
        )

    if not client:
        st.caption("Set `HF_TOKEN` in `.env` to connect to Hugging Face.")
    elif st.session_state.custom_model.strip() and not is_valid_model_id(
        st.session_state.custom_model.strip()
    ):
        st.caption("Custom model should use `org/model` format.")
    else:
        st.caption(f"Active model: `{get_selected_model()}`")

    with st.expander("Model compatibility (HF Inference API)", expanded=False):
        st.caption(
            "Only **chat** models deployed on Hugging Face Inference API are listed here for reference."
        )
        all_models = list(dict.fromkeys(load_models() + VERIFIED_CHAT_MODELS))
        if st.button("Test all models", type="secondary"):
            if not client:
                st.warning("Set `HF_TOKEN` in `.env` to test models.")
            else:
                with st.spinner("Probing chat_completion for each model..."):
                    statuses = check_models(client, all_models, force=True)
                rows = [
                    {
                        "Model": model,
                        "Status": "✅ OK" if info["ok"] else "❌ Fail",
                        "Details": info["message"],
                    }
                    for model, info in statuses.items()
                ]
                st.dataframe(rows, hide_index=True, width="stretch")

    with st.expander("Recommended models for Indian stocks", expanded=False):
        st.markdown("**LLM models** (HF Inference API)")
        llm_rows = [
            {"Model": model, "Recommendation": MODEL_RECOMMENDATIONS.get(model, "")}
            for model in models
        ]
        st.dataframe(llm_rows, hide_index=True, width="stretch")

        st.markdown("**Market analysis LLM** (local inference — not HF chat API)")
        st.dataframe(
            [{"Model": m["id"], "Notes": m["note"]} for m in RECOMMENDED_LOCAL_LLM_MODELS],
            hide_index=True,
            width="stretch",
        )

        st.markdown("**Price forecasting** (yfinance OHLCV — local / custom pipeline)")
        st.dataframe(
            [{"Model": m["id"], "Notes": m["note"]} for m in RECOMMENDED_TS_MODELS],
            hide_index=True,
            width="stretch",
        )

        st.markdown("**News sentiment** (HF text_classification on headlines)")
        st.dataframe(
            [{"Model": m["id"], "Notes": m["note"]} for m in RECOMMENDED_SENTIMENT_MODELS],
            hide_index=True,
            width="stretch",
        )

        st.caption("Model lists are for reference only — not investment advice.")

    with st.expander("Database & cache", expanded=False):
        init_db()
        stats = db_stats()
        st.markdown(
            f"- **Stocks:** {stats['stocks']:,} rows (refresh every {STOCKS_CACHE_HOURS}h)\n"
            f"- **Market cap:** {stats['market_cap']:,} tickers in SQLite "
            f"({MARKET_CAP_CACHE_HOURS}h TTL · from Earnings / scans)\n"
            f"- **Metrics:** {stats['metrics']:,} price rows ({METRICS_CACHE_HOURS}h TTL)\n"
            f"- **ROCE / EV cache:** {stats['fundamentals']:,} rows ({FUNDAMENTALS_CACHE_HOURS}h TTL)"
        )
        if st.button("Refresh stocks from Hugging Face"):
            with st.spinner("Downloading and saving to SQLite..."):
                df = load_india_stocks(force_refresh=True)
            st.success(f"Saved {len(df):,} stocks to the database.")

    with st.expander("Error logs", expanded=False):
        st.caption(f"Log file: `{ERROR_LOG_FILE}`")
        category = st.selectbox(
            "Filter by type",
            [
                "All",
                SENTIMENT_ERROR,
                PREDICTION_ERROR,
                STOCK_NOT_FOUND,
                PRICE_ERROR,
                METRICS_ERROR,
                ANALYSIS_ERROR,
                DATASET_ERROR,
            ],
        )
        errors = (
            read_recent_errors(50)
            if category == "All"
            else filter_errors(category, limit=50)
        )
        if errors:
            st.code("\n".join(errors), language="text")
        else:
            st.info("No errors logged yet.")
