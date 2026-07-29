#!/usr/bin/env python3
"""Fetch NSE DIN boards for tickers in a governance pending CSV and save to governance.db."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from stocks.core.text_utils import safe_str
from stocks.governance.scan import pending_governance_jobs, run_governance_scan
from stocks.governance.service import (
    clear_scan_log_for_tickers,
    governance_stats,
)


def _load_universe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    need = {"ticker", "name", "market"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"CSV missing columns: {sorted(missing)}")
    df = df.copy()
    df["ticker"] = df["ticker"].map(lambda x: safe_str(x).upper())
    df["name"] = df["name"].map(lambda x: safe_str(x) or "")
    df["market"] = df["market"].map(lambda x: safe_str(x).upper() or "NSE")
    df = df[df["ticker"] != ""].drop_duplicates(subset=["ticker"])
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv",
        type=Path,
        help="CSV with columns ticker, name, market (e.g. governance_pending.csv)",
    )
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--max-batches",
        type=int,
        default=0,
        help="Stop after N batches (0 = run until no pending jobs)",
    )
    parser.add_argument(
        "--retry-empty",
        action="store_true",
        help="Clear empty/failed scan_log rows for CSV tickers before scanning",
    )
    parser.add_argument(
        "-o",
        "--still-pending",
        type=Path,
        default=None,
        help="Write tickers still pending after run to this CSV",
    )
    args = parser.parse_args()

    if not args.csv.is_file():
        raise SystemExit(f"Not found: {args.csv}")

    universe = _load_universe(args.csv)
    tickers = universe["ticker"].tolist()
    print(f"Universe: {len(tickers):,} tickers from {args.csv}")

    if args.retry_empty:
        n = clear_scan_log_for_tickers(tickers, only_empty_failed=True)
        print(f"Cleared {n:,} empty/failed scan_log rows for CSV tickers")

    pending0 = pending_governance_jobs(universe, skip_scanned=True)
    print(f"Pending before scan: {len(pending0):,}")

    totals = {
        "saved": 0,
        "skipped_empty": 0,
        "skipped_protected": 0,
        "failed": 0,
        "batches": 0,
    }
    batch_num = 0

    while True:
        pending = pending_governance_jobs(universe, skip_scanned=True)
        if not pending:
            print("No pending jobs left.")
            break
        if args.max_batches and batch_num >= args.max_batches:
            print(f"Stopped at --max-batches={args.max_batches}")
            break

        def _progress(done: int, total: int, ticker: str) -> None:
            print(f"  [{done}/{total}] {ticker}", flush=True)

        result = run_governance_scan(
            universe,
            batch_size=args.batch_size,
            max_workers=args.workers,
            skip_scanned=True,
            progress_callback=_progress,
        )
        batch_num += 1
        scanned = int(result.get("scanned") or 0)
        if scanned == 0:
            print("Batch returned 0 scans; stopping.")
            break

        totals["saved"] += int(result.get("saved") or 0)
        totals["skipped_empty"] += int(result.get("skipped_empty") or 0)
        totals["skipped_protected"] += int(result.get("skipped_protected") or 0)
        totals["failed"] += int(result.get("failed") or 0)
        totals["batches"] += 1

        still = len(pending_governance_jobs(universe, skip_scanned=True))
        din = governance_stats().get("directors_with_din", 0)
        print(
            f"Batch {totals['batches']}: scanned={scanned} "
            f"saved={result.get('saved')} empty={result.get('skipped_empty')} "
            f"failed={result.get('failed')} · pending={still:,} · DIN directors={din:,}",
            flush=True,
        )

    pending_end = pending_governance_jobs(universe, skip_scanned=True)
    stats = governance_stats()
    print(
        f"\nDone — batches={totals['batches']} "
        f"saved={totals['saved']:,} empty={totals['skipped_empty']:,} "
        f"protected={totals['skipped_protected']:,} failed={totals['failed']:,}"
    )
    print(
        f"Still pending in CSV universe: {len(pending_end):,} · "
        f"companies_with_board={stats.get('companies', 0):,} · "
        f"directors_with_din={stats.get('directors_with_din', 0):,}"
    )

    out = args.still_pending
    if out is None and pending_end:
        out = Path("data/logs/governance_pending_after_scan.csv")
    if out and pending_end:
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [{"ticker": t, "name": n, "market": m} for t, n, m in pending_end]
        ).to_csv(out, index=False)
        print(f"Wrote still-pending list: {out}")

    if pending_end:
        sys.exit(1)


if __name__ == "__main__":
    main()
