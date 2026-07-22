"""NSE governance — curated board / director graph (separate SQLite)."""

from stocks.governance.service import (
    companies_with_boards,
    directors_for_ticker,
    governance_stats,
    init_governance_db,
    multi_board_directors,
    overlaps_for_ticker,
    save_company_board,
    seats_for_din,
    seats_for_person,
    seed_curated_boards,
)

__all__ = [
    "companies_with_boards",
    "directors_for_ticker",
    "governance_stats",
    "init_governance_db",
    "multi_board_directors",
    "overlaps_for_ticker",
    "save_company_board",
    "seats_for_din",
    "seats_for_person",
    "seed_curated_boards",
]
