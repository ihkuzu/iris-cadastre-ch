# Acceptance checklist

Every requirement from the assignment (TASK 143, IRIS-EU-CH-AV) and the invitation email, and
where it is met. "Evidence" points to a file, a test or a command whose output can be checked.

## Implementation scope

| Requirement | How it is met | Evidence |
|---|---|---|
| Task-specific workflow with documented source data, stable identifiers and reproducible inputs or fixtures | One configured source per canton (`config/sources.toml`) with URL, licence and access date; the downloaded file's SHA-256 is stored with every run; the natural key is canton + NBIdent + parcel number, EGRID is kept and checked to belong to one land register parcel | `config/sources.toml`, table `ingestion_runs`, `tests/test_transform.py` |
| Resolve lawful access, canton/parcel references, source CRS and projected geometry with provenance | Only sources marked open in the config are ingested; each row carries canton, NBIdent, number, EGRID, BFS number, source CRS, licence, source URL and file hash; geometry kept in LV95 (EPSG:2056) with a WGS84 copy | README "Data provenance", columns of `cadastre_switzerland` |
| Normalise fields, timestamps, units and spatial metadata; repeatable staging-only ingestion without data loss | Canonical column names, UTC timestamps, areas in m², every original attribute kept in `source_attributes`; re-running the same file changes nothing; rejected rows are stored with a reason instead of being dropped; writes are refused outside an `iris_staging*` schema | `tests/test_load.py::test_second_run_changes_nothing`, `tests/test_load.py::test_refuses_iris_core` |
| Source-aware logging, fault handling and tests for missing, malformed or duplicate records | Logs carry run id, canton and file; reason codes for every rejection; tests for missing keys, invalid and empty geometry, wrong CRS, exact and conflicting duplicates | `tests/test_transform.py`, `logs/` |
| Representative validated result and concise quality report on coverage, assumptions and known gaps | `python main.py report` writes the report from the database; validation SQL checks keys, SRID, validity and areas | `docs/quality_report.md`, `sql/validation.sql`, `results/` |

## What to submit

| Requirement | Where |
|---|---|
| Python 3.11+ source code | `app/`, `main.py` |
| Pinned dependencies | `requirements.txt` (exact versions) |
| Example configuration, no secrets | `config/sources.toml`, `.env.example` |
| Dockerfile and docker-compose.yml | `Dockerfile`, `docker-compose.yml` |
| README: provenance, run instructions, schema mapping, assumptions, limitations | `README.md` |
| Automated tests with fixture or mocked data | `tests/`, synthetic fixtures labelled `SYNTHETIC` |
| Example result or validation query | `sql/validation.sql`, `results/` |
| Short quality and error report | `docs/quality_report.md` |

## Acceptance criteria

| Criterion | How it is met |
|---|---|
| No invented polygons passed off as live cadastre | Test fixtures are generated in code, use the canton code `XX`, EGRIDs starting `CH9999` and the source name `SYNTHETIC test fixture`; the loader refuses synthetic sources unless the target is a test schema |
| Preserve canton and national metadata | `canton`, `bfs_nr`, `municipality`, `nbident`, `egrid` and `country = 'CH'` on every row |
| Deterministic or auditable method with clear evidence | Rows are processed in key order; a record hash decides updates; each run stores file hash, counts and reasons |

## From the email

| Requirement | Where |
|---|---|
| Reproducible implementation | Docker Compose, pinned dependencies, file hashes |
| Docker configuration | `Dockerfile`, `docker-compose.yml` |
| Brief README with run and test instructions | `README.md` |
| Automated checks | `pytest`, `ruff`, GitHub Actions |
| Summary of limitations and assumptions | README and quality report |
| Isolated staging only, never `iris_core` or production | Own PostGIS in Docker; schema guard in `app/database/guard.py` |
