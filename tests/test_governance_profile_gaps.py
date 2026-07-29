"""Tests for governance map profile gap audit."""

from stocks.governance.profile_gaps import audit_map_profile_gaps, gap_summary


def test_gap_summary_empty():
    assert gap_summary(audit_map_profile_gaps(min_boards=99))["tickers"] == 0
