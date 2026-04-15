# PriceOrbit Deployment Guide

## Overview
This guide deploys PriceOrbit to Render with:
- Managed application hosting
- Managed MySQL/PostgreSQL database
- GitHub Actions migration + deploy trigger workflow

## 1. Prerequisites
- GitHub repository with Actions enabled
- Render account
- Kroger API credentials
- Production database connection string

## 2. Required GitHub Secrets
Set these in `Settings -> Secrets and variables -> Actions`:
- `PROD_DATABASE_URL`
- `PROD_MYSQL_PASSWORD`
- `KROGER_CLIENT_ID`
- `KROGER_CLIENT_SECRET`
- `SECRET_KEY`
- `RENDER_DEPLOY_HOOK_URL`

## 3. Create Render Web Service
1. Connect repository in Render.
2. Create a new Web Service using this project.
3. Build command:
   ```bash
   pip install -r requirements.txt
   ```
4. Start command:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
5. Add all required environment variables from `.env.example`.

## 4. Database Migration Strategy
- GitHub Actions workflow `.github/workflows/deploy.yml` runs:
  ```bash
  alembic upgrade head
  ```
  before deploy trigger.
- Keep migrations backward-compatible when possible.

### Free Plan (No Shell Access)
If Render shell is unavailable, use GitHub Actions:
- `.github/workflows/deploy.yml` now runs USITC tariff sync + product tariff resolution during deploy (non-blocking).
- `.github/workflows/tariff-sync.yml` can be triggered manually from the Actions tab (`workflow_dispatch`) and also runs weekly.

Important:
- `PROD_DATABASE_URL` must be the Render database **External URL** so GitHub Actions can connect.

## 5. Health Check Verification
After deployment:
1. Open:
   - `/health`
   - `/docs`
2. Confirm API returns healthy status and docs load.
3. Test auth and product endpoints quickly.

## 6. Rollback Procedure
1. In Render, redeploy previous successful release.
2. If a migration caused the issue:
   - Roll back schema revision manually:
     ```bash
     alembic downgrade -1
     ```
   - Re-run deploy with fixed code.
3. If credentials changed, rotate and update GitHub/Render secrets.

## 7. Production Checklist
- `DEBUG=False`
- strong `SECRET_KEY`
- valid Kroger credentials
- working DB connectivity
- deploy workflow green on `main`
- `/health` confirms healthy
