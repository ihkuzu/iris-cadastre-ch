from pathlib import Path

import pytest

from app.config.settings import get_settings
from app.config.sources import load_sources
from app.runners.cli import main
from tests import fixtures

CONFIG = """
[source.XX]
name = "SYNTHETIC test fixture"
url = "file://tests/fixtures.py"
file = "fixture.gpkg"
licence = "none, synthetic"
licence_url = "file://tests/fixtures.py"
access = "open"
dataset_date = "2026-10-01"

[source.VD]
name = "closed"
url = "https://example.invalid"
licence = "approval required"
licence_url = "https://example.invalid"
access = "approval-required"
"""


@pytest.fixture
def env(tmp_path, monkeypatch):
    (tmp_path / "sources.toml").write_text(CONFIG)
    data = tmp_path / "data"
    (data / "raw" / "XX").mkdir(parents=True)
    fixtures.write(data / "raw" / "XX" / "fixture.gpkg", fixtures.broken())
    monkeypatch.setenv("IRIS_SOURCES_FILE", str(tmp_path / "sources.toml"))
    monkeypatch.setenv("IRIS_DATA_DIR", str(data))
    monkeypatch.setenv("IRIS_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("IRIS_DB_SCHEMA", "iris_staging_test")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_shipped_config_is_valid_and_only_open_sources_are_lawful():
    sources = load_sources(Path(__file__).parents[1] / "config" / "sources.toml")
    assert {"AI", "BS", "GE", "FR"} <= set(sources)
    assert all(s.lawful for c, s in sources.items() if c != "VD") and not sources["VD"].lawful
    assert all(s.licence and s.licence_url.startswith("https://") for s in sources.values())


def test_inspect_lists_layers_and_recognised_columns(env, capsys):
    assert main(["inspect", str(env / "data" / "raw" / "XX" / "fixture.gpkg")]) == 0
    out = capsys.readouterr().out
    assert "Liegenschaften_Liegenschaft" in out and '"egrid": "EGRIS_EGRID"' in out


def test_dry_run_writes_nothing_and_closed_sources_are_refused(env, capsys):
    assert main(["ingest", "XX", "--dry-run", "--layer", "Liegenschaften_Liegenschaft"]) == 0
    assert '"accepted": 2' in capsys.readouterr().out
    assert main(["download", "VD"]) == 2
    assert main(["ingest", "ZZ"]) == 2


def test_ingest_report_validate_end_to_end(env, db_url, monkeypatch, capsys):
    monkeypatch.setenv("IRIS_DATABASE_URL", db_url)
    get_settings.cache_clear()
    from sqlalchemy import create_engine, text

    with create_engine(db_url).begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS iris_staging_test CASCADE"))
    assert main(["ingest", "XX", "--layer", "Liegenschaften_Liegenschaft"]) == 0
    assert "inserted 2" in capsys.readouterr().out
    report, results = env / "report.md", env / "results"
    assert main(["report", "--out", str(report), "--results", str(results)]) == 0
    assert "All checks pass" in report.read_text() and (results / "summary.json").exists()
    assert main(["validate"]) == 0
