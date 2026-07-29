#!/usr/bin/env python3
"""Write NSE governance-map gap report (mcap / website / about)."""

from __future__ import annotations

import argparse
from pathlib import Path

from stocks.governance.profile_gaps import gap_summary, write_governance_gaps_csv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data/logs/governance_map_profile_gaps_nse.csv"),
    )
    parser.add_argument("--min-boards", type=int, default=2)
    parser.add_argument(
        "--all-markets",
        action="store_true",
        help="Include BSE etc. (default: NSE + NSE SME only)",
    )
    args = parser.parse_args()
    path = write_governance_gaps_csv(
        args.output,
        min_boards=args.min_boards,
        nse_only=not args.all_markets,
    )
    from stocks.governance.profile_gaps import audit_map_profile_gaps

    stats = gap_summary(
        audit_map_profile_gaps(min_boards=args.min_boards, nse_only=not args.all_markets)
    )
    print(f"Wrote {path}")
    print(
        f"tickers={stats['tickers']} "
        f"missing_mcap={stats['missing_mcap']} "
        f"missing_website={stats['missing_website']} "
        f"missing_about={stats['missing_about']}"
    )


if __name__ == "__main__":
    main()
