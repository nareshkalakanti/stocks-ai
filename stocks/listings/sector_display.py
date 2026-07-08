"""Map coarse / HF sector labels to Indian market-friendly display names."""

from __future__ import annotations

import pandas as pd

from stocks.core.text_utils import safe_str

# Groww / FinanciallyFree-style sector names (aligned with common Indian screener UX).
AUTOMOBILE = "Automobile & Ancillaries"
BANKING = "Banking & Finance"
IT = "IT & Technology"
PHARMA = "Pharmaceuticals & Healthcare"
FMCG = "FMCG & Consumer Goods"
CONSUMER_DURABLES = "Consumer Durables"
RETAIL = "Retail"
REAL_ESTATE = "Real Estate & Construction"
METALS = "Metals & Mining"
OIL_GAS = "Oil & Gas & Energy"
POWER = "Power & Utilities"
CHEMICALS = "Chemicals & Petrochemicals"
TEXTILES = "Textiles & Apparel"
MEDIA = "Media & Entertainment"
TRANSPORT = "Transportation & Logistics"
HOTELS = "Hotels, Tourism & Leisure"
TELECOM = "Telecom"
AGRI = "Agriculture & Agro"
CAPITAL_GOODS = "Engineering & Capital Goods"
SERVICES = "Commercial & Business Services"
DIVERSIFIED = "Diversified & Others"

# When industry was copied from a prior display-sector pass, keep stable labels.
_DISPLAY_IDENTITY = {
    AUTOMOBILE: AUTOMOBILE,
    BANKING: BANKING,
    IT: IT,
    PHARMA: PHARMA,
    FMCG: FMCG,
    CONSUMER_DURABLES: CONSUMER_DURABLES,
    RETAIL: RETAIL,
    REAL_ESTATE: REAL_ESTATE,
    METALS: METALS,
    OIL_GAS: OIL_GAS,
    POWER: POWER,
    CHEMICALS: CHEMICALS,
    TEXTILES: TEXTILES,
    MEDIA: MEDIA,
    TRANSPORT: TRANSPORT,
    HOTELS: HOTELS,
    TELECOM: TELECOM,
    AGRI: AGRI,
    CAPITAL_GOODS: CAPITAL_GOODS,
    SERVICES: SERVICES,
    DIVERSIFIED: DIVERSIFIED,
}

# Industry / sub-sector (from NSE.csv taxonomy) -> display sector.
_INDUSTRY_DISPLAY: dict[str, str] = {
    **_DISPLAY_IDENTITY,
    # Automobile & Ancillaries
    "Auto Parts": AUTOMOBILE,
    "Batteries": AUTOMOBILE,
    "Two Wheelers": AUTOMOBILE,
    "Three Wheelers": AUTOMOBILE,
    "Four Wheelers": AUTOMOBILE,
    "Trucks & Buses": AUTOMOBILE,
    "Tractors": AUTOMOBILE,
    "Tyres & Tubes": AUTOMOBILE,
    "Tires & Rubber": AUTOMOBILE,
    "Cycles": AUTOMOBILE,
    # Banking & Finance
    "Asset Management": BANKING,
    "Capital Markets": BANKING,
    "Consumer Finance": BANKING,
    "Credit Services": BANKING,
    "Diversified Financials": BANKING,
    "Finance": BANKING,
    "Financial Services": BANKING,
    "Home Financing": BANKING,
    "Insurance": BANKING,
    "Investment Banking & Brokerage": BANKING,
    "Payment Infrastructure": BANKING,
    "Private Banks": BANKING,
    "Public Banks": BANKING,
    "Specialized Finance": BANKING,
    "Stock Exchanges & Ratings": BANKING,
    # IT & Technology
    "IT Services & Consulting": IT,
    "Software - Application": IT,
    "Software Services": IT,
    "Technology Hardware": IT,
    "Communication & Networking": IT,
    "Communication Equipment": IT,
    "Electronic Equipments": IT,
    "Electronic technology": IT,
    "Technology services": IT,
    "Online Services": IT,
    "Animation": IT,
    # Pharma & Healthcare
    "Pharmaceuticals": PHARMA,
    "Drug Manufacturers - Specialty & Generic": PHARMA,
    "Biotechnology": PHARMA,
    "Labs & Life Sciences Services": PHARMA,
    "Pharmaceutical Retailers": PHARMA,
    "Hospitals & Diagnostic Centres": PHARMA,
    "Health Care Equipment & Supplies": PHARMA,
    "Health services": PHARMA,
    "Health technology": PHARMA,
    "Wellness Services": PHARMA,
    "Healthcare": PHARMA,
    # FMCG
    "FMCG - Foods": FMCG,
    "FMCG - Household Products": FMCG,
    "FMCG - Personal Products": FMCG,
    "FMCG - Tobacco": FMCG,
    "Packaged Foods": FMCG,
    "Packaged Foods & Meats": FMCG,
    "Confectioners": FMCG,
    "Soft Drinks": FMCG,
    "Alcoholic Beverages": FMCG,
    "Tea & Coffee": FMCG,
    "Housewares": FMCG,
    "Consumer non-durables": FMCG,
    "Consumer Defensive": FMCG,
    # Consumer durables
    "Consumer Electronics": CONSUMER_DURABLES,
    "Home Electronics & Appliances": CONSUMER_DURABLES,
    "Furnishings, Fixtures & Appliances": CONSUMER_DURABLES,
    "Footwear": CONSUMER_DURABLES,
    "Luxury Goods": CONSUMER_DURABLES,
    "Consumer durables": CONSUMER_DURABLES,
    "Consumer Cyclical": CONSUMER_DURABLES,
    # Retail
    "Retail - Apparel": RETAIL,
    "Retail - Department Stores": RETAIL,
    "Retail - Online": RETAIL,
    "Retail - Speciality": RETAIL,
    "Retailing": RETAIL,
    "Retail trade": RETAIL,
    "Precious Metals, Jewellery & Watches": RETAIL,
    # Real estate & construction
    "Real Estate": REAL_ESTATE,
    "Real Estate - Development": REAL_ESTATE,
    "Real Estate Services": REAL_ESTATE,
    "Construction & Engineering": REAL_ESTATE,
    "Engineering & Construction": REAL_ESTATE,
    "Building Materials": REAL_ESTATE,
    "Building Products & Equipment": REAL_ESTATE,
    "Building Products - Ceramics": REAL_ESTATE,
    "Building Products - Glass": REAL_ESTATE,
    "Building Products - Granite": REAL_ESTATE,
    "Building Products - Laminates": REAL_ESTATE,
    "Building Products - Others": REAL_ESTATE,
    "Building Products - Pipes": REAL_ESTATE,
    "Building Products - Prefab Structures": REAL_ESTATE,
    "Cement": REAL_ESTATE,
    "Home Furnishing": REAL_ESTATE,
    "Wood Products": REAL_ESTATE,
    "Construction": REAL_ESTATE,
    # Metals & mining
    "Iron & Steel": METALS,
    "Steel": METALS,
    "Metals - Aluminium": METALS,
    "Metals - Coke": METALS,
    "Metals - Copper": METALS,
    "Metals - Diversified": METALS,
    "Metals - Iron": METALS,
    "Metals - Lead": METALS,
    "Metal Fabrication": METALS,
    "Mining - Coal": METALS,
    "Mining - Copper": METALS,
    "Mining - Diversified": METALS,
    "Mining - Iron Ore": METALS,
    "Mining - Manganese": METALS,
    "Other Industrial Metals & Mining": METALS,
    "Non-energy minerals": METALS,
    "Basic Materials": METALS,
    "Materials": METALS,
    "Metals & Mining": METALS,
    # Oil, gas & energy
    "Oil & Gas - Equipment & Services": OIL_GAS,
    "Oil & Gas - Exploration & Production": OIL_GAS,
    "Oil & Gas - Refining & Marketing": OIL_GAS,
    "Oil & Gas - Storage & Transportation": OIL_GAS,
    "Gas Distribution": OIL_GAS,
    "Energy minerals": OIL_GAS,
    "Energy": OIL_GAS,
    "Coal": OIL_GAS,
    # Power & utilities
    "Power Generation": POWER,
    "Power Infrastructure": POWER,
    "Power Transmission & Distribution": POWER,
    "Power Trading & Consultancy": POWER,
    "Utilities": POWER,
    "Utilities - Renewable": POWER,
    "Renewable Energy": POWER,
    "Renewable Energy Equipment & Services": POWER,
    "Water Management": POWER,
    # Chemicals
    "Specialty Chemicals": CHEMICALS,
    "Commodity Chemicals": CHEMICALS,
    "Diversified Chemicals": CHEMICALS,
    "Chemicals": CHEMICALS,
    "Fertilizers & Agro Chemicals": CHEMICALS,
    "Paints": CHEMICALS,
    "Process industries": CHEMICALS,
    "Organic Chemicals": CHEMICALS,
    "Misc.Chem.": CHEMICALS,
    "Specialty Chemicals Industry": CHEMICALS,
    # Agriculture
    "Agro Products": AGRI,
    "Farm Products": AGRI,
    "Seeds": AGRI,
    "Agricultural & Farm Machinery": CAPITAL_GOODS,
    # Textiles
    "Textiles": TEXTILES,
    "Textile Manufacturing": TEXTILES,
    "Apparel & Accessories": TEXTILES,
    "Apparel Manufacturing": TEXTILES,
    "Textiles Apparels & Accessories": TEXTILES,
    # Media
    "Advertising": MEDIA,
    "Cable & D2H": MEDIA,
    "Entertainment": MEDIA,
    "Movies & TV Serials": MEDIA,
    "Publishing": MEDIA,
    "Radio": MEDIA,
    "TV Channels & Broadcasters": MEDIA,
    "Theatres": MEDIA,
    "Theme Parks & Gaming": MEDIA,
    "Media": MEDIA,
    # Transport & logistics
    "Airlines": TRANSPORT,
    "Airports": TRANSPORT,
    "Logistics": TRANSPORT,
    "Marine Shipping": TRANSPORT,
    "Rail": TRANSPORT,
    "Roads": TRANSPORT,
    "Ports": TRANSPORT,
    "Dredging": TRANSPORT,
    "Shipbuilding": TRANSPORT,
    "Transportation": TRANSPORT,
    "Travel Services": TRANSPORT,
    "Tour & Travel Services": TRANSPORT,
    "Warehousing & Logistics": TRANSPORT,
    # Hotels & leisure
    "Hotels, Resorts & Cruise Lines": HOTELS,
    "Lodging": HOTELS,
    "Restaurants": HOTELS,
    "Restaurants & Cafes": HOTELS,
    "Hotels Restaurants & Tourism": HOTELS,
    # Telecom
    "Telecom Equipments": TELECOM,
    "Telecom Infrastructure": TELECOM,
    "Telecom Services": TELECOM,
    "Communications": TELECOM,
    "Communication Services": TELECOM,
    "Telecommunications Equipment": TELECOM,
    # Engineering & capital goods
    "Heavy Electrical Equipments": CAPITAL_GOODS,
    "Heavy Machinery": CAPITAL_GOODS,
    "Industrial Machinery": CAPITAL_GOODS,
    "Specialty Industrial Machinery": CAPITAL_GOODS,
    "Electrical Components & Equipments": CAPITAL_GOODS,
    "Plastic Products": CAPITAL_GOODS,
    "Packaging": CAPITAL_GOODS,
    "Packaging & Containers": CAPITAL_GOODS,
    "Paper & Paper Products": CAPITAL_GOODS,
    "Paper Products": CAPITAL_GOODS,
    "Aerospace & Defense Equipments": CAPITAL_GOODS,
    "Producer manufacturing": CAPITAL_GOODS,
    "Industrials": CAPITAL_GOODS,
    "General Industrials": CAPITAL_GOODS,
    "Industrial services": CAPITAL_GOODS,
    "Industrial Distribution": CAPITAL_GOODS,
    "Cables": CAPITAL_GOODS,
    "Wires & Cables": CAPITAL_GOODS,
    "Stationery": CAPITAL_GOODS,
    "Sugar": CAPITAL_GOODS,
    # Services
    "Academic & Educational Services": SERVICES,
    "Education & Training Services": SERVICES,
    "Education Services": SERVICES,
    "Business Support Services": SERVICES,
    "Consulting Services": SERVICES,
    "Employment Services": SERVICES,
    "Outsourced services": SERVICES,
    "Specialty Business Services": SERVICES,
    "Environmental Services": SERVICES,
    "Commercial services": SERVICES,
    "Consumer services": SERVICES,
    "Distribution services": SERVICES,
    "Commercial Services & Supplies": SERVICES,
    # Diversified / misc
    "Conglomerates": DIVERSIFIED,
    "Commodities Trading": DIVERSIFIED,
    "Miscellaneous": DIVERSIFIED,
    "Government": DIVERSIFIED,
    "Shell Companies": DIVERSIFIED,
    "Diversified": DIVERSIFIED,
    "Others": DIVERSIFIED,
    "N/A": DIVERSIFIED,
}

# HuggingFace / yfinance coarse sectors when industry is missing or mirrors sector.
_COARSE_SECTOR_DISPLAY: dict[str, str] = {
    "Producer manufacturing": CAPITAL_GOODS,
    "Process industries": CHEMICALS,
    "Non-energy minerals": METALS,
    "Energy minerals": OIL_GAS,
    "Basic Materials": METALS,
    "Finance": BANKING,
    "Financial Services": BANKING,
    "Technology": IT,
    "Technology services": IT,
    "Electronic technology": IT,
    "Health technology": PHARMA,
    "Health services": PHARMA,
    "Healthcare": PHARMA,
    "Consumer durables": CONSUMER_DURABLES,
    "Consumer non-durables": FMCG,
    "Consumer Cyclical": CONSUMER_DURABLES,
    "Consumer Defensive": FMCG,
    "Consumer services": HOTELS,
    "Retail trade": RETAIL,
    "Real Estate": REAL_ESTATE,
    "Industrials": CAPITAL_GOODS,
    "Industrial services": CAPITAL_GOODS,
    "Commercial services": SERVICES,
    "Distribution services": SERVICES,
    "Transportation": TRANSPORT,
    "Communications": TELECOM,
    "Communication Services": TELECOM,
    "Energy": OIL_GAS,
    "Utilities": POWER,
    "Miscellaneous": DIVERSIFIED,
}


def display_sector(
    *,
    sector: str = "",
    industry: str = "",
    sub_sector: str = "",
) -> str:
    """Return Indian-market display sector; fall back to original sector when unmapped."""
    for label in (industry, sub_sector):
        key = safe_str(label)
        if key in _INDUSTRY_DISPLAY:
            return _INDUSTRY_DISPLAY[key]

    coarse = safe_str(sector)
    if coarse in _INDUSTRY_DISPLAY:
        return _INDUSTRY_DISPLAY[coarse]
    if coarse in _COARSE_SECTOR_DISPLAY:
        return _COARSE_SECTOR_DISPLAY[coarse]

    ind_lower = safe_str(industry).lower()
    if ind_lower:
        if any(k in ind_lower for k in ("auto", "motor", "vehicle", "tyre", "tire", "battery")):
            return AUTOMOBILE
        if any(k in ind_lower for k in ("bank", "finance", "insurance", "capital market")):
            return BANKING
        if any(k in ind_lower for k in ("software", "it ", "tech")):
            return IT
        if any(k in ind_lower for k in ("pharma", "hospital", "health", "drug", "biotech")):
            return PHARMA
        if "chem" in ind_lower or "fertilizer" in ind_lower or "paint" in ind_lower:
            return CHEMICALS
        if any(k in ind_lower for k in ("textile", "apparel", "garment")):
            return TEXTILES
        if any(k in ind_lower for k in ("real estate", "construction", "cement", "building")):
            return REAL_ESTATE
        if any(k in ind_lower for k in ("steel", "metal", "mining", "iron", "alumin")):
            return METALS
        if "oil" in ind_lower or "gas" in ind_lower or "petrol" in ind_lower:
            return OIL_GAS
        if any(k in ind_lower for k in ("power", "utility", "renewable", "solar", "wind")):
            return POWER
        if "telecom" in ind_lower:
            return TELECOM

    return coarse


def effective_industry_label(
    *,
    sector: str,
    industry: str = "",
    sub_sector: str = "",
    source_sector: str = "",
) -> str:
    """Industry label distinct from display sector when finer taxonomy exists."""
    display = safe_str(sector)
    ind = safe_str(industry)
    if ind and ind != display:
        return ind
    for candidate in (safe_str(sub_sector), safe_str(source_sector)):
        if candidate and candidate != display:
            return candidate
    return ""


def reconcile_industry_labels(stocks: pd.DataFrame) -> pd.DataFrame:
    """Avoid industry == display sector when a finer label is available."""
    if stocks is None or stocks.empty:
        return stocks if stocks is not None else pd.DataFrame()

    out = stocks.copy()
    for col in ("industry", "sub_sector", "source_sector"):
        if col not in out.columns:
            out[col] = ""

    industries: list[str] = []
    sub_sectors: list[str] = []
    for _, row in out.iterrows():
        sector = safe_str(row.get("sector"))
        industry = effective_industry_label(
            sector=sector,
            industry=safe_str(row.get("industry")),
            sub_sector=safe_str(row.get("sub_sector")),
            source_sector=safe_str(row.get("source_sector")),
        )
        sub = safe_str(row.get("sub_sector")) or industry
        industries.append(industry)
        sub_sectors.append(sub)

    out["industry"] = industries
    out["sub_sector"] = sub_sectors
    return out


def apply_display_sector_mapping(stocks: pd.DataFrame) -> pd.DataFrame:
    """Replace ``sector`` with display-friendly labels; keep ``source_sector`` when changed."""
    if stocks is None or stocks.empty:
        return stocks if stocks is not None else pd.DataFrame()

    out = stocks.copy()
    if "sector" not in out.columns:
        out["sector"] = ""
    if "industry" not in out.columns:
        out["industry"] = ""
    if "sub_sector" not in out.columns:
        out["sub_sector"] = ""

    source_sectors: list[str] = []
    display_sectors: list[str] = []
    for _, row in out.iterrows():
        existing_source = safe_str(row.get("source_sector"))
        raw = existing_source or safe_str(row.get("sector"))
        mapped = display_sector(
            sector=raw,
            industry=safe_str(row.get("industry")),
            sub_sector=safe_str(row.get("sub_sector")),
        )
        display_sectors.append(mapped or raw)
        source_sectors.append(existing_source or (raw if raw and raw != mapped else ""))

    out["sector"] = display_sectors
    if "source_sector" not in out.columns:
        out["source_sector"] = source_sectors
    else:
        out["source_sector"] = [
            src or safe_str(existing)
            for src, existing in zip(source_sectors, out["source_sector"], strict=False)
        ]
    return reconcile_industry_labels(out)
