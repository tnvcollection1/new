# Shopify Scraper Web App (FastAPI, v1l)
- Image positions: 1..N (no gaps)
- Only different angles (resized duplicates collapsed)
- Variant images rotate angles across variants
- Optional metafields (Design Code / Fabric / Color / Work Details)

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000
