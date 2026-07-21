"""Distressed / surveillance turnaround scoring."""

from __future__ import annotations

import pandas as pd

from stocks.market.nse_surveillance import load_distress_seed_tickers
from stocks.strategies.distress.strategy import score_distress_turnaround


def test_distress_seed_tickers_loaded():
    seeds = load_distress_seed_tickers()
    for t in (
        "GPTINFRA",
        "HMT",
        "LOKESHMACH",
        "ATAM",
        "MIRCELECTR",
        "TEAMGTY",
        "DGCONTENT",
        "BPL",
    ):
        assert t in seeds


def test_score_keeps_seed_and_ranks_recovery_tape():
    df = pd.DataFrame(
        [
            {
                "ticker": "ATAM",
                "surv_type": "SEED",
                "surv_stage": "monitor",
                "forward_pe": 22.3,
                "eps_yoy": -60.0,
                "sales_yoy": -10.0,
                "returns_pct": -10.0,
                "price": 67.0,
                "snapshot": {"w52_high": 111.0, "w52_low": 48.0, "price": 67.0},
                "market_cap_cr": 77.0,
            },
            {
                "ticker": "LOKESHMACH",
                "surv_type": "SEED",
                "surv_stage": "monitor",
                "forward_pe": 266.0,
                "eps_yoy": -114.0,
                "sales_yoy": -2.0,
                "returns_pct": 84.0,
                "price": 330.0,
                "snapshot": {"w52_high": 344.0, "w52_low": 139.0, "price": 330.0},
                "market_cap_cr": 719.0,
            },
            {
                "ticker": "DEADCO",
                "surv_type": "GSM",
                "surv_stage": "IV",
                "forward_pe": 5.0,
                "eps_yoy": 5.0,
                "sales_yoy": 5.0,
                "returns_pct": -40.0,
                "price": 10.0,
                "snapshot": {"w52_high": 12.0, "w52_low": 9.0, "price": 10.0},
                "market_cap_cr": 50.0,
            },
        ]
    )
    scored = score_distress_turnaround(df)
    assert "ATAM" in set(scored["ticker"])
    assert "LOKESHMACH" in set(scored["ticker"])
    # Strong bounce + positive returns should outrank mild seed monitor.
    assert scored.iloc[0]["ticker"] == "LOKESHMACH"
    assert scored.iloc[0]["pead_score"] > scored[scored["ticker"] == "ATAM"].iloc[0]["pead_score"]
