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
  load without a single rejection, repair or area difference, and a second run of the same file
  writes nothing (`inserted 0, updated 0, unchanged 9143` for AI).
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
