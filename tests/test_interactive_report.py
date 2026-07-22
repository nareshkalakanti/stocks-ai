"""Interactive quant report expand payload."""

from __future__ import annotations

import json
import re

import pandas as pd

from stocks.dashboards.interactive_table import (
    _has_quarter_panel,
    prepare_interactive_report_df,
    rows_for_json,
)
from stocks.strategies.pead2.expand_data import apply_scan_price_to_payload
from stocks.strategies.ema_daily.html import build_ema_daily_html


def test_apply_scan_price_refreshes_stale_cached_snapshot():
    payload = {
        "snapshot": {
            "price": 44.15,
            "moving_averages": [
                {"period": 20, "value": 251.86, "above": False},
                {"period": 200, "value": 207.43, "above": False},
            ],
            "ema_averages": [
                {"period": 20, "value": 251.86, "above": False},
                {"period": 200, "value": 207.43, "above": False},
            ],
            "above_all_emas": False,
        },
        "pe_ratio": 3.1,
        "quarters": {"labels": ["Mar 2025"], "rows": []},
    }
    out = apply_scan_price_to_payload(payload, 282.45)
    snap = out["snapshot"]
    assert snap["price"] == 282.45
    assert snap["moving_averages"][0]["above"] is True
    assert snap["above_all_emas"] is True
    assert out["pe_ratio"] == round(3.1 * 44.15 / 282.45, 1)


def test_rows_for_json_backfills_snapshot_from_db(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "ticker": "CUPID",
                "name": "Cupid Ltd",
                "market": "NSE",
                "sector": "FMCG",
                "price": 206.9,
                "snapshot": {"price": 206.9},
            }
        ]
    )

    monkeypatch.setattr(
        "stocks.core.database.load_market_cap_from_db",
        lambda tickers: pd.DataFrame([{"ticker": "CUPID", "market_cap_cr": 27821.0}]),
    )
    monkeypatch.setattr(
        "stocks.core.database.load_metrics_from_db",
        lambda tickers: pd.DataFrame(
            [{"ticker": "CUPID", "pe": 258.6, "52w_low": 29.12, "52w_high": 226.0}]
        ),
    )

    rows = rows_for_json(df)
    snap = rows[0]["snapshot"]
    assert snap["market_cap_cr"] == 27821.0
    assert snap["pe_ratio"] == 258.6


def test_prepare_interactive_report_df_attaches_quarters(monkeypatch):
    df = pd.DataFrame(
        [
            {
                "ticker": "CUPID",
                "name": "Cupid Ltd",
                "market": "NSE",
                "sector": "FMCG",
                "price": 206.9,
            }
        ]
    )
    payload = {
        "quarters": {
            "labels": ["Mar 2025", "Jun 2025"],
            "rows": [{"label": "Sales", "values": [1, 2], "decimals": 0, "pct": False}],
        },
        "snapshot": {"price": 206.9, "market_cap_cr": 27821.0},
    }

    def _fake_attach_pead_expand(frame, *, max_workers=None):
        del max_workers
        out = frame.copy()
        out["quarters"] = [payload["quarters"]]
        out["snapshot"] = [payload["snapshot"]]
        return out

    monkeypatch.setattr(
        "stocks.strategies.pead2.expand_data.attach_pead_expand",
        _fake_attach_pead_expand,
    )

    out = prepare_interactive_report_df(df, max_workers=1)
    assert _has_quarter_panel(out.iloc[0]["quarters"])
    rows = rows_for_json(out)
    assert rows[0]["quarters"]["labels"] == ["Mar 2025", "Jun 2025"]
    assert rows[0]["snapshot"]["market_cap_cr"] == 27821.0

    html = build_ema_daily_html(out, standalone=False)
    match = re.search(r"const DATA = (\[.*?\]);", html, re.S)
    assert match
    data = json.loads(match.group(1))
    assert data[0]["quarters"]["labels"]
