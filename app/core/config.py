'''
Docstring for app.core.config
Application config using Pydantic Settings 
Loading our env variables 
'''

from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings): 
    '''
        Application settings loaded from env vars
    '''

    #App Settings
    APP_NAME: str = "PriceOrbit API"
    VERSION: str = '1.0.0'
    DEBUG: bool = False
    PORT: int = 8080
    SECRET_KEY: str = "change-me-in-production"
    ENABLE_API_DOCS: bool = False
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    DEPLOY_ENV: str = "development"

    #Database Config
    DATABASE_URL: str 
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "priceorbit_db"

      # Kroger API Configuration
    KROGER_CLIENT_ID: str
    KROGER_CLIENT_SECRET: str
    KROGER_BASE_URL: str  = "https://api.kroger.com/v1"
    KROGER_AUTH_URL: str = "https://api.kroger.com/v1/connect/oauth2/token"
    KROGER_LOCATION_ID: str = "01400943"
    KROGER_MIN_MATCH_CONFIDENCE: float = 70.0
    KROGER_CERT_MIN_MATCH_CONFIDENCE: float = 55.0
    KROGER_ALIAS_MIN_MATCH_CONFIDENCE: float = 45.0
    KROGER_FALLBACK_MIN_SIMILARITY: float = 0.45
    KROGER_SKIP_UNMATCHED_RETRIES: bool = False
    KROGER_OVERRIDE_FILE: str = "data/kroger_product_overrides.json"
    KROGER_ALIAS_FILE: str = "data/kroger_search_aliases.json"
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]
    
    # Application Constants
    PRODUCTS_PER_PAGE: int = 20
    CACHE_TIMEOUT: int = 300  # 5 minutes

    # Admin access
    ADMIN_PIN: str = "3030"

    # Scheduler configuration
    PRICE_UPDATE_JOB_ENABLED: bool = True
    PRICE_UPDATE_CRON_HOUR_UTC: int = 6
    PRICE_UPDATE_BATCH_SIZE: int = 10
    PRICE_UPDATE_DELAY_SECONDS: float = 2.0
    PRICE_UPDATE_MAX_DAILY_CALLS: int = 500
    PRICE_UPDATE_RUN_ON_STARTUP_IF_STALE: bool = True
    PRICE_UPDATE_STALE_HOURS: int = 24
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Accept Render-style `postgres://` URLs by normalizing to SQLAlchemy dialect name."""
        if isinstance(value, str) and value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql://", 1)
        return value


# Create global settings instance
settings = Settings()
