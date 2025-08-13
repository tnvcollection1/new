# Shopify Scraper Web App (FastAPI, Render-safe)

- Image positions: 1..N (no gaps)
- Only different angles (resized duplicates collapsed)
- Variant images rotate angles across variants
- Optional metafields (Design Code / Fabric / Color / Work Details)
- Health endpoints for Render (`/healthz`, `HEAD /`)

## Deploy to Render (web only)
1) Upload this folder's contents to a new GitHub repo (Add file → Upload files).
2) Render → New → Web Service → select the repo (Docker is auto-detected).
3) Click Create. Done.

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000
