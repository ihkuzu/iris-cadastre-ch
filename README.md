# iris-cadastre-ch

Ingestion module for Swiss cadastral parcels (assignment IRIS-EU-CH-AV, task 143). It reads the
official cadastral survey (Amtliche Vermessung, AV) as published by the cantons on geodienste.ch,
checks every parcel, and loads it with its provenance into `iris_staging.cadastre_switzerland`
in PostGIS. It only ever writes to an isolated staging schema.

```
geodienste.ch GeoPackage ──> extract ──> map fields ──> check & normalise ──> load (upsert) ──> report
   (per canton, LV95)        layers,      DM.01 names    CRS, geometry,      iris_staging      quality
                             SHA-256      to one schema  keys, duplicates    + rejected rows   report
```

## Quick start (Docker)

```
cp .env.example .env
# Linux only, if your user id is not 1000: let the container user write the mounted folders
# mkdir -p data logs results && chmod a+w data logs results docs
docker compose up -d db                     # own PostGIS on 127.0.0.1:5434, nothing else
docker compose run --rm app init-db         # create schema and tables

# download one canton (or put the zip from geodienste.ch into data/raw/<KT>/ yourself)
docker compose run --rm app download AI
docker compose run --rm app inspect data/raw/AI/av_AI_gpkg_lv95.zip
docker compose run --rm app ingest AI --dry-run     # check only
docker compose run --rm app ingest AI
docker compose run --rm app report                  # docs/quality_report.md, results/
docker compose run --rm app validate                # exit code 1 if a check fails
```

Running `ingest` again on unchanged data changes no parcel content (`inserted 0, updated 0,
unchanged N`); it adds an entry to `ingestion_runs` and sets `last_seen_run_id`. A new export
with the same content is also unchanged, since the export date is not part of the record hash. `download` keeps a file that is
already there (geodienste.ch allows one download per dataset and day); `--force` fetches it again.

Updating an existing database after a schema change: `docker compose down -v` removes only this
project's PostGIS volume (`iris_cadastre_ch_pg`), then `up -d db` and `init-db` again.
The container runs as uid 1000 and writes to the bind-mounted `data/`, `logs/`, `results/` and
`docs/`; on Linux with another user id, use the `chmod` line above.

## Local run and tests

Python 3.11 or newer.

```
pip install -r requirements-dev.txt
pytest -q                                   # unit tests, no database needed
IRIS_TEST_DATABASE_URL=postgresql+psycopg://iris:iris@localhost:5434/iris_staging pytest -q   # plus database tests
ruff check . && ruff format --check .
alembic upgrade head                        # the same tables through a migration
```

The database tests create and drop their own schema `iris_staging_test`.

## Data provenance

- Source: geodienste.ch, offer "Amtliche Vermessung" version 24.0, model DM.01-AV-CH, LV95
  (EPSG:2056), GeoPackage per canton. Details and links: [docs/sources.md](docs/sources.md).
- Cantons: AI (Appenzell Innerrhoden), BS (Basel-Stadt), GE (Genève) and FR (Fribourg/Freiburg),
  all freely available with attribution. The cantons that need approval (JU, LU, NE, NW, OW, VD)
  are in the config as closed: `download` and the loader refuse them.
- Every row stores the source name, download URL, licence and terms URL, file name, SHA-256 of
  the file, layer, feature id, source CRS, the dataset date (`last_change` of the layer in the
  GeoPackage, the config value only as a fallback) and all original attributes.
- Every run is recorded in `ingestion_runs` with counts, rejection reasons and the field mapping.
- Attribution: data © the respective canton, via geodienste.ch.

## Schema mapping

| Column | From | Notes |
|---|---|---|
| `country` | constant | `CH` |
| `canton`, `canton_name` | configuration | two-letter code, checked against a canton attribute if present |
| `bfs_nr` | `resf.BFSNr` | else from the municipality layer `mbsf` by a point inside the parcel |
| `municipality` | `mbsf.Name` | point inside the parcel |
| `nbident` | `resf.NBIdent` (DM.01 `Grundstueck.NBIdent`) | numbering area, starts with the canton code |
| `parcel_number` | `resf.Nummer` | |
| `egrid` | `resf.EGRIS_EGRID` | national id `CH` + 12 characters, optional; one land register parcel each (see below) |
| `parcel_type` | configuration | `Liegenschaft`; the layer has no `Art` column |
| `completeness`, `validity` | `Vollstaendigkeit`, `Gueltigkeit` | as delivered |
| `area_source_m2` | `resf.Flaeche` | the legal area |
| `area_m2` | computed in LV95 | m², compared with `area_source_m2` |
| `geom` | `resf` geometry | MultiPolygon, EPSG:2056, arcs stroked, 1 mm precision |
| `geom_wgs84` | derived | MultiPolygon, EPSG:4326 |
| `geometry_repaired` | check | true when an invalid polygon was repaired |
| `source_*`, `licence*` | configuration and file | provenance, see above |
| `source_attributes` | all original columns | JSON, nothing is dropped |
| `record_hash`, `run_id`, `first_seen_at`, `updated_at` | ingestion | `run_id` is the run that last wrote the row |
| `last_seen_run_id` | ingestion | last run whose file still contained the parcel |

Key: `canton + nbident + parcel_number` (unique), as in DM.01-AV-CH. The geodienste.ch
GeoPackage is flat: the layer `resf` holds geometry and Grundstueck attributes together; `resfproj`
(projected) and `dprsf` (building rights) are skipped. Column names are matched in any spelling
(`EGRIS_EGRID`, `egris_egrid`, `egrid` ...), and for INTERLIS-shaped exports with separate
`Grundstueck` and `Liegenschaft` layers the two are joined.

## Checks and fault handling

| Problem | What happens |
|---|---|
| NBIdent or number missing | rejected: `missing_key` |
| EGRID not `CH` + 12 characters | rejected: `malformed_egrid` |
| no geometry, or not an area | rejected: `empty_geometry`, `not_polygon` |
| invalid polygon | repaired if the area changes by at most 1 %, else rejected: `invalid_geometry` |
| identical copy | stored once, the copy recorded as `exact_duplicate` |
| same key, several separate polygons, same attributes | merged into one MultiPolygon, areas summed (`multipart_parcel` warning) |
| same key, different content or overlapping parts | all copies held back: `conflicting_duplicate` |
| same EGRID on two land register parcels | `duplicate_egrid`, or `egrid_already_stored` across runs; in cantons with `egrid_parts = true` (Fribourg) the numbered parts `<article>.<nn>` of one parcel may share it |
| canton attribute differs | rejected: `canton_mismatch` |
| CRS missing | taken from the configuration, logged |
| LV03 data | reprojected to LV95, logged |
| any other CRS | the file is refused |
| polygon empty after rounding to 1 mm | rejected: `empty_geometry` |
| parcel stored before but missing in the new file | kept, counted in `ingestion_runs.not_in_source` and logged |
| server returns an order page instead of a zip | `download` stops, nothing is kept |
| database error during load | transaction rolled back, run marked `failed` with the error |
| schema not `iris_staging*`, closed licence, synthetic data in the main schema | refused before writing |

Rejected features are stored in `rejected_records` with the reason, their attributes and WKT,
so nothing is silently dropped. Logs go to the console and, one JSON line per event with run id,
canton and file, to `logs/ingest.jsonl`.

## Result and quality report

`python main.py report` builds [docs/quality_report.md](docs/quality_report.md) and
`results/summary.json` and `results/sample_parcels.csv` from the database: coverage per canton,
integrity checks, rejected records by reason, runs and sample rows. `sql/validation.sql` holds the
acceptance checks (valid geometries, SRIDs, unique keys, one parcel per EGRID, provenance,
location). `sql/examples.sql` has example queries (parcel under a point, coverage per
municipality) and the queries behind the findings in the quality report:
`docker compose exec -T db psql -U iris -d iris_staging < sql/examples.sql`.

Result of the run on 2026-10-28 (files in `docs/` and `results/`):

| Canton | Parcels | Municipalities | Rejected | Area differs from `Flaeche` |
|---|---|---|---|---|
| AI Appenzell Innerrhoden | 9,143 | 5 | 0 | 0 |
| BS Basel-Stadt | 24,426 | 3 | 0 | 0 |
| FR Fribourg | 168,506 | 120 | 4 | 17,699 |
| GE Genève | 73,111 | 45 | 0 | 0 |

All validation checks pass; the Fribourg findings are explained in the quality report.

## Assumptions and limitations

See the end of the [quality report](docs/quality_report.md) and [docs/report_notes.md](docs/report_notes.md).
In short: configured cantons only, no INTERLIS reader (the GeoPackage of the same data is used),
building rights and projected parcels out of scope, DMAV migration of the cantons by 2027 will
need a mapping update.

## Test data

All test data is synthetic and generated in `tests/fixtures.py`: canton code `XX`, EGRIDs
starting `CH9999`, the note `SYNTHETIC test fixture`. `tests/data/synthetic_geodienste.gpkg`
copies the flat layout of the geodienste.ch GeoPackage (`resf`, `resfproj`, `dprsf`, `mbsf`) for
the container test in CI; it is rebuilt with `fixtures.geodienste(path, parts=True)`.
`tests/data/synthetic_arc.gpkg` holds one polygon with an arc. None of it is presented as
cadastre data, and the loader refuses to put it into the main staging schema.

## Layout

```
app/extractors   read files, pick layers, hash        app/loaders     upsert, runs, rejections
app/parsers      column name mapping                   app/reports     quality report
app/transformers checks, CRS, geometry, duplicates     app/runners     command line
app/database     tables, staging guard                 config/         sources and licences
alembic/         migration                             sql/            validation queries
```

## Licence

Code: MIT. Data: © the cantons, under their terms via geodienste.ch; not included in this
repository.
