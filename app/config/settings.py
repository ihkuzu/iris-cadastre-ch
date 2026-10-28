"""Runtime settings, read from the environment or a .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="IRIS_", extra="ignore")

    database_url: str = "postgresql+psycopg://iris:iris@localhost:5434/iris_staging"
    db_schema: str = "iris_staging"
    table: str = "cadastre_switzerland"
    sources_file: Path = Path("config/sources.toml")
    data_dir: Path = Path("data")
    log_dir: Path = Path("logs")
    # repaired geometries may differ from the source by at most this share of their area
    repair_tolerance: float = 0.01
    # allowed difference between the stored area (Flaechenmass) and the computed one
    area_tolerance_m2: float = 1.0
    area_tolerance_share: float = 0.005


@lru_cache
def get_settings() -> Settings:
    return Settings()
