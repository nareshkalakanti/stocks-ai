"""Map coarse / HF sector labels to Indian market-friendly display names."""

from __future__ import annotations

import re

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

_HF_COARSE_LABELS = frozenset(_COARSE_SECTOR_DISPLAY.keys())

# Friendlier industry labels when only HF coarse taxonomy is available.
_COARSE_INDUSTRY_LABEL: dict[str, str] = {
    "Process industries": "Manufacturing & Processing",
    "Producer manufacturing": "Manufacturing",
    "Non-energy minerals": "Metals & Mining",
    "Energy minerals": "Oil, Gas & Mining",
    "Finance": "Financial Services",
    "Technology services": "IT Services",
    "Electronic technology": "Electronics & Technology",
    "Consumer durables": "Consumer Durables",
    "Consumer non-durables": "FMCG & Consumables",
    "Health technology": "Pharmaceuticals & Healthcare",
    "Health services": "Healthcare Services",
    "Distribution services": "Trading & Distribution",
    "Industrial services": "Industrial Services",
    "Commercial services": "Commercial Services",
    "Consumer services": "Consumer Services",
    "Retail trade": "Retail",
    "Transportation": "Transportation & Logistics",
    "Utilities": "Power & Utilities",
    "Communications": "Telecom & Communications",
    "Miscellaneous": "Diversified",
}

_AUTO_NAME_MARKERS = (
    "automobile",
    "automotive",
    "automation",
    " autol",
    "auto ",
    "auto-",
    "autopin",
    "autorid",
    "autocast",
    "autocorp",
    "motorcycle",
    " motor ",
    " motors",
    "motocorp",
    "vehicle",
    "vehicles",
    "tyre",
    "tires",
    "tire",
    "scooter",
    "tractor",
    "maruti",
    "leyland",
    "bajaj auto",
    "hero ",
    "tvs motor",
    "eicher",
    "force motor",
    "piaggio",
    "cycle & motor",
)

_PHARMA_NAME_MARKERS = (
    "pharma",
    "pharmaceutical",
    " drug ",
    " drugs",
    " biotech",
    "medicine",
    "diagnostic",
    " hospital",
    "healthcare",
)

_BANK_NAME_RE = re.compile(
    r"\b(bank|financier|housing finance|microfinance|small finance bank)\b",
    re.I,
)

_REAL_ESTATE_NAME_MARKERS = (
    " real estate",
    " realty",
    " developers",
    " developer ",
    " construction ltd",
    " infra ltd",
    " infrastructure ltd",
)


def _name_lower(name: str) -> str:
    return f" {safe_str(name).lower()} "


def _name_suggests_automobile(name: str) -> bool:
    n = _name_lower(name)
    return any(marker in n for marker in _AUTO_NAME_MARKERS)


def _name_suggests_pharma(name: str) -> bool:
    n = _name_lower(name)
    return any(marker in n for marker in _PHARMA_NAME_MARKERS)


def _name_suggests_banking(name: str) -> bool:
    return bool(_BANK_NAME_RE.search(safe_str(name)))


def _name_suggests_real_estate(name: str) -> bool:
    n = _name_lower(name)
    return any(marker in n for marker in _REAL_ESTATE_NAME_MARKERS)


def _humanize_coarse_industry(label: str) -> str:
    key = safe_str(label)
    if not key:
        return ""
    return _COARSE_INDUSTRY_LABEL.get(key, key)


def _industry_from_name(name: str) -> str:
    n = _name_lower(name)
    if _name_suggests_automobile(name):
        return "Automobile & Components"
    if _name_suggests_pharma(name):
        return "Pharmaceuticals & Healthcare"
    if _name_suggests_banking(name):
        return "Banking & Financial Services"
    if _name_suggests_real_estate(name):
        return "Real Estate & Construction"
    if any(k in n for k in (" hotel", " hospitality", " resort", " tourism", " restaurant")):
        return "Hotels & Hospitality"
    if any(k in n for k in (" textile", " garment", " apparel", " fabric")):
        return "Textiles & Apparel"
    if any(k in n for k in (" steel", " iron ore", " metal ")):
        return "Steel & Metals"
    if any(k in n for k in (" oil ", " petroleum", " petrol", " gas ltd")):
        return "Oil & Gas"
    if any(k in n for k in (" software", " technology", " infotech", " it ltd")):
        return "Software & IT Services"
    return ""


def refine_display_sector_from_name(
    *,
    name: str,
    sector: str,
    source_sector: str = "",
) -> str:
    """Correct obvious HF mis-buckets using the company name."""
    current = safe_str(sector)
    source = safe_str(source_sector)
    if not current:
        return current

    if _name_suggests_automobile(name) and current != AUTOMOBILE:
        return AUTOMOBILE
    if _name_suggests_pharma(name) and current not in {PHARMA, FMCG}:
        return PHARMA
    if _name_suggests_banking(name) and current != BANKING:
        return BANKING
    if _name_suggests_real_estate(name) and current not in {REAL_ESTATE, CAPITAL_GOODS}:
        return REAL_ESTATE

    # HF often tags auto ancillaries as producer manufacturing / consumer durables.
    if source in {"Consumer durables", "Producer manufacturing", "Retail trade"}:
        if _name_suggests_automobile(name):
            return AUTOMOBILE

    return current


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


def display_sectors_for_labels(labels) -> set[str]:
    """Map classifier labels (industry / sub-sector / coarse sector) to display sectors."""
    out: set[str] = set()
    for label in labels:
        key = safe_str(label).strip()
        if not key or key.upper() in {"N/A", "NA"}:
            continue
        mapped = display_sector(sector=key, industry=key, sub_sector=key)
        if mapped:
            out.add(mapped)
    return out


def match_classifier_mask(df: pd.DataFrame, labels) -> pd.Series:
    """True where a row matches any classifier label (fine tags or display sector peers)."""
    label_set = {
        safe_str(v).strip()
        for v in labels
        if safe_str(v).strip() and safe_str(v).strip().upper() not in {"N/A", "NA"}
    }
    if not label_set:
        return pd.Series(False, index=df.index)

    display_targets = display_sectors_for_labels(label_set)
    mask = pd.Series(False, index=df.index)
    for col in ("industry", "sub_sector", "sector"):
        if col not in df.columns:
            continue
        mask |= df[col].astype(str).str.strip().isin(label_set)
    if display_targets and "sector" in df.columns:
        untagged = pd.Series(True, index=df.index)
        for col in ("industry", "sub_sector"):
            if col in df.columns:
                untagged &= df[col].astype(str).str.strip().eq("")
        mask |= untagged & df["sector"].astype(str).str.strip().isin(display_targets)
    return mask


def effective_industry_label(
    *,
    sector: str,
    industry: str = "",
    sub_sector: str = "",
    source_sector: str = "",
    name: str = "",
) -> str:
    """Industry label distinct from display sector when finer taxonomy exists."""
    display = safe_str(sector)
    ind = safe_str(industry)
    if ind and ind != display and ind not in _DISPLAY_IDENTITY:
        if ind not in _HF_COARSE_LABELS:
            return ind
        humanized = _humanize_coarse_industry(ind)
        if humanized and humanized != display:
            return humanized

    sub = safe_str(sub_sector)
    if sub and sub != display and sub not in _DISPLAY_IDENTITY and sub not in _HF_COARSE_LABELS:
        return sub

    name_ind = _industry_from_name(name)
    if name_ind and name_ind != display:
        return name_ind

    for candidate in (sub, safe_str(source_sector)):
        if not candidate or candidate == display or candidate in _DISPLAY_IDENTITY:
            continue
        if candidate in _HF_COARSE_LABELS:
            humanized = _humanize_coarse_industry(candidate)
            if humanized and humanized != display:
                return humanized
            continue
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
            name=safe_str(row.get("name")),
        )
        sub = industry or safe_str(row.get("sub_sector"))
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
        mapped = refine_display_sector_from_name(
            name=safe_str(row.get("name")),
            sector=mapped or raw,
            source_sector=existing_source or raw,
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
