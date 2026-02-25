# PriceOrbit API

A grocery price prediction system that monitors tariffs, supply chain dynamics, and retail prices to provide intelligent price forecasting and analysis.

## 🎯 Project Overview

PriceOrbit is a FastAPI-based backend service that integrates with the Kroger API to track and analyze grocery prices. The system uses SQLAlchemy for database management and Alembic for database migrations, providing a robust foundation for price tracking and prediction.

## 🏗️ Project Structure

```
Capstone/
├── app/                    # Main application package
│   ├── core/              # Core configuration and settings
│   ├── db/                # Database connection and session management
│   ├── models/            # SQLAlchemy database models
│   │   └── product_model.py
│   ├── routers/           # API and page route handlers
│   │   ├── main.py
│   │   └── product_routes.py
│   ├── schemas/           # Pydantic request/response schemas
│   │   └── product_schemas.py
│   ├── services/          # Business logic and external API integrations
│   │   ├── product_service.py
│   │   ├── health_score_service.py
│   │   ├── price_history_service.py
│   │   └── kroger_service.py
│   ├── static/            # Static files (CSS, JS, images)
│   └── templates/         # Jinja2 HTML templates
├── migrations/            # Alembic database migration files
│   ├── versions/          # Individual migration scripts
│   ├── env.py            # Alembic environment configuration
│   ├── script.py.mako    # Template for generating new migrations
│   ├── init_db.py        # Database initialization script
│   ├── seed_products.py  # Product seeding script
│   ├── map_kroger_products.py
│   └── fetch_initial_prices.py
├── data/                  # Data files and datasets
├── docs/                  # Documentation
├── scripts/               # Utility scripts
├── tests/                 # Test files
├── alembic.ini           # Alembic configuration file
├── main.py               # Application entry point
├── requirements.txt      # Python dependencies
└── .env                  # Environment variables (not in version control)
```

## 📋 Key Files Explained

### `alembic.ini`
This is the **Alembic configuration file** that controls database migration behavior:

- **Purpose**: Configures how Alembic manages database schema changes
- **Key Settings**:
  - `script_location`: Points to the `migrations/` directory where migration files are stored
  - `sqlalchemy.url`: Database connection string (loaded from `.env` in practice)
  - `path_separator`: Defines how file paths are split (uses OS-specific separators)
  - Logging configuration for migration operations
- **When to modify**: Rarely needs changes unless you're adjusting migration file organization or logging levels

### `migrations/script.py.mako`
This is a **Mako template** used by Alembic to generate new migration files:

- **Purpose**: Template for creating new database migration scripts
- **How it works**: When you run `alembic revision --autogenerate -m "message"`, Alembic uses this template to create a new Python file in `migrations/versions/`
- **Template variables**:
  - `${message}`: Your migration description
  - `${up_revision}`: Current revision ID
  - `${down_revision}`: Previous revision ID
  - `${create_date}`: Timestamp of migration creation
  - `${upgrades}`: Auto-generated upgrade operations
  - `${downgrades}`: Auto-generated downgrade operations
- **Functions**:
  - `upgrade()`: Applies schema changes (e.g., creating tables, adding columns)
  - `downgrade()`: Reverts schema changes (rollback functionality)

### `migrations/env.py`
The **Alembic environment configuration** that connects your models to the migration system:

- **Purpose**: Bridges your SQLAlchemy models with Alembic's migration engine
- **Key responsibilities**:
  - Loads environment variables from `.env`
  - Imports your SQLAlchemy `Base` metadata
  - Configures database connection for migrations
  - Provides offline and online migration modes
- **Important**: This file imports `app.db.base.Base` to ensure all models are registered for autogeneration

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- MySQL database
- Kroger API credentials

### Installation

1. **Clone the repository**
   ```bash
   cd /Users/rishi/Capstone
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Create a `.env` file in the project root with the following variables:
   ```env
   # Database Configuration
   DATABASE_URL=mysql+pymysql://user:password@localhost:3306/priceorbit_db
   MYSQL_HOST=localhost
   MYSQL_PORT=3306
   MYSQL_USER=root
   MYSQL_PASSWORD=your_password
   MYSQL_DATABASE=priceorbit_db
   
   # Kroger API
   KROGER_CLIENT_ID=your_client_id
   KROGER_CLIENT_SECRET=your_client_secret
   
   # Application
   SECRET_KEY=your_secret_key
   DEBUG=True
   PORT=8080
   ```

5. **Initialize the database**
   ```bash
   # Create initial migration
   alembic revision --autogenerate -m "Initial migration"
   
   # Apply migrations
   alembic upgrade head
   
   # (Optional) Seed sample data
   python migrations/seed_products.py
   ```

### Running the Application

```bash
# Development mode (with auto-reload)
python main.py

# Or using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

The API will be available at:
- **API**: http://localhost:8080
- **Interactive Docs**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc
- **Health Check**: http://localhost:8080/health

## 🗄️ Database Migrations with Alembic

Alembic is a database migration tool that tracks and applies schema changes over time.

### Common Alembic Commands

```bash
# Create a new migration (auto-detect model changes)
alembic revision --autogenerate -m "Add new table"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history

# Check current database version
alembic current

# Rollback to specific revision
alembic downgrade <revision_id>
```

### Migration Workflow

1. **Modify your SQLAlchemy models** in `app/models/`
2. **Generate migration**: `alembic revision --autogenerate -m "Description"`
3. **Review the generated file** in `migrations/versions/`
4. **Apply migration**: `alembic upgrade head`
5. **Commit both** the model changes and migration file to version control

## 🛠️ Technology Stack

- **Framework**: FastAPI 0.104.1
- **Database ORM**: SQLAlchemy 2.0.23
- **Database**: MySQL (via PyMySQL)
- **Migrations**: Alembic 1.18.3
- **Server**: Uvicorn 0.24.0
- **Validation**: Pydantic 2.5.0
- **Testing**: Pytest 7.4.0
- **Templating**: Jinja2 3.1.2

## 📡 API Endpoints

### Health Check
```
GET /health
```
Returns API status and version information.

### Page Routes (`app/routers/main.py`)
```
GET /
GET /products.html
GET /about.html
GET /product/{product_id}
GET /products/{product_id}
```

### Product API Routes (`/api/products`, `app/routers/product_routes.py`)
```
GET    /api/products
GET    /api/products/{product_id}
POST   /api/products
PATCH  /api/products/{product_id}
DELETE /api/products/{product_id}?confirm=true
GET    /api/products/category/{category}
GET    /api/products/search?q={query}&category={optional}
GET    /api/products/{product_id}/price-history
POST   /api/products/{product_id}/add-price-point
POST   /api/products/{product_id}/recalculate-health-score
POST   /api/products/{product_id}/update-price
POST   /api/products/update-all-prices?limit=50
```

### Error Response Format
Domain exceptions are translated to structured JSON:
```json
{
  "detail": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "context": {}
  }
}
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_specific.py
```

## 📝 Development Notes

### Adding New Models

1. Create model in `app/models/`
2. Import in `app/db/base.py` to register with Base
3. Generate migration: `alembic revision --autogenerate -m "Add ModelName"`
4. Review and apply: `alembic upgrade head`

### Environment Variables

All configuration is managed through `app/core/config.py` using Pydantic Settings, which automatically loads from `.env` files.

## 🔒 Security

- Never commit `.env` files to version control
- Keep `SECRET_KEY` secure and unique
- Use environment-specific configurations for production
- Rotate API credentials regularly

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Kroger API Documentation](https://developer.kroger.com/)

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Write/update tests
4. Generate migrations if needed
5. Submit a pull request
