# stocks package

| Folder | Purpose |
|--------|---------|
| `core/` | Config, SQLite, logging, text helpers |
| `listings/` | India stock universe, sectors, classification |
| `market/` | yfinance prices, fundamentals, indicators |
| `scans/` | Filter bar, playlists, scan toolbar |
| `pages/` | Streamlit screens (one module per sidebar item) |
| `dashboards/` | In-app HTML tables + iframe embed |
| `shared/` | Links, portfolio, corp tags, superstars |
| `strategies/` | Scan logic per feature (see below) |

## Strategies

| Module | Used by |
|--------|---------|
| `tq_bb/` | Strategy page — TQ + Bollinger Bands |
| `tq_recovery/` | Strategy tab — W52 recovery |
| `pead/` + `pead2/` | PEAD page |
| `earnings/` | PEAD scoring helpers |
| `intrinsic_value/` | H&T page |
| `sector_landscape/` | Sector Landscape |
| `valuation_formula/` | Headwind ranking helpers |

## Entry point

`app.py` at repo root imports from `stocks.pages.*`.

## Investment themes (AI infra)

Tags are regex-extracted from About Us / Yahoo profile copy and stored pipe-delimited in `company_profile_cache.theme_tags`. Use them in **Strategy → Watching** quick filters or search the profile text directly.

Implementation: `market/investment_themes.py` (`extract_theme_tags`, `THEME_GROUPS`, `SEARCH_SYNONYMS`).

### Playing the AI theme in India

AI data centers need high-density GPU facilities, clean continuous power, advanced cooling, and low-latency fiber. Ancillary suppliers (power gear, conductors, transformers, switchgear, backup, cooling) often capture the build-out before pure-play AI names.

**What to look for in company profiles**

| Layer | Focus |
|-------|--------|
| In-facility power | Industrial UPS, busways/busducts, medium-voltage switchgear |
| Grid & transmission | 400–765 kV transformers, GIS substations, smart-grid monitoring |
| Ops metrics | Order book / bill > 1.5×, spare capacity, raw-material pass-through (Cu / Al) |

### Core commodities & materials

Search About Us / product pages for these base inputs:

| Keywords | Use |
|----------|-----|
| Copper | Wiring, transformer windings, motor coils, busbars |
| Aluminium | EHV overhead lines, lighter conductors |
| CRGO steel | Transformer core laminations |
| Transformer oil | Insulation and cooling in oil-immersed transformers |
| SF6 | Gas insulation in high-voltage switchgear |
| Epoxy / porcelain / polymer | Cast-coil insulation, line insulators |

Example all-in-one profile match: `ACSR | Copper | Aluminium | Transformer Oil`

Boolean screener example: `("ACSR" OR "Conductor") AND "Transformer Oil" AND ("Copper" OR "Aluminum")`

### Keyword groups (About Us search strings)

Copy-paste these pipe-separated strings into profile search or scrapers. Each group maps to a Watching quick filter in `THEME_GROUPS`.

**1. High-voltage transmission & cable** (`transmission`)

```
ACSR | AAAC | OPGW | Extra High Voltage | EHV Cables | XLPE Insulation | Copper Conductors | Aluminum Rods
```

**2. Transformer core & thermal systems** (`transformers`)

```
Transformer Oil | CRGO Steel | Amorphous Core | Copper Windings | Bushings | Tap Changers | Radiators | Ester Fluid
```

**3. Data-center power & switchgear** (`switchgear`)

```
Switchgear | Busducts | Busbars | Vacuum Circuit Breaker | VCB | GIS Substation | Air Insulated Switchgear | SF6 Gas
```

**4. Backup power & storage** (`backup_power`)

```
Industrial UPS | Flywheel Energy Storage | Lead Acid Batteries | Lithium Iron Phosphate | LiFePO4 | Diesel Generator Sets | BESS
```

**5. Data-center cooling** (`cooling`)

```
Liquid Cooling | Immersion Cooling | Direct-to-Chip | Chilled Water Systems | CRAH | CRAC | Heat Exchangers | Coolant Distribution Unit
```

**All AI infra tags** (`ai_infra`): union of groups above plus `data center`, `smart grid`, `power transmission`, etc. — see `AI_INFRA_THEME_PATTERNS` in code.
