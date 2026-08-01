# Stocks AI

Streamlit app for Indian equity scans.

**Sidebar:** Strategy · PEAD · H&T · Sector Landscape · SuperStars · Holdings · ValuePickr

## Repo layout

```
app.py              # entry — streamlit run app.py
requirements.txt
.env
data/               # SQLite, BSE codes, models, logs
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
| `stocks_ai.db` | SQLite cache (local; not in git) |
| `governance.db` | Governance Map boards/directors (local; not in git) |
| `seeds/governance.db` | **Bundled GovMap snapshot** — copied to `governance.db` on first run |
| `bse_codes.csv` | BSE screener symbols |
| `models/` | Optional model weights |
| `logs/errors.log` | Error log |

**Governance Map on a fresh clone:** commit `data/seeds/governance.db` on `dev` (or `main`). On startup, `ensure_governance_db_seeded()` copies it to `data/governance.db` if that file is missing, empty, or has fewer companies than the seed (stale local DB). Your local `governance.db` stays gitignored so scans and hydrates do not dirty the repo.

To refresh the seed after a big scan:

```bash
cp data/governance.db data/seeds/governance.db
git add data/seeds/governance.db
```

Listings dataset: Hugging Face `kjhq/India-Stock-Symbols-and-Metadata` (cached in DB).

## Environment

See `.env` — `HF_TOKEN`, `MIN_MARKET_CAP_CR`, `STRATEGY_MAX_WORKERS`, etc.

python scripts/refresh_sector_classification.py
# optional: also refresh NSE listing CSVs
python scripts/refresh_sector_classification.py --refresh-csv