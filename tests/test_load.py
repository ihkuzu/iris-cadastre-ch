import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config.sources import Source
from app.database.guard import StagingGuardError, check_schema
from app.database.session import engine
from app.extractors import av_file
from app.loaders.parcels import load
from app.reports import quality
from app.runners.cli import main
from app.transformers.parcels import transform
from tests import fixtures

SCHEMA = "iris_staging_test"


@pytest.fixture
def eng(db_url):
    e = engine(db_url)
    with e.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
    yield e
    e.dispose()


def ingest(eng, path, settings, source, layer=None):
    extract = av_file.read(path, layer=layer)
    return load(eng, SCHEMA, "cadastre_switzerland", transform(extract, source, settings), extract, source)


def count(eng, sql):
    with eng.connect() as conn:
        return conn.execute(text(sql.replace("S.", f"{SCHEMA}."))).scalar()


def test_schema_guard():
    assert check_schema("iris_staging") == "iris_staging"
    for bad in ("iris_core", "public", "iris_staging;drop", "staging"):
        with pytest.raises(StagingGuardError):
            check_schema(bad)


def test_refuses_iris_core_synthetic_main_and_closed_sources(eng, tmp_gpkg, settings, source):
    fixtures.write(tmp_gpkg, fixtures.parcels(2))
    extract = av_file.read(tmp_gpkg)
    result = transform(extract, source, settings)
    with pytest.raises(StagingGuardError):
        load(eng, "iris_core", "cadastre_switzerland", result, extract, source)
    with pytest.raises(StagingGuardError, match="synthetic"):
        load(eng, "iris_staging", "cadastre_switzerland", result, extract, source)
    closed = Source(**{**source.__dict__, "canton": "ZH", "access": "registration"})
    with pytest.raises(StagingGuardError, match="not open"):
        load(eng, SCHEMA, "cadastre_switzerland", result, extract, closed)


def test_second_run_changes_nothing_and_a_change_updates_one_row(eng, tmp_gpkg, settings, source):
    fixtures.write(tmp_gpkg, fixtures.parcels(12))
    first = ingest(eng, tmp_gpkg, settings, source)
    assert (first.inserted, first.updated, first.unchanged) == (12, 0, 0)
    second = ingest(eng, tmp_gpkg, settings, source)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 12)
    rows = fixtures.parcels(12)
    rows[3]["geometry"] = fixtures.square(3, size=25)
    changed = tmp_gpkg.with_name("changed.gpkg")
    fixtures.write(changed, rows)
    third = ingest(eng, changed, settings, source)
    assert (third.inserted, third.updated, third.unchanged) == (0, 1, 11)
    assert count(eng, "SELECT area_m2 FROM S.cadastre_switzerland WHERE parcel_number = '103'") == 625
    assert count(eng, "SELECT count(*) FROM S.ingestion_runs WHERE status = 'succeeded'") == 3
    assert count(eng, "SELECT count(DISTINCT source_sha256) FROM S.ingestion_runs") == 2


def test_rejections_are_stored_not_dropped(eng, tmp_gpkg, settings, source):
    fixtures.write(tmp_gpkg, fixtures.broken())
    stats = ingest(eng, tmp_gpkg, settings, source, layer="Liegenschaften_Liegenschaft")
    assert stats.inserted == 2 and stats.rejected == 10
    assert count(eng, "SELECT count(*) FROM S.rejected_records") == 10
    assert (
        count(
            eng,
            "SELECT count(*) FROM S.rejected_records"
            " WHERE reason = 'invalid_geometry' AND geometry_wkt LIKE 'POLYGON%'",
        )
        == 1
    )
    assert count(eng, "SELECT (details->'reasons'->>'conflicting_duplicate')::int FROM S.ingestion_runs") == 2


def test_egrid_stored_under_another_key_is_rejected(eng, tmp_gpkg, settings, source):
    fixtures.write(tmp_gpkg, fixtures.parcels(2))
    ingest(eng, tmp_gpkg, settings, source)
    rows = fixtures.parcels(2)
    rows[1]["Nummer"] = "999"
    other = tmp_gpkg.with_name("other.gpkg")
    fixtures.write(other, rows)
    stats = ingest(eng, other, settings, source)
    assert stats.rejected == 1 and stats.unchanged == 1
    assert count(eng, "SELECT reason FROM S.rejected_records") == "egrid_already_stored"


def test_failed_run_is_recorded_and_leaves_no_rows(eng, tmp_gpkg, settings, source, monkeypatch):
    fixtures.write(tmp_gpkg, fixtures.parcels(3))
    extract = av_file.read(tmp_gpkg)
    result = transform(extract, source, settings)
    result.rows[1]["egrid"] = "not an egrid"  # violates the database check
    with pytest.raises(IntegrityError):
        load(eng, SCHEMA, "cadastre_switzerland", result, extract, source)
    assert count(eng, "SELECT count(*) FROM S.cadastre_switzerland") == 0
    assert count(eng, "SELECT status FROM S.ingestion_runs") == "failed"


def test_report_and_validation(eng, db_url, tmp_gpkg, tmp_path, settings, source, monkeypatch, capsys):
    fixtures.write(tmp_gpkg, fixtures.broken())
    ingest(eng, tmp_gpkg, settings, source, layer="Liegenschaften_Liegenschaft")
    data = quality.gather(eng, SCHEMA, "cadastre_switzerland")
    assert data["by_canton"][0]["parcels"] == 2 and all(v == 0 for v in data["checks"][0].values())
    quality.write(data, tmp_path / "report.md", tmp_path / "results")
    report = (tmp_path / "report.md").read_text()
    assert "All checks pass" in report and "conflicting_duplicate" in report
    assert (tmp_path / "results" / "sample_parcels.csv").exists()
    monkeypatch.setenv("IRIS_DATABASE_URL", db_url)
    monkeypatch.setenv("IRIS_DB_SCHEMA", SCHEMA)
    monkeypatch.setenv("IRIS_LOG_DIR", str(tmp_path / "logs"))
    from app.config.settings import get_settings

    get_settings.cache_clear()
    assert main(["validate"]) == 0
    assert "FAIL" not in capsys.readouterr().out
    get_settings.cache_clear()


def test_parcel_missing_from_a_new_file_is_counted_not_deleted(eng, tmp_gpkg, tmp_path, settings, source):
    fixtures.write(tmp_gpkg, fixtures.parcels(5))
    ingest(eng, tmp_gpkg, settings, source, layer="Liegenschaften_Liegenschaft")
    smaller = fixtures.write(tmp_path / "smaller.gpkg", fixtures.parcels(4))
    stats = ingest(eng, smaller, settings, source, layer="Liegenschaften_Liegenschaft")
    assert (stats.unchanged, stats.not_in_source) == (4, 1)
    assert count(eng, "SELECT count(*) FROM S.cadastre_switzerland") == 5
    assert count(eng, "SELECT not_in_source FROM S.ingestion_runs ORDER BY started_at DESC LIMIT 1") == 1
