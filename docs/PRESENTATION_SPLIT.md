# PriceOrbit — 15-Minute Presentation Split

4 members × ~3.5 minutes each

---

## Member 1 — Rishi (Backend Lead) ~3.5 min

**Topic: App Architecture & API Layer**

- `main.py` — app entry point, middleware, scheduler boot
- `app/core/config.py` — env config
- `app/routers/` — walk through one or two routes (e.g. `product_routes.py`, `auth_routes.py`)
- `app/services/auth_service.py` — JWT auth flow

---

## Member 2 — Sabirin (API Integration Lead) ~3.5 min

**Topic: Kroger Integration & Automated Price Updates**

- `app/services/kroger_service.py` — live API calls, search aliases
- `app/tasks/price_updater.py` — scheduled job, locking, batching
- `app/routers/admin_routes.py` — manual trigger + status endpoint
- `data/kroger_search_aliases.json` — alias mapping

---

## Member 3 — Hania (Frontend Lead) ~3.5 min

**Topic: UI & User Experience**

- `app/templates/` — walk through key pages: `index.html`, `product_details.html`, `alerts.html`
- `app/static/js/product_details.js` — price chart, dynamic UI
- `app/static/css/main.css` / `mobile.css` — responsive design

---

## Member 4 — Asha (Data Management Lead) ~3.5 min

**Topic: Data Layer, Models & Tariffs**

- `app/models/` — 5 SQLAlchemy models (user, product, store, price, alert)
- `app/schemas/` — Pydantic validation schemas
- `data/tariff_rates.csv` — tariff data + HTS codes
- `app/services/tariff_resolver_service.py` — tariff resolution logic
- `app/services/health_score_service.py` — health score calculation
- `docs/DATABASE_SCHEMA.md` — quick schema diagram reference
