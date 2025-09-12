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

    # Variables de GCP
    GOOGLE_CLOUD_PROJECT: str
    GOOGLE_CLOUD_LOCATION: str

    # Variables del Modelo Gemini
    GEMINI_MODEL: str
    MAX_OUTPUT_TOKENS: int = 16384
    TEMPERATURE: float = 0.7
    TOP_P: float = 0.9

    # Variables para el PSE
    PSE_API_KEY: str
    PSE_ID: str

settings = Settings()

log.info(f"Configuración cargada para el proyecto: {settings.GOOGLE_CLOUD_PROJECT} usando el modelo {settings.GEMINI_MODEL}")
