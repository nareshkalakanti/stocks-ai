# stocks package

| Folder | Purpose |
|--------|---------|
| `core/` | Config, SQLite, logging, text helpers |
| `listings/` | India stock universe, sectors, classification |
| `market/` | yfinance prices, fundamentals, indicators |
| `scans/` | Filter bar, playlists, scan toolbar |
| `pages/` | Streamlit screens (one module per sidebar item) |
| `dashboards/` | In-app HTML tables + iframe embed |
| `shared/` | Links, portfolio, HF client, corp tags, superstars |
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
