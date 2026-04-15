# Tariff Automation Context (PriceOrbit)

## Goal
Build a reliable tariff-tracking workflow that:
- Keeps product tariff data updated over time
- Explains why many products may show `0.00%`
- Uses AI for assistance, while keeping final tariff values deterministic

## Why Many Products Show 0% Tariff
`0.00%` is often valid, not always a bug. Common reasons:
- The product is sourced from a country covered by a free trade agreement (FTA) and qualifies under rules of origin.
- The HTS line has a **specific duty** (e.g., cents/kg) instead of an ad valorem percentage. Your current model stores percent only.
- The product is domestic or effectively treated as low import risk in your seed assumptions.
- The product lacks verified HTS/country mapping and defaults to `0`/`Not specified`.

## Important Principle
Use ChatGPT to **assist** with mapping and explanations, but do **not** treat LLM output as tariff authority.

Recommended split:
- AI: candidate HTS suggestions, confidence scoring, human-readable rationale
- Backend rules/data: final rate assignment, program eligibility checks, audit trail

## Proposed Automation Architecture
1. **Product Classification Layer**
- Input: product name, brand, category, size, description
- Output: candidate HTS code(s), confidence, rationale
- Tooling: deterministic keyword matcher + optional ChatGPT assistant pass

2. **Tariff Resolution Layer (Authoritative)**
- Input: `hts_code`, `origin_country`, trade-program flags
- Output:
  - `applied_tariff_rate_percent` (or `specific_duty_value`)
  - `rate_type` (`ad_valorem`, `specific`, `mixed`, `duty_free`)
  - `source_url`
  - `last_verified_at`

3. **Storage + Audit Layer**
- Persist:
  - `hts_code`
  - `origin_country`
  - `tariff_rate`
  - `rate_type`
  - `verification_source`
  - `verification_notes`
  - `verified_at`
  - `confidence_score`
- Keep change history so you can explain score changes.

4. **Scheduled Refresh**
- Nightly/weekly job:
  - Re-check tariff data for products with stale verification
  - Recompute health scores
  - Flag low-confidence or ambiguous mappings

## Data Quality Rules (Recommended)
- If HTS or origin is missing -> mark status `incomplete` and show UI warning.
- If rate is specific duty (non-percent) -> set `rate_type=specific`, do not force `0.00%` silently.
- If confidence < threshold (e.g., 80) -> send to manual review queue.
- Never overwrite manually-approved HTS mappings without explicit admin action.

## UI Recommendations
On product detail page, show:
- `Tariff Rate` (with type: percent/specific)
- `Origin Country`
- `HTS Code`
- `Verified` date
- `Source` link label (if available)
- `Confidence` badge (`High`, `Medium`, `Needs Review`)

This avoids confusion when users ask why a product shows 0%.

## Rollout Plan
1. Add new schema fields for rate type + verification metadata.
2. Add a tariff resolver service (deterministic).
3. Add scheduled refresh job.
4. Backfill existing products and mark uncertain records for review.
5. Expose verification metadata in admin and product detail APIs/UI.

## Operational Notes
- Rotate secrets immediately if exposed anywhere (DB URLs, API credentials, JWT secret).
- Keep `DEBUG=False` and docs disabled in production.
- Use rate limiting + auth controls on admin endpoints.

## Definition of Done
A product is considered tariff-ready when:
- HTS code is populated
- origin country is populated
- tariff value is resolved with explicit `rate_type`
- verification timestamp exists
- confidence/review status is set

