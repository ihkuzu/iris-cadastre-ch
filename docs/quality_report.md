# Quality report: Swiss cadastre (AV) ingestion

Generated 2026-10-28T19:59:49+00:00 from the staging tables.

## Coverage by canton

| canton | canton_name | parcels | municipalities | with_egrid | without_municipality | repaired | area_mismatch | area_km2 | dataset_date | source_crs | licence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AI | Appenzell Innerrhoden | 9143 | 5 | 9143 | 0 | 0 | 0 | 172.48 | 2026-10-28 | EPSG:2056 | Frei erhältlich, Quellenangabe Pflicht (geodienste.ch terms of use and cantonal terms) |
| BS | Basel-Stadt | 24426 | 3 | 24426 | 0 | 0 | 0 | 36.95 | 2026-10-24 | EPSG:2056 | Frei erhältlich, Quellenangabe Pflicht (geodienste.ch terms of use and cantonal terms) |
| FR | Fribourg | 168506 | 120 | 168281 | 0 | 0 | 17699 | 1672.19 | 2026-10-28 | EPSG:2056 | Freie Nutzung, Quellenangabe Pflicht (geodienste.ch terms of use and cantonal terms) |
| GE | Genève | 73111 | 45 | 73111 | 0 | 0 | 0 | 282.49 | 2026-10-03 | EPSG:2056 | Freie Nutzung, Quellenangabe Pflicht; SITG conditions d'utilisation |

## Integrity checks

All checks pass.

| invalid_geometries | wrong_srid | empty_geometries | duplicate_keys | egrids_on_two_parcels | wrong_country |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 |

## Rejected records (latest successful run per canton)

| canton | reason | n | meaning |
|---|---|---|---|
| FR | conflicting_duplicate | 2 | same parcel key with different content, all copies held back |
| FR | duplicate_egrid | 2 | same EGRID on different land register parcels in one file |

## Warnings (latest successful run per canton; rows are stored)

| canton | warning | n | meaning |
|---|---|---|---|
| FR | area_differs_from_source | 17699 | computed area differs from Flaeche by more than the tolerance |
| FR | egrid_shared_by_parts | 1605 | numbered part <article>.<nn> sharing the EGRID of its parcel |
| FR | multipart_parcel | 4 | several polygons of one parcel merged into one MultiPolygon |

## Runs (times in UTC)

| started | canton | source_file | sha256 | status | read | accepted | inserted | updated | unchanged | rejected | merged | repaired | not_in_source |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-28 19:58 | FR | av_FR_gpkg_lv95.zip | 7030dd266e39 | succeeded | 168520 | 168506 | 0 | 0 | 168506 | 4 | 10 | 0 | 0 |
| 2026-10-28 16:52 | FR | av_FR_gpkg_lv95.zip | 7030dd266e39 | succeeded | 168520 | 168506 | 0 | 0 | 168506 | 4 | 10 | 0 | 0 |
| 2026-10-28 16:49 | FR | av_FR_gpkg_lv95.zip | 7030dd266e39 | succeeded | 168520 | 168506 | 168506 | 0 | 0 | 4 | 10 | 0 | 0 |
| 2026-10-28 16:47 | GE | av_GE_gpkg_lv95.zip | 2d79b08bccc7 | succeeded | 73111 | 73111 | 73111 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-28 16:46 | BS | av_BS_gpkg_lv95.zip | 5c9602a619d6 | succeeded | 24426 | 24426 | 24426 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2026-10-28 16:46 | AI | av_AI_gpkg_lv95.zip | a94e14aed24d | succeeded | 9143 | 9143 | 9143 | 0 | 0 | 0 | 0 | 0 | 0 |

## Sample rows

| canton | bfs_nr | municipality | nbident | parcel_number | egrid | area_m2 | lon | lat |
|---|---|---|---|---|---|---|---|---|
| AI | 3102 | Gonten | AI02003102 | 412 | CH595977054157 | 12880.26 | 9.381817 | 47.341074 |
| AI | 3112 | Schwende-Rüte | AI02003103 | 2070 | CH995977594150 | 555.81 | 9.417465 | 47.329493 |
| AI | 3104 | Schlatt-Haslen | AI02003104 | 877 | CH367702107919 | 899.94 | 9.412721 | 47.362384 |
| AI | 3112 | Schwende-Rüte | AI02003105 | 711 | CH167759413807 | 168.38 | 9.433694 | 47.305269 |
| AI | 3111 | Oberegg | AI02003111 | 1093 | CH541799778868 | 2421.28 | 9.569568 | 47.429346 |
| BS | 2701 | Basel | BSS100000000 | 0973 | CH876778858989 | 526.76 | 7.578188 | 47.560827 |
| BS | 2701 | Basel | BSS200000000 | 9056 | CH567989671673 | 2016.63 | 7.564042 | 47.554448 |
| BS | 2701 | Basel | BSS300000000 | 1539 | CH576778688948 | 186.49 | 7.585352 | 47.542896 |
| BS | 2701 | Basel | BSS500000000 | 1826 | CH127954896752 | 296.31 | 7.608795 | 47.546360 |
| BS | 2701 | Basel | BSS700000000 | 0541 | CH907067888949 | 3838.18 | 7.597322 | 47.571502 |
| FR | 2041 | Saint-Aubin (FR) | FR204111 | 506 | CH749410972682 | 10883.46 | 6.971862 | 46.901577 |
| FR | 2125 | Bulle | FR212511 | 6141 | CH783010948875 | 6.00 | 7.066091 | 46.611301 |
| FR | 2129 | Corbières | FR212911 | 3105 | CH538573014084 | 200.10 | 7.107417 | 46.645113 |
| FR | 2121 | Haut-Intyamon | FR214212 | 470b | CH749410897260 | 3182.33 | 7.015200 | 46.467601 |
| FR | 2309 | Wünnewil-Flamatt | FR230911 | 1625 | CH649410827119 | 481.58 | 7.274330 | 46.874503 |
| GE | 6612 | Chêne-Bougeries | GE0100000012 | 1524 | CH916367658239 | 2311.31 | 6.194270 | 46.203354 |
| GE | 6616 | Collonge-Bellerive | GE0100000016 | 7013 | CH508063136506 | 1022.10 | 6.209403 | 46.244824 |
| GE | 6621 | Genève | GE0100000021 | 6367 | CH136582635887 | 73.97 | 6.132939 | 46.206558 |
| GE | 6633 | Plan-les-Ouates | GE0100000036 | 7120 | CH529752656309 | 118.51 | 6.117497 | 46.168542 |
| GE | 6634 | Pregny-Chambésy | GE0100000037 | 766 | CH168265639583 | 1211.40 | 6.132078 | 46.242925 |

## Assumptions

- Source: geodienste.ch GeoPackage exports of the official cadastral survey (DM.01-AV-CH, version
  24.0), downloaded once and kept in `data/raw` with their SHA-256. Only cantons marked as freely
  available are ingested; the licence and terms URL are stored on every row.
- One row is one Liegenschaft (real estate parcel). Building rights and other SelbstRechte, and
  projected parcels (`Proj*` layers) that are not yet legally valid, are out of scope.
- The parcel key is canton + NBIdent + parcel number, as in the model. The EGRID is stored and
  may be missing. It identifies the land register parcel: in Fribourg one parcel is delivered as
  several numbered parts `<article>.<nn>` (for example `2007.03101`, `2007.03102`) that share its
  EGRID. Each part is kept as its own row; an EGRID on two different parcels is rejected.
- Geometry is stored in LV95 (EPSG:2056) as delivered. Arcs are stroked into straight segments by
  GDAL when reading. `geom_wgs84` is a derived copy for web maps (pyproj, Swiss transformation
  without height); the LV95 column is the reference.
- Areas are computed in LV95 in square metres. A difference to the stated area (`Flaeche`) above
  1 m² and 0.5 % is reported, not corrected: the stored value is the legal one.
- Municipality: the BFS number is on every `resf` row; the name comes from the municipality
  boundary layer `mbsf` of the same export, by a point inside each parcel.
- A parcel stored as several separate polygons with the same key and attributes is one parcel
  and is stored as one MultiPolygon with the summed area.
- `source_dataset_date` is the layer's `last_change` in the GeoPackage, which is the export date
  of geodienste.ch, not the date of the last field survey.
- Timestamps are stored in UTC; a source date or time without a zone is taken as UTC.
- An unchanged parcel keeps the provenance (file, hash, run) of the run that last wrote it; a new
  run only updates `last_seen_run_id`. Parcels missing from a newer file are counted, not deleted.

## Findings from the real data (run of 2026-10-28)

- 275,186 parcels from four cantons are in staging; every integrity check passes. AI, BS and GE
  load without a single rejection, repair or area difference. A second run of the same file
  changes nothing (`inserted 0, updated 0, unchanged 168506` for FR, the largest canton).
- Fribourg: 168,520 features = 168,506 stored rows + 4 held back (below) + 10 merged. The 10
  are extra polygons of 4 parcels that the source splits into separate features with one key;
  each of the 4 is stored once as a MultiPolygon (`multipart_parcel`, `merged_parts` in the run).
- Fribourg delivers one land register parcel as numbered parts `<article>.<nn>` that share the
  parcel's EGRID: 1,605 parts, 2 to 11 per EGRID, always within one NBIdent and article number.
  An earlier version of the rule rejected these as duplicate EGRIDs; FR is now configured with
  `egrid_parts = true`, which accepts parts of the same article. Other cantons keep the strict rule.
- Fribourg: EGRID `CH349410860776` is on two different parcels of `FR213812` (municipality 2138),
  numbers `1356` (1,121 m²) and `1817` (430 m²). An EGRID identifies exactly one parcel, so both
  features are held back as `duplicate_egrid` instead of picking one.
- Fribourg: parcel `FR213812/1058a` comes twice, in municipalities 2138 and 2163, with different
  geometry and stated area (10,434 m² and 225,600 m²). Both copies are held back as
  `conflicting_duplicate` for a person to resolve; they are not guessed.
- Fribourg: 17,699 parcels (about one in ten) have a computed area that differs from the stated
  area (`Flaeche`) by more than 1 m² and 0.5 %. Most differences are below 5 %; a few dozen are much
  larger, on single polygons with or without holes. The stated area is the legal value of the
  land register and is often not recomputed from the survey geometry where an older survey was
  digitised, which is the likely cause. Both values are stored, the difference is reported and
  nothing is corrected. `sql/examples.sql` (queries 7 to 9) lists them; the output of the real
  run is in `results/examples_output.txt`.
- The two earlier FR runs in `results/summary.json` count 17,704 area differences; they were made
  before the count was switched to exact decimals, like the report SQL. The final run on the same
  file counts 17,699, the same as the coverage table.
- 225 Fribourg parcels have no EGRID; they are stored, the EGRID is optional in the model.
- All parcels are `vollstaendig` and `rechtskraeftig`; the source has no incomplete or pending
  parcels in the `resf` layer.

## Known gaps

- An update replaces the stored row (geometry and attributes); earlier versions are not kept in a
  history table. Each run's file hash in `ingestion_runs` and the kept source files allow an
  earlier state to be rebuilt.
- Coverage is the configured cantons, not all of Switzerland. Cantons that require approval
  (JU, LU, NE, NW, OW, VD) are deliberately not ingested.
- INTERLIS (.itf/.xtf) is not read directly; the GeoPackage export of the same data is used.
- Each canton switches to the new model DMAV by the end of 2027; the column mapping will need
  an update then.
- An invalid polygon is repaired only if the area changes by at most 1 %; otherwise it is held
  back in `rejected_records` with its WKT, for a person to look at.
- LV03 input is reprojected with the standard pyproj transformation, which is accurate to about a
  metre, not with the official FINELTRA grid; for legal accuracy use LV95 sources (all
  geodienste.ch exports are LV95).
- `geom_wgs84` is for display; its accuracy is limited by the datum shift and is not cadastral.
