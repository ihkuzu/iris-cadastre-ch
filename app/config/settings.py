"""Runtime settings, read from the environment or a .env file."""

import re
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_prefix="IRIS_", extra="ignore")

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

    @field_validator("table")
    @classmethod
    def _plain_name(cls, value: str) -> str:
        if not NAME.match(value):
            raise ValueError(f"table name {value!r} must be a plain lower-case identifier")
        return value

    @field_validator("sources_file", "data_dir", "log_dir")
    @classmethod
    def _from_root(cls, value: Path) -> Path:
        return value if value.is_absolute() else ROOT / value


@lru_cache
def get_settings() -> Settings:
    return Settings()
