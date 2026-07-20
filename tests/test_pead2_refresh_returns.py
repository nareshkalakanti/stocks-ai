from unittest.mock import patch

import pandas as pd

from stocks.strategies.pead2.service import _refresh_returns_blob


def test_refresh_returns_blob_updates_lag0():
    blob = {
        "ticker": "TEST",
        "market": "NSE",
        "calc_version": 3,
        "lags": {
            "0": {
                "result_date": "2026-07-01",
                "returns_pct": 0.0,
                "daily_ret_pct": 19.9,
                "price": 100.0,
            }
        },
    }
    hist = pd.DataFrame(
        {"Close": [100.0, 110.0, 125.0]},
        index=pd.to_datetime(["2026-06-28", "2026-07-02", "2026-07-10"]),
    )

    class _FakeTicker:
        def history(self, *args, **kwargs):
            return hist

        @property
        def info(self):
            return {"regularMarketPrice": 125.0}

    with patch("stocks.strategies.pead2.service.yf.Ticker", return_value=_FakeTicker()):
        with patch("stocks.strategies.pead2.service.PEAD2_CALC_VERSION", 3):
            out = _refresh_returns_blob("TEST", "NSE", blob)

    assert out is not None
    lag0 = out["lags"]["0"]
    assert lag0["returns_pct"] == 13.64
    assert lag0["price"] == 125.0
    assert lag0["daily_ret_pct"] is not None
