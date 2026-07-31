"""Cap band color palette — NC MIC SC MC LC."""

from stocks.shared.cap_colors import CAP_CODES, CAP_PALETTE, cap_css_class


def test_cap_codes_order():
    assert CAP_CODES == ("NC", "MIC", "SC", "MC", "LC")


def test_each_code_has_distinct_palette():
    bgs = {CAP_PALETTE[c]["bg"] for c in CAP_CODES}
    fgs = {CAP_PALETTE[c]["fg"] for c in CAP_CODES}
    assert len(bgs) == len(CAP_CODES)
    assert len(fgs) == len(CAP_CODES)


def test_cap_css_class():
    assert cap_css_class("mc") == "cap-mc"
    assert cap_css_class("") == ""
