# Stocks AI

Streamlit app for Indian equity scans.

**Sidebar:** Strategy · SuperStars · Data

## Repo layout

```
app.py              # entry — streamlit run app.py
requirements.txt
.env
data/               # committed SQLite only
stocks/               # application code (see stocks/README.md)
```

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Data (`data/`)

| Path | Purpose |
|------|---------|
| `stocks_ai.db` | Listings, BSE codes, prices/mcap, profiles, holdings, shareholding, business groups, … |
| `governance.db` | Governance Map boards / directors |

Everything else under `data/` is regenerable (NSE CSV caches, XBRL, logs, `*.db-wal` / `*.db-shm`) and gitignored.

```bash
python scripts/refresh_governance.py --status
python scripts/refresh_governance.py --cins --apify --update-seed
python scripts/refresh_sector_classification.py
```

## Environment

See `.env` — `HF_TOKEN`, `MIN_MARKET_CAP_CR`, `STRATEGY_MAX_WORKERS`, `APIFY_TOKEN`, etc.
