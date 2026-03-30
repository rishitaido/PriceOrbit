

## Critical Context from Sprint 3 Handoff

**Current State (March 27):**
- 14 uncommitted files in worktree
- Test coverage: 63% (target: 60%+ achieved, stretch to 70%)
- Tariff coverage: 15/50 products (need 45+)
- Stores: 20 (need 50+)
- Kroger mapping: 50/50 ✅
- Database: products=50, stores=20, users=5, product_store_prices=252

**Technical Debt to Address:**
1. `migrations/seed_stores.py` out of sync with KrogerService
2. Commit dirty worktree (14 files)
3. SQLAlchemy deprecation warnings

---

## Team Assignments - Sprint 4

### Rishi Raj - Backend Lead (16 points)

**Focus:** Technical debt cleanup, automated updates, production deployment, documentation

#### Ticket #47: Fix Sprint 3 Technical Debt (3 pts)
**Priority:** Critical - Day 1 task  
**Status:** Blocker for other work

**Tasks:**
1. Commit dirty worktree changes
   - Review and commit 14 modified files in logical groups
   - Test all changes before committing
   - Push to main branch

2. Fix `migrations/seed_stores.py`
   - Update to match current KrogerService.search_stores() response
   - Fix parameter names: `radius` → `radius_miles`
   - Test script successfully seeds stores

3. Fix deprecation warnings
   - Update `app/db/base.py` to use DeclarativeBase pattern
   - Resolve passlib crypt warnings

**Deliverables:**
- Clean git status
- seed_stores.py working
- No deprecation warnings

---

#### Ticket #49: Automated Price Updates (5 pts)
**Priority:** High  
**Dependencies:** Ticket #47

**Tasks:**
1. Install APScheduler
   - Add `apscheduler==3.10.4` to requirements.txt
   - Create `app/tasks/__init__.py`

2. Create scheduled price updater
   - Create `app/tasks/price_updater.py`
   - Daily job at 6 AM UTC
   - Batch processing: 10 products, 2-second delays
   - Respect Kroger API rate limits (500/day)

3. Integration with main.py
   - Start scheduler in lifespan startup
   - Graceful shutdown in teardown
   - File lock to prevent multiple instances

4. Admin endpoint
   - `POST /api/admin/trigger-price-update`
   - Manual trigger capability
   - Returns job status

5. Logging
   - Log to `app/logs/price_updates.log`
   - Success/failure counts per run

**Deliverables:**
- Automated daily price updates
- Manual trigger endpoint
- Comprehensive logging

---

#### Ticket #51: Production Deployment (5 pts)
**Priority:** High  
**Dependencies:** All other backend tickets

**Tasks:**
1. Choose deployment platform
   - Recommended: Railway or Render (free tier)
   - Configure environment variables
   - Set up database (managed MySQL or PostgreSQL)

2. GitHub Actions workflow
   - Create `.github/workflows/deploy.yml`
   - Auto-deploy on merge to main
   - Run migrations automatically

3. Production configuration
   - Create production `.env.example`
   - Document all required environment variables
   - Health check verification

4. Deployment documentation
   - Create `docs/DEPLOYMENT.md`
   - Step-by-step deployment guide
   - Rollback procedures

**Deliverables:**
- Live production URL
- GitHub Actions CI/CD working
- Complete deployment docs

---

#### Ticket #54: Final Documentation (3 pts)
**Priority:** High  
**Dependencies:** All tickets

**Tasks:**
1. Update README.md
   - Project description and features
   - Complete setup instructions
   - All environment variables documented
   - Team member credits

2. Document database schema
   - All models: Product, Store, User, ProductStorePrice, PriceAlert
   - Relationships diagram
   - Migration order

3. Inline code documentation
   - Add docstrings to undocumented methods
   - Update existing docstrings
   - Code comments for complex logic

4. Sprint 4 report
   - Complete sprint summary
   - Velocity and metrics
   - Lessons learned

**Deliverables:**
- Professional README.md
- Complete code documentation
- Sprint 4 report

---

### Sabirin Mohamed - API Integration Lead (13 points)

**Focus:** Price alerts, tariff data completion, performance optimization

#### Ticket #50: Complete Tariff Data Coverage (URGENT - 5 pts)
**Priority:** Critical  
**Current:** 15/50 products  
**Target:** 45+/50 products

**Tasks:**
1. Research HTS codes for remaining 35 products
   - Use https://hts.usitc.gov/
   - Focus on high-import items: avocados, salmon, shrimp, coffee, bananas
   - Document sources in `data/tariff_sources.txt`

2. Update `data/tariff_rates.csv`
   - Add 30+ more products with HTS codes and rates
   - Validation: rates 0-25%
   - Include source URLs

3. Import and verify
   - Run `python migrations/import_tariff_data.py`
   - Verify health scores recalculated
   - Confirm: `SELECT COUNT(*) FROM products WHERE tariff_rate > 0` ≥ 45

**Deliverables:**
- 45+ products with real tariff data
- Updated tariff_rates.csv
- Documentation of sources

---

#### Ticket #47: Price Alert System (5 pts)
**Priority:** High  
**Dependencies:** User authentication from Sprint 3

**Tasks:**
1. Create PriceAlert model
   - Fields: user_id (FK), product_id (FK), target_price, is_active, created_at
   - Migration: `alembic revision --autogenerate -m "add price alerts"`

2. Alert API endpoints
   - `POST /api/alerts` - Create alert
   - `GET /api/alerts` - List user's alerts (requires auth)
   - `DELETE /api/alerts/{id}` - Remove alert

3. Alert service
   - Create `app/services/alert_service.py`
   - Check alerts after each price update
   - Log triggered alerts (email optional for Sprint 4)

4. Integration with price updater
   - After price update, check all active alerts
   - If current_price ≤ target_price, trigger alert
   - Log to console: "Alert triggered for user X on product Y"

**Deliverables:**
- PriceAlert model and endpoints
- Alert checking logic
- Console logging of triggered alerts

---

#### Ticket #53: Performance Optimization (3 pts)
**Priority:** Medium  
**Dependencies:** None

**Tasks:**
1. Database indexes
   - Add index on `products.kroger_product_id`
   - Add composite index on `product_store_prices(product_id, store_id)`
   - Add indexes on `stores(latitude, longitude)`

2. Backend optimization
   - Verify KrogerService token caching working
   - Add simple cache for store locations (1 hour TTL)
   - Profile update_all_prices() for bottlenecks

3. Frontend optimization
   - Minimize CSS/JS files
   - Lazy load map markers (>20 stores)
   - Reduce product page load time

4. Benchmarking
   - Document before/after metrics
   - Create `docs/PERFORMANCE.md`

**Deliverables:**
- Database indexes added
- Performance improvements documented
- Benchmark results

---

### Hania Zaidi - Frontend Lead (10 points)

**Focus:** Admin dashboard, mobile responsiveness

#### Ticket #48: Admin Dashboard (5 pts)
**Priority:** High  
**Dependencies:** None

**Tasks:**
1. Create `/admin` page
   - Accessible from navigation
   - Simple card-based layout

2. Display metrics (use existing endpoints)
   - Total products tracked
   - Total stores in database
   - Recent price updates (last 10)
   - Failed API calls count
   - Last price check timestamps

3. Admin actions
   - "Trigger Price Update" button → `POST /api/admin/trigger-price-update`
   - Show loading state during update
   - Display success/failure message

4. Styling
   - Reuse existing CSS
   - Responsive card grid
   - Professional appearance

**Deliverables:**
- Working admin dashboard
- Real-time metrics display
- Manual price update trigger

---

#### Ticket #52: Mobile Responsive (5 pts)
**Priority:** High for showcase  
**Dependencies:** None

**Tasks:**
1. Audit all pages for mobile issues
   - Product listing
   - Product detail
   - Stores map
   - Navigation
   - Forms (login/register)

2. Add mobile CSS
   - Media queries for <768px screens
   - Hamburger menu for navigation
   - Touch-friendly buttons (44x44px minimum)

3. Map mobile optimization
   - Full-screen map option
   - Touch-friendly zoom controls
   - Prominent geolocation button

4. Testing
   - Chrome DevTools mobile simulator
   - Test on actual iPhone/Android (optional)
   - Tablet landscape/portrait

**Deliverables:**
- All pages mobile-responsive
- Touch-friendly interface
- Testing documentation

---

### Asha Iman - Data Management Lead (8 points)

**Focus:** Test coverage, store expansion

#### Ticket #50: Test Coverage to 60%+ (5 pts)
**Priority:** High  
**Current:** 63% (already met target!)  
**Stretch Goal:** 70%

**Tasks:**
1. Measure current coverage
   - Run `pytest --cov=app tests/`
   - Identify low-coverage modules

2. Add tests for new Sprint 3 features
   - `app/services/product_store_price_service.py`
   - `app/services/store_service.py`
   - `app/routers/store_routes.py`
   - `app/services/auth_service.py`

3. Priority test areas
   - Mock Kroger API calls with httpx
   - Test price update logic
   - Test alert system
   - Test store nearby calculation (Haversine)

4. Coverage report
   - Generate HTML report
   - Document gaps in `tests/README.md`

**Deliverables:**
- Test coverage ≥60% (stretch: 70%)
- All new tests passing
- Coverage report

---

#### Ticket #56: Store Data Expansion (3 pts)
**Priority:** Medium  
**Current:** 20 stores  
**Target:** 50+ stores

**Tasks:**
1. Fix `migrations/seed_stores.py`
   - Work with Rishi to ensure it works with current service
   - Support multiple zip codes

2. Seed stores in multiple locations
   - Atlanta, GA: 15 stores (existing)
   - Los Angeles, CA: 15 stores
   - Chicago, IL: 10 stores
   - Houston, TX: 10 stores

3. Data quality verification
   - All stores have valid lat/lng
   - Complete addresses
   - Phone numbers formatted

**Deliverables:**
- 50+ stores in database
- Geographic diversity
- Working seed script

---

## Sprint 4 Summary

**Total Story Points:** 47 points  
**Team Capacity:** 11 days × 4 people = reasonable workload  
**Realistic Completion:** High confidence

### Must Complete (Critical Path):
1. ✅ Fix technical debt (Rishi - Day 1)
2. ✅ Complete tariff data 45+ (Sabirin - Days 1-3)
3. ✅ Automated price updates (Rishi - Days 2-5)
4. ✅ Price alert system (Sabirin - Days 3-6)
5. ✅ Admin dashboard (Hania - Days 1-4)
6. ✅ Mobile responsive (Hania - Days 5-8)
7. ✅ Production deployment (Rishi - Days 6-9)
8. ✅ Final documentation (Rishi + Asha - Days 9-11)

### Should Complete:
- Test coverage to 60%+ (Asha) - Already at 63%!
- Performance optimization (Sabirin)
- Store expansion to 50+ (Asha)

### Sprint 4 Demo (April 6):
- ✅ Price alerts triggering on price drops
- ✅ Admin dashboard showing live metrics
- ✅ Production URL live and accessible
- ✅ Mobile responsive on phone simulator
- ✅ Test coverage report ≥60%

### Buffer Period (April 7-16):
- Final bug fixes
- CS Showcase preparation
- Demo script and video
- UI polish
- README polish

---

## Success Criteria (April 6)

**Mandatory (SDD Requirements):**
- [x] Find Nearby Stores (map interface) - Done Sprint 3
- [x] Find Store with Best Price (price comparison) - Done Sprint 3
- [x] User authentication - Done Sprint 3
- [ ] Price alerts functional
- [ ] Admin dashboard working
- [ ] Production deployment live
- [ ] 45+ products with real tariff data

**Technical Requirements:**
- [ ] Test coverage ≥60%
- [ ] Automated price updates running
- [ ] Mobile responsive UI
- [ ] Complete documentation
- [ ] Clean codebase (no deprecation warnings)

---

## Risk Mitigation

**Critical Risks:**
1. **Tariff data research time** (Sabirin)
   - Mitigation: Start immediately, parallelize with Asha if needed
   - Fallback: 40/50 products acceptable if documented

2. **Production deployment complexity**
   - Mitigation: Use Railway/Render (simpler than AWS)
   - Fallback: Document deployment steps, deploy in buffer period

**Medium Risks:**
1. **APScheduler integration**
   - Mitigation: Use well-documented examples
   - Fallback: Manual trigger only, document automated setup

2. **Mobile testing**
   - Mitigation: Chrome DevTools first, real devices optional
   - Sufficient for showcase

---

## Daily Progress Tracking

**Discord Standup (6 PM daily):**
```
Day X Progress:
- Completed: [ticket/task]
- In Progress: [ticket/task]
- Blockers: [any issues]
- Tomorrow: [plan]
```

**Key Milestones:**
- Day 1 (Mar 27): Technical debt resolved, tariff research started
- Day 3 (Mar 29): Tariff data complete, price alerts started
- Day 5 (Mar 31): Automated updates working, admin dashboard done
- Day 7 (Apr 2): Mobile responsive complete, production prep started
- Day 9 (Apr 4): Production deployed, testing complete
- Day 11 (Apr 6): Documentation done, demo ready

---


**This is the definitive Sprint 4 plan that addresses both technical debt AND delivers all required features for a complete, production-ready capstone project.**