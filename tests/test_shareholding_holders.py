"""Named public >1% holders from SHP XBRL."""

from __future__ import annotations

from stocks.market.shareholding import parse_xbrl_public_gt1_holders


_SAMPLE = """
<?xml version="1.0"?>
<xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:in-bse-shp="http://www.bseindia.com/xbrl/XBRLSchema_SHP">
  <xbrli:context id="D_IndividualsOrHUF_Context15">
    <xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/isin">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="in-bse-shp:DetailsSharesHeldByIndividualsOrHUFAxis">in-bse-shp:IndividualsOrHUFDomain</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>
  <xbrli:context id="IndividualsOrHUF_Context15">
    <xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/isin">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="in-bse-shp:DetailsSharesHeldByIndividualsOrHUFAxis">in-bse-shp:IndividualsOrHUFDomain</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>
  <xbrli:context id="D_MutualFundsOrUTI_Context15">
    <xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/isin">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis">in-bse-shp:MutualFundsOrUTIDomain</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>
  <xbrli:context id="MutualFundsOrUTI_Context15">
    <xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/isin">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis">in-bse-shp:MutualFundsOrUTIDomain</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>
  <xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">
    <xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/isin">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis">in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>
  <xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">
    <xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/isin">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis">in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>
  <xbrli:context id="D_OthersIndianShareholders_Context15">
    <xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/isin">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="in-bse-shp:DetailsOfSharesHeldByOthersIndianShareholdersAxis">in-bse-shp:OthersIndianShareholdersDomain</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>
  <xbrli:context id="OthersIndianShareholders_Context15">
    <xbrli:entity><xbrli:identifier scheme="http://www.nseindia.com/isin">INE123</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
    <xbrli:scenario>
      <xbrldi:explicitMember dimension="in-bse-shp:DetailsOfSharesHeldByOthersIndianShareholdersAxis">in-bse-shp:OthersIndianShareholdersDomain</xbrldi:explicitMember>
    </xbrli:scenario>
  </xbrli:context>

  <in-bse-shp:NameOfTheShareholder contextRef="D_IndividualsOrHUF_Context15">PROMOTER PERSON</in-bse-shp:NameOfTheShareholder>
  <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="IndividualsOrHUF_Context15">0.20</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>

  <in-bse-shp:NameOfTheShareholder contextRef="D_OthersIndianShareholders_Context15">Promoter Body Pvt Ltd</in-bse-shp:NameOfTheShareholder>
  <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="OthersIndianShareholders_Context15">0.174</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>

  <in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context15">Quant Mutual Fund - Quant Small Cap Fund</in-bse-shp:NameOfTheShareholder>
  <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context15">0.02</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>

  <in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">Sachin Bansal</in-bse-shp:NameOfTheShareholder>
  <in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">0.014</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
</xbrl>
"""


def test_parse_xbrl_public_gt1_holders_keeps_public_skips_promoter():
    holders = parse_xbrl_public_gt1_holders(_SAMPLE)
    names = [h["name"] for h in holders]
    assert names == ["Sachin Bansal"]
    assert "Quant Mutual Fund - Quant Small Cap Fund" not in names
    assert "PROMOTER PERSON" not in names
    assert "Promoter Body Pvt Ltd" not in names
    assert holders[0]["pct"] == 1.4
    assert holders[0]["category"] == "Individual"


def test_individual_holders_index_includes_multi_company_people():
    from stocks.core.database import init_db, save_shareholding_holders
    from stocks.market.shareholding import individual_holders_index

    init_db()
    save_shareholding_holders(
        "PPAP",
        "2026-06-30",
        [{"name": "Manohar Devabhaktuni", "pct": 2.5, "category": "NRI"}],
    )
    save_shareholding_holders(
        "TNPL",
        "2026-06-30",
        [{"name": "MANOHAR DEVABHAKTUNI", "pct": 1.5, "category": "NRI"}],
    )
    idx = individual_holders_index(min_companies=2)
    hit = next((p for p in idx if "devabhaktuni" in p["name_key"]), None)
    assert hit is not None
    assert hit["company_count"] >= 2
    tickers = {h["ticker"] for h in hit["holdings"]}
    assert "PPAP" in tickers and "TNPL" in tickers
