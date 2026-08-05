#!/usr/bin/env python3
"""Refresh governance.db: resolve CINs, optionally pull MCA boards via Apify.

Examples::

  # Resolve BSE→CIN for tickers still missing boards
  python scripts/refresh_governance.py --cins

  # Pull MCA directors for companies that already have CIN but no DIN board
  python scripts/refresh_governance.py --apify

  # Checkpoint + VACUUM governance.db before committing it
  python scripts/refresh_governance.py --update-seed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stocks.governance.refresh import (
    companies_with_cin_missing_din_board,
    refresh_boards_from_apify,
    refresh_missing_cins,
    update_governance_seed,
)
from stocks.governance.service import governance_stats, init_governance_db, missing_boards


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cins",
        action="store_true",
        help="Resolve missing CINs via Screener BSE code + BSE CorpInfo",
    )
    parser.add_argument(
        "--apify",
        action="store_true",
        help="Fetch MCA boards via Apify for companies with CIN but no DIN board",
    )
    parser.add_argument(
        "--max-apify",
        type=int,
        default=0,
        help="Cap Apify companies (0 = all with CIN missing board)",
    )
    parser.add_argument(
        "--update-seed",
        action="store_true",
        help="Checkpoint + VACUUM data/governance.db (ready to commit)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print coverage only (default if no other flags)",
    )
    args = parser.parse_args()

    if not (args.cins or args.apify or args.update_seed):
        args.status = True

    init_governance_db()
    if args.status:
        stats = governance_stats()
        miss = missing_boards()
        need = companies_with_cin_missing_din_board()
        print("=== governance.db ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        print(f"  missing_boards: {len(miss)}")
        print(f"  cin_but_no_din_board: {len(need)}")
        if not miss.empty:
            print(miss.groupby("market").size().to_string())

    if args.cins:
        print("Resolving CINs…")
        result = refresh_missing_cins()
        print("CIN refresh:", result)

    if args.apify:
        print("Fetching MCA boards via Apify…")
        cap = args.max_apify or None
        try:
            result = refresh_boards_from_apify(max_companies=cap)
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(1) from exc
        print("Apify refresh:", result)

    if args.update_seed:
        path = update_governance_seed()
        print(f"governance.db ready to commit: {path}")

    if args.cins or args.apify or args.update_seed:
        stats = governance_stats()
        miss = missing_boards()
        print("=== after ===")
        print(f"  companies: {stats['companies']}")
        print(f"  seats: {stats['seats']}")
        print(f"  multi_board_directors: {stats['multi_board_directors']}")
        print(f"  missing_boards: {len(miss)}")


if __name__ == "__main__":
    main()
