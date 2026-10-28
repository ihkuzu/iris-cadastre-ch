## Assumptions

- Source: geodienste.ch GeoPackage exports of the official cadastral survey (DM.01-AV-CH, version
  24.0), downloaded once and kept in `data/raw` with their SHA-256. Only cantons marked as freely
  available are ingested; the licence and terms URL are stored on every row.
- One row is one Liegenschaft (real estate parcel). Building rights and other SelbstRechte, and
  projected parcels (`Proj*` layers) that are not yet legally valid, are out of scope.
- The parcel key is canton + NBIdent + parcel number, as in the model. The EGRID is stored and
  must be unique, but may be missing.
- Geometry is stored in LV95 (EPSG:2056) as delivered. Arcs are stroked into straight segments by
  GDAL when reading. `geom_wgs84` is a derived copy for web maps (pyproj, Swiss transformation
  without height); the LV95 column is the reference.
- Areas are computed in LV95 in square metres. A difference to the stored `Flaechenmass` above
  1 m² and 0.5 % is reported, not corrected: the stored value is the legal one.
- Municipality (BFS number and name) comes from the municipality boundary layer of the same
  export, by a point inside each parcel.

## Known gaps

- Coverage is the configured cantons, not all of Switzerland. Cantons that require approval
  (JU, LU, NE, NW, OW, VD) are deliberately not ingested.
- INTERLIS (.itf/.xtf) is not read directly; the GeoPackage export of the same data is used.
- Each canton switches to the new model DMAV by the end of 2027; the column mapping will need
  an update then.
- An invalid polygon is repaired only if the area changes by at most 1 %; otherwise it is held
  back in `rejected_records` with its WKT, for a person to look at.
