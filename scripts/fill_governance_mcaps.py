#!/usr/bin/env python3
"""Fill missing Governance Map market caps into stocks_ai.db (screener → Yahoo).

Usage (from repo root):
  python scripts/fill_governance_mcaps.py
  python scripts/fill_governance_mcaps.py --ticker MIRCELECTR --mcap-cr 123.4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python scripts/…` from repo root without installing the package.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stocks.core.config import GOVERNANCE_MAP_MCAP_FILL_BATCH
from stocks.core.database import save_market_cap_to_db
from stocks.governance.map_data import (
    hydrate_all_missing_mcaps,
    map_company_ticker_markets,
    missing_mcap_tickers,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-boards", type=int, default=2)
    parser.add_argument(
        "--batch",
        type=int,
        default=GOVERNANCE_MAP_MCAP_FILL_BATCH,
        help="Names per screener batch (default: env GOVERNANCE_MAP_MCAP_FILL_BATCH)",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        dest="tickers",
        metavar="SYM",
        help="Manual mcap: SYM with --mcap-cr (repeatable)",
    )
    parser.add_argument(
        "--mcap-cr",
        type=float,
        help="Market cap in ₹ Cr for --ticker (required with --ticker)",
    )
    parser.add_argument(
        "--market",
        default="NSE",
        help="Market for manual --ticker (default: NSE)",
    )
    args = parser.parse_args()

    if args.tickers:
        if args.mcap_cr is None or args.mcap_cr <= 0:
            parser.error("--mcap-cr is required and must be > 0 with --ticker")
        for sym in args.tickers:
            save_market_cap_to_db(sym.upper(), float(args.mcap_cr), market=args.market)
            print(f"Saved {sym.upper()} mcap={args.mcap_cr} Cr")
        return

    tm = map_company_ticker_markets(min_boards=args.min_boards)
    before = missing_mcap_tickers(tm)
    if not before:
        print("No missing market caps on the governance map.")
        return

    print(f"Missing {len(before)} tickers — fetching (batch={args.batch})…")

    def _progress(filled: int, still: int) -> None:
        print(f"  filled={filled} still_missing={still}", flush=True)

    n = hydrate_all_missing_mcaps(
        tm,
        batch_size=max(1, args.batch),
        workers=1,
        progress_callback=_progress,
    )
    still = missing_mcap_tickers(tm)
    print(f"Done: filled={n} still_missing={len(still)}")
    if still:
        print("Still missing:", ", ".join(still[:20]), end="")
        if len(still) > 20:
            print(f" … +{len(still) - 20} more")
        else:
            print()
        print("Tip: python scripts/fill_governance_mcaps.py --ticker SYM --mcap-cr 123.4")


if __name__ == "__main__":
    main()
