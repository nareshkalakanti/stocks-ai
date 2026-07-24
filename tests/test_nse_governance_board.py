"""NSE governance DIN board fetch / iXBRL parse."""

from __future__ import annotations

from stocks.market.nse_governance_board import (
    fetch_board_from_nse_governance,
    parse_governance_ixbrl_html,
)


_SAMPLE_IXBRL = """
<html><body>
<table>
<tr>
  <th>Sr</th><th>Title (Mr / Ms)</th><th>Name of the Director</th><th>PAN</th><th>DIN</th>
  <th>Category 1 of directors</th><th>Category 2 of directors</th>
  <th>Category 3 of directors</th><th>Current status</th>
</tr>
<tr>
  <td>1</td><td>Mr.</td><td>Mukesh Dhirubhai Ambani</td><td></td><td>00001695</td>
  <td>Executive Director</td><td>Chairperson related to Promoter</td><td>MD</td><td>Active</td>
</tr>
<tr>
  <td>2</td><td>Mrs.</td><td>Dummy No Din</td><td></td><td>99999999</td>
  <td>Non-Executive - Independent Director</td><td>Not Applicable</td><td></td><td>Active</td>
</tr>
<tr>
  <td>3</td><td>Mr.</td><td>Shumeet Banerji</td><td></td><td>02787784</td>
  <td>Non-Executive - Independent Director</td><td>Not Applicable</td><td></td><td>Active</td>
</tr>
</table>
</body></html>
"""


def test_parse_governance_ixbrl_html_extracts_din_seats():
    seats = parse_governance_ixbrl_html(_SAMPLE_IXBRL, as_of="2026-03-31")
    dins = {s["din"] for s in seats}
    assert "00001695" in dins
    assert "02787784" in dins
    assert "99999999" not in dins  # dummy DIN dropped
    mukesh = next(s for s in seats if s["din"] == "00001695")
    assert mukesh["name"] == "Mukesh Dhirubhai Ambani"
    assert mukesh["as_of"] == "2026-03-31"
    assert mukesh["source"] == "nse_integrated_governance"
    assert "Executive" in mukesh["designation"] or mukesh["category"] == "Executive"


def test_fetch_board_from_nse_governance_live_tcs():
    board = fetch_board_from_nse_governance("TCS")
    assert board is not None
    assert board["ticker"] == "TCS"
    seats = board["seats"]
    assert len(seats) >= 3
    assert all(len(s["din"]) == 8 for s in seats)
    assert all(s["din"] != "99999999" for s in seats)
    assert any(s["name"] for s in seats)


def test_fetch_board_from_nse_governance_live_sme_aaron():
    """SME DIN filings use ``index=sme`` (equities returns empty)."""
    board = fetch_board_from_nse_governance("AARON", market="NSE SME")
    assert board is not None
    assert board["ticker"] == "AARON"
    assert board["market"] == "NSE SME"
    seats = board["seats"]
    assert len(seats) >= 3
    assert all(len(s["din"]) == 8 for s in seats)
    assert all(s["din"] != "99999999" for s in seats)
