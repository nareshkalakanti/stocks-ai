"""Market-cap tier defaults — All caps, no hidden floor."""

from __future__ import annotations

import pandas as pd

from stocks.core.config import DEFAULT_CAP_TIER
from stocks.scans.scan_universe import cap_tier_min_mcap_cr, resolve_cap_tier_id
from stocks.scans.holdings_playlist import HOLDINGS_PLAYLIST_LABEL
from stocks.scans.ds_playlist import DS_PLAYLIST_LABEL
from stocks.strategies.tq_bb.service import prepare_strategy_universe


def test_default_cap_tier_is_all():
    assert DEFAULT_CAP_TIER == "all"


def test_holdings_respects_cap_tier_ds_uses_all_caps():
    assert resolve_cap_tier_id(HOLDINGS_PLAYLIST_LABEL, "micro") == "micro"
    assert resolve_cap_tier_id(DS_PLAYLIST_LABEL, "range_100_3000") == "all"
    assert cap_tier_min_mcap_cr("all") is None


def test_prepare_strategy_universe_all_caps_keeps_small_names():
    stocks = pd.DataFrame(
        {
            "ticker": ["SMALL", "BIG"],
            "market": ["NSE", "NSE"],
            "name": ["Small Co", "Big Co"],
        }
    )
    universe, cap_excluded, mcap_excluded = prepare_strategy_universe(stocks, cap_tier_id="all")
    assert len(universe) == 2
    assert cap_excluded == 0
    assert mcap_excluded == 0
