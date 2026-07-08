import pandas as pd

from stocks.core.text_utils import safe_str


def dedupe_recommendations(df: pd.DataFrame, *, top_n: int = 10) -> pd.DataFrame:
    """Dedupe by ticker, sort by score, optionally cap at top_n (0 = all rows)."""
    if df.empty or "ticker" not in df.columns:
        return df

    out = df.copy()
    out["ticker"] = out["ticker"].map(lambda t: safe_str(t).upper())
    out = out[out["ticker"] != ""]

    if "score" in out.columns:
        out["score"] = pd.to_numeric(out["score"], errors="coerce")
        out = out.sort_values("score", ascending=False, na_position="last")

    out = out.drop_duplicates(subset="ticker", keep="first")
    if top_n and top_n > 0:
        out = out.head(top_n)
    return out.reset_index(drop=True)


def analysis_universe(stocks: pd.DataFrame, *, limit: int = 80) -> pd.DataFrame:
    """One row per ticker for LLM input; prefer NSE over BSE on symbol clashes."""
    if stocks.empty or "ticker" not in stocks.columns:
        return stocks

    ordered = stocks.copy()
    ordered["ticker"] = ordered["ticker"].map(lambda t: safe_str(t).upper())
    if "market" in ordered.columns:
        ordered["_market_rank"] = ordered["market"].map(
            lambda m: 0 if safe_str(m).upper() == "NSE" else 1
        )
        ordered = ordered.sort_values("_market_rank")
        ordered = ordered.drop(columns=["_market_rank"])

    ordered = ordered.drop_duplicates(subset="ticker", keep="first")
    if limit and limit > 0:
        return ordered.head(limit)
    return ordered
