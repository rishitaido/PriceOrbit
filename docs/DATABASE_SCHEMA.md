# PriceOrbit Database Schema

## Current Models

### `products`
- `id` (PK)
- `name`
- `category`
- `retailer`
- `description`
- `current_price`
- `price_history` (JSON)
- `tariff_rate`
- `import_dependency`
- `hts_code`
- `origin_country`
- `rate_type`
- `specific_duty_value`
- `source_url`
- `verification_source`
- `verification_notes`
- `verified_at`
- `confidence_score`
- `review_status`
- `manual_tariff_override`
- `health_score`
- `kroger_product_id` (unique)
- `image_url`
- `last_price_check`
- `created_at`
- `updated_at`

Indexes:
- `ix_products_id`
- `ix_products_name`
- `ix_products_category`
- `ix_products_verified_at`
- `ix_products_review_status`

### `stores`
- `id` (PK)
- `name`
- `address`
- `city`
- `state`
- `zip_code`
- `kroger_location_id` (unique)
- `latitude`
- `longitude`
- `phone`
- `hours`
- `created_at`
- `updated_at`

Indexes:
- `ix_stores_id`
- `ix_stores_name`
- `ix_stores_city`
- `ix_stores_state`
- `ix_stores_zip_code`
- `ix_stores_latitude`
- `ix_stores_longitude`
- `ix_stores_kroger_location_id`

### `users`
- `id` (PK)
- `email` (unique)
- `full_name`
- `hashed_password`
- `is_active`
- `created_at`
- `updated_at`

Indexes:
- `ix_users_id`
- `ix_users_email`

### `product_store_prices`
- `id` (PK)
- `product_id` (FK -> `products.id`)
- `store_id` (FK -> `stores.id`)
- `price`
- `last_updated`

Constraints:
- unique (`product_id`, `store_id`) via `uq_product_store_price`

Indexes:
- `ix_product_store_prices_id`
- `ix_product_store_prices_product_id`
- `ix_product_store_prices_store_id`
- `ix_product_store_prices_last_updated`

## Relationships
- `Product 1..* ProductStorePrice`
- `Store 1..* ProductStorePrice`
- `User` currently independent for auth (alerts planned in Sprint 4 extension)

## Migration Order
1. `bf251f5767b3_initial_schema` (products)
2. `8f2c4ba9d1a7_add_users_table`
3. `d4c1e8b9f2a1_add_price_alerts_table`
4. `7e90d6e2e6a3_add_stores_table`
5. `33a5d9c12b4f_add_product_store_prices`
6. `f9d3c7a21b8e_add_tariff_verification_metadata` (current head)

## Planned Extension
- `price_alerts` table:
  - `user_id` FK
  - `product_id` FK
  - `target_price`
  - `is_active`
  - timestamps
