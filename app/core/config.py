'''
Docstring for app.core.config
Application config using Pydantic Settings 
Loading our env variables 
'''

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings): 
    '''
        Application settings loaded from env vars
    '''

    #App Settings
    APP_NAME: str = "PriceOrbit API"
    VERSION: str = '1.0.0'
    DEBUG: bool = True
    PORT: int = 8080 
    SECRET_KEY: str = "" 

    #Database Config
    DATABASE_URL: str 
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str = "priceorbit_db"

      # Kroger API Configuration
    KROGER_CLIENT_ID: str
    KROGER_CLIENT_SECRET: str
    KROGER_BASE_URL: str = "https://api.kroger.com/v1"
    KROGER_AUTH_URL: str = "https://api.kroger.com/v1/connect/oauth2/token"
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]
    
    # Application Constants
    PRODUCTS_PER_PAGE: int = 20
    CACHE_TIMEOUT: int = 300  # 5 minutes
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )


# Create global settings instance
settings = Settings()





