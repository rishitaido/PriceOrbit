# Sprint 3 Context Prompt for Claude

Copy-paste this at the start of your next Claude conversation:

---

```
I'm the Backend Lead for PriceOrbit, a grocery price prediction web app (CSC4351 capstone). We're starting Sprint 3 and I need help implementing store location features.

PROJECT CONTEXT:
- Tech: FastAPI 0.104.1, SQLAlchemy 2.0.23, MySQL 8.0, Python 3.9+
- Currently: Day 1 of Sprint 3 (February 24, 2025)
- Final deadline: April 12, 2025
- Current location: /Users/rishi/Capstone

WHAT WE'VE BUILT (Sprints 1-2):
✅ Product model with 50 seeded products
✅ Health score algorithm (uses tariff_rate, import_dependency, price_volatility)
✅ Full CRUD API: GET/POST/PATCH/DELETE /api/products
✅ Price history tracking with statistics (min, max, avg, trend, change_7d, change_30d)
✅ Kroger API integration for product prices (OAuth 2.0 with httpx)
✅ Frontend connected to backend (product listing, detail pages, search, filters)
✅ ~40 products mapped to Kroger API with kroger_product_id

DATABASE SCHEMA (Current):
```sql
products:
  - id, name, category, retailer
  - current_price, price_history (JSON)
  - tariff_rate, import_dependency, origin_country
  - health_score, kroger_product_id
  - created_at, updated_at, last_price_check
```

PROJECT STRUCTURE:
```
priceorbit/
├── main.py
├── app/
│   ├── core/
│   │   ├── config.py (Pydantic settings)
│   │   └── exceptions.py (NotFoundError, DuplicateError, ValidationError)
│   ├── db/
│   │   ├── base.py (SQLAlchemy Base)
│   │   └── session.py (get_db dependency)
│   ├── models/
│   │   └── product.py
│   ├── schemas/
│   │   └── product.py (ProductCreate, ProductUpdate, ProductResponse)
│   ├── services/
│   │   ├── product_service.py (CRUD + business logic)
│   │   ├── price_history_service.py (statistics calculations)
│   │   └── kroger_service.py (API integration)
│   └── routers/
│       ├── main.py (homepage)
│       └── products.py (REST API)
├── migrations/
│   └── seed_products.py
└── data/
    └── products_seed.csv
```

ARCHITECTURE PATTERNS WE USE:
1. Service Layer Pattern:
   - Services handle business logic
   - Routers are thin, just call services
   - Services raise custom exceptions (NotFoundError, etc.)
   - Routers catch and map to HTTP status codes

2. Dependency Injection:
   ```python
   def get_service(db: Session = Depends(get_db)) -> Service:
       return Service(db)
   
   @router.get("/endpoint")
   def handler(service: Service = Depends(get_service)):
       return service.method()
   ```

3. Custom Exceptions (not HTTPException in services):
   ```python
   # In services:
   raise NotFoundError("Product", product_id)
   
   # In routers:
   try:
       service.method()
   except NotFoundError as exc:
       raise HTTPException(status_code=404, detail={...})
   ```

CODE STANDARDS (Required):
- Full type hints everywhere
- Comprehensive docstrings (Google style)
- Logging: logger = logging.getLogger(__name__)
- Medium complexity (not over-engineered, practical)
- Follow existing patterns exactly

SPRINT 3 MANDATORY FEATURES (SDD Requirements):
Our capstone SDD requires these features that were missing:

1. "Find Nearby Stores" - Map-based interface showing stores near user
2. "Find Store with Best Price" - Price comparison map with color-coded markers
3. Location services integration (geolocation or zip code)
4. Store-specific pricing (prices vary by location)

MY SPRINT 3 TICKETS (Backend Lead):
- Ticket #34: Create Store Model and Database (5 pts)
- Ticket #35: Store API Endpoints (5 pts)
- Ticket #36: Product Price by Store (8 pts)
- Ticket #37: Simple User Authentication (3 pts)

CURRENT TASK: [Specify which ticket you're working on]

WHAT I NEED:
[Describe what you need help with]

EXAMPLES:
- "Help me create the Store model following our Product model pattern"
- "Build the store API endpoints copying the products.py router structure"
- "Implement Haversine distance calculation for nearby stores"
- "Create ProductStorePrice join table for location-specific pricing"

ADDITIONAL CONTEXT:
- Kroger API supports location_id parameter for store-specific prices
- We'll use Leaflet.js for maps (frontend team handles this)
- Auth needs to be simple JWT - no complex roles for Sprint 3
- Must maintain same code quality as Sprints 1-2

CRITICAL: 
- Follow existing code patterns exactly
- Use custom exceptions, not HTTPException in services
- Include full type hints and docstrings
- Keep it simple - we have 2 weeks for Sprint 3
```

---

## For Specific Tickets, Add:

### If working on Ticket #34 (Store Model):
```
CURRENT TASK: Ticket #34 - Create Store Model

I need to create:
1. app/models/store.py - SQLAlchemy model for Kroger store locations
2. app/schemas/store.py - Pydantic schemas for API responses
3. Alembic migration to create stores table

Requirements:
- Follow exact pattern from app/models/product.py
- Fields: id, name, address, city, state, zip_code, latitude, longitude, phone, hours, created_at, updated_at
- Pydantic schema: StoreResponse with all fields
- Include __repr__ and to_dict() methods

Walk me through creating these files step by step.
```

### If working on Ticket #35 (Store API):
```
CURRENT TASK: Ticket #35 - Store API Endpoints

I need to create:
1. app/services/store_service.py - Business logic for stores
2. app/routers/stores.py - REST API endpoints
3. Haversine distance calculation for nearby stores

Endpoints needed:
- GET /api/stores - List all stores
- GET /api/stores/{id} - Get single store
- GET /api/stores/nearby?lat={lat}&lng={lng}&radius={miles} - Find nearby

Follow exact pattern from products.py router and product_service.py.
Include dependency injection and custom exception handling.

Walk me through implementation.
```

### If working on Ticket #36 (Product Price by Store):
```
CURRENT TASK: Ticket #36 - Product Price by Store

I need to create:
1. app/models/product_store_price.py - Join table model
2. Update product_service.py to handle store-specific prices
3. Endpoint: GET /api/products/{id}/prices?store_ids=1,2,3

Schema:
- ProductStorePrice: product_id (FK), store_id (FK), price, last_updated
- Return format: [{"store_id": 1, "store_name": "...", "price": 3.99, "distance": 2.3}, ...]

When Kroger API returns prices, save to this table with store_id.

Walk me through implementation following our patterns.
```

### If working on Ticket #37 (Auth):
```
CURRENT TASK: Ticket #37 - Simple User Authentication

I need to create:
1. app/models/user.py - User model
2. app/services/auth_service.py - Login/register logic
3. app/routers/auth.py - Auth endpoints
4. JWT token generation and validation

Endpoints:
- POST /api/auth/register - Create account
- POST /api/auth/login - Returns JWT token

Dependencies to install:
- python-jose
- passlib
- bcrypt

Keep it simple for Sprint 3 - just basic login, no roles/permissions yet.
Use FastAPI security tutorial patterns.

Walk me through implementation.
```

---

## Quick Reference Commands

```bash
# Start working
cd /Users/rishi/Capstone
source venv/bin/activate
uvicorn main:app --reload

# Run tests
pytest -v

# Check API docs
open http://localhost:8000/docs

# Database commands
alembic revision --autogenerate -m "description"
alembic upgrade head

# View logs
tail -f app.log
```

---

Save this as `SPRINT3_CONTEXT.md` in your project root for easy copy-paste!