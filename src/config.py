# src/config.py
import logging
import google.cloud.logging
from pydantic_settings import BaseSettings, SettingsConfigDict

client = google.cloud.logging.Client()
client.setup_logging()
log = logging.getLogger("pida-backend")
log.setLevel(logging.INFO)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    GOOGLE_CLOUD_PROJECT: str
    GOOGLE_CLOUD_LOCATION: str
    GEMINI_MODEL: str
    PSE_API_KEY: str
    PSE_ID: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

settings = Settings()
