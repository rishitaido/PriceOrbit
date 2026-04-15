# PriceOrbit

PriceOrbit is a FastAPI application for tracking grocery prices, mapping Kroger products and stores, and surfacing price differences across locations.

## Features
- Product catalog with tariff metadata and health score calculation
- Store locator with map-based nearby search
- Store-specific pricing (`product_store_prices`)
- User authentication (register/login/JWT)
- Kroger API integration (product + location lookup)
- Automated price-update scheduler + manual admin trigger

## Tech Stack
- FastAPI
- SQLAlchemy + Alembic
- MySQL (PyMySQL)
- APScheduler
- Pytest

## Quick Start
1. Create and activate virtualenv.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy env template and fill values:
   ```bash
   cp .env.example .env
   ```
4. Run migrations:
   ```bash
   alembic upgrade head
   ```
5. Start app:
   ```bash
   uvicorn main:app --reload
   ```

## Core Endpoints
- Health:
  - `GET /health`
- Auth:
  - `POST /api/auth/register`
  - `POST /api/auth/login`
  - `GET /api/auth/me`
- Alerts:
  - `POST /api/alerts`
  - `GET /api/alerts`
  - `DELETE /api/alerts/{id}`
- Products:
  - `GET /api/products`
  - `GET /api/products/{id}`
  - `GET /api/products/{id}/prices`
  - `POST /api/products/{id}/update-price`
  - `POST /api/products/update-all-prices`
- Stores:
  - `GET /api/stores`
  - `GET /api/stores/{id}`
  - `GET /api/stores/nearby?lat=...&lng=...&radius=...`
- Admin:
  - `POST /api/admin/trigger-price-update`
  - `GET /api/admin/price-update-status`
  - `GET /api/admin/dashboard-metrics`

## Scheduler
The daily scheduler runs at `06:00 UTC` by default and can be tuned via env vars:
- `PRICE_UPDATE_JOB_ENABLED`
- `PRICE_UPDATE_CRON_HOUR_UTC`
- `PRICE_UPDATE_BATCH_SIZE`
- `PRICE_UPDATE_DELAY_SECONDS`
- `PRICE_UPDATE_MAX_DAILY_CALLS`
- `PRICE_UPDATE_RUN_ON_STARTUP_IF_STALE`
- `PRICE_UPDATE_STALE_HOURS`

Logs are written to:
- `app/logs/price_updates.log`

## Price History (Kroger-Only)
To keep history points sourced from live Kroger calls only:

```bash
python scripts/rebuild_kroger_only_history.py --clear-existing
```

Optional flags:
- `--limit N` process first N products
- `--delay-seconds X` throttle API calls

## Synthetic Backfill (Optional)
If you still want generated historical points for demo charts:

```bash
python scripts/backfill_price_history.py --days 30
```

## USITC Tariff Refresh
To refresh `data/tariff_rates.csv` from USITC by HTS code:

```bash
python scripts/update_tariffs_from_usitc.py --dry-run
python scripts/update_tariffs_from_usitc.py
```

Optional flags:
- `--resolve-products` run in-app tariff resolution after CSV update
- `--resolve-stale-only` only update stale/unverified product records
- `--resolve-force` override manual tariff lock

## Documentation
- Deployment: `docs/DEPLOYMENT.md`
- Database schema: `docs/DATABASE_SCHEMA.md`
- Sprint 4 report draft: `docs/SPRINT4_REPORT.md`
- Sprint context handoff: `SPRINT4_CONTEXT.md`

## Testing
```bash
pytest tests/ -q
pytest tests/ -q --cov=app
```

## Team
- Rishi Raj (Backend Lead)
- Sabirin Mohamed (API Integration Lead)
- Hania Zaidi (Frontend Lead)
- Asha Iman (Data Management Lead)
