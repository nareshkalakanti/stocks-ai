# Stocks AI

Streamlit app for Indian equity scans.

**Sidebar:** Settings · Strategy · PEAD · H&T · Sector Landscape · SuperStars · Holdings

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
| `stocks_ai.db` | SQLite cache |
| `bse_codes.csv` | BSE screener symbols |
| `models/` | Optional model weights |
| `logs/errors.log` | Error log |

Listings dataset: Hugging Face `kjhq/India-Stock-Symbols-and-Metadata` (cached in DB).

## Environment

See `.env` — `HF_TOKEN`, `MIN_MARKET_CAP_CR`, `STRATEGY_MAX_WORKERS`, etc.
