"""LotusDew Napkin Investing strategy."""

from stocks.strategies.napkin.napkin_framework import (
    NapkinParams,
    required_cagr,
    run_napkin_pipeline,
)
from stocks.strategies.napkin.service import prepare_pead_universe, run_napkin_scan
from stocks.strategies.napkin.strategy import (
    format_napkin_export_df,
    napkin_caption,
    score_napkin,
)

__all__ = [
    "NapkinParams",
    "format_napkin_export_df",
    "napkin_caption",
    "prepare_pead_universe",
    "required_cagr",
    "run_napkin_pipeline",
    "run_napkin_scan",
    "score_napkin",
]
