"""NSE governance — DIN board / director graph (separate SQLite)."""

from stocks.governance.map_data import build_governance_map_rows
from stocks.governance.scan import fetch_board_for_ticker, run_governance_scan
from stocks.governance.score import score_director_seats
from stocks.governance.service import (
    companies_with_boards,
    directors_for_ticker,
    enrich_governance_company_classification,
    governance_stats,
    init_governance_db,
    multi_board_directors,
    overlaps_for_ticker,
    save_company_board,
    seats_for_din,
    seats_for_person,
    seed_curated_boards,
)
from stocks.market.nse_governance_board import fetch_board_from_nse_governance

__all__ = [
    "build_governance_map_rows",
    "companies_with_boards",
    "directors_for_ticker",
    "enrich_governance_company_classification",
    "fetch_board_for_ticker",
    "fetch_board_from_nse_governance",
    "governance_stats",
    "init_governance_db",
    "multi_board_directors",
    "overlaps_for_ticker",
    "run_governance_scan",
    "save_company_board",
    "score_director_seats",
    "seats_for_din",
    "seats_for_person",
    "seed_curated_boards",
]
