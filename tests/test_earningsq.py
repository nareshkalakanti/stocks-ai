"""EarningsQ score + fixture reverse-engineering tests."""

from __future__ import annotations

import json

from stocks.strategies.earningsq.scores import (
    compute_return_score,
    compute_surprise_score,
    market_hours_bucket,
)
from stocks.strategies.earningsq.service import FIXTURES_PATH, enrich_earningsq_row
import pandas as pd


def test_market_hours_bucket():
    assert market_hours_bucket(pd.Timestamp("2026-07-29 08:00:00")) == "BEFORE"
    assert market_hours_bucket(pd.Timestamp("2026-07-29 10:00:00")) == "DURING"
    assert market_hours_bucket(pd.Timestamp("2026-07-29 20:18:00")) == "AFTER"


def test_fixture_chemfab_scores_in_ballpark():
    rows = json.loads(FIXTURES_PATH.read_text())
    chem = next(r for r in rows if r["ticker"] == "CHEMFAB")
    surprise = compute_surprise_score(
        sales_yoy=chem["rev_yoy"],
        sales_qoq=chem["rev_qoq"],
        np_yoy=chem["np_yoy"],
        np_qoq=chem["np_qoq"],
        eps_yoy=chem["eps_yoy"],
        eps_qoq=chem["eps_qoq"],
        opm_yoy_pp=chem.get("opm_yoy_pp"),
        opm_qoq_pp=chem.get("opm_qoq_pp"),
    )
    ret = compute_return_score(
        ret_1d=chem.get("ret_1d"),
        ret_1w=chem.get("ret_1w"),
        ret_qtd=chem.get("ret_qtd"),
    )
    # Reverse-engineered ballpark vs screenshot (not exact clone).
    assert surprise is not None and surprise > 0
    assert abs(surprise - float(chem["expected_surprise_score"])) < 2.5
    assert ret is not None and ret > 0
    assert abs(ret - float(chem["expected_return_score"])) < 12.0


def test_enrich_fixture_row_without_yahoo():
    rows = json.loads(FIXTURES_PATH.read_text())
    out = enrich_earningsq_row(rows[0], pead_blob=None, with_returns=False)
    assert out["ticker"] == "CHEMFAB"
    assert out["market_hours"] == "AFTER"
    assert out["surprise_score"] is not None
    assert out["filing_type"] in {"Consolidated", "Standalone", "—"}
