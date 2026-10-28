import os
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.config.sources import Source


@pytest.fixture
def settings(tmp_path):
    return Settings(
        db_schema="iris_staging_test",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        database_url=os.environ.get("IRIS_TEST_DATABASE_URL", "postgresql+psycopg://x@nowhere/x"),
    )


@pytest.fixture
def source():
    return Source(
        canton="XX",
        name="SYNTHETIC test fixture",
        url="file://tests/fixtures.py",
        licence="none, synthetic",
        licence_url="file://tests/fixtures.py",
        access="open",
        dataset_date="2026-10-01",
    )


@pytest.fixture
def db_url():
    url = os.environ.get("IRIS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set IRIS_TEST_DATABASE_URL to a PostGIS database to run database tests")
    return url


@pytest.fixture
def tmp_gpkg(tmp_path) -> Path:
    return tmp_path / "fixture.gpkg"
