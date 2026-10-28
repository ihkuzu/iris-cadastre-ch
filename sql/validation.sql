-- Each check returns the number of offending rows; a check passes when that number is 0.
SELECT 'table is not empty' AS check_name, CASE WHEN EXISTS (SELECT 1 FROM iris_staging.cadastre_switzerland)
       THEN 0 ELSE 1 END AS found, EXISTS (SELECT 1 FROM iris_staging.cadastre_switzerland) AS passed
UNION ALL
SELECT 'geometries are valid', count(*), count(*) = 0
  FROM iris_staging.cadastre_switzerland WHERE NOT ST_IsValid(geom)
UNION ALL
SELECT 'geometries are LV95 and WGS84', count(*), count(*) = 0
  FROM iris_staging.cadastre_switzerland WHERE ST_SRID(geom) <> 2056 OR ST_SRID(geom_wgs84) <> 4326
UNION ALL
SELECT 'areas are positive and match the geometry', count(*), count(*) = 0
  FROM iris_staging.cadastre_switzerland WHERE area_m2 <= 0 OR abs(ST_Area(geom) - area_m2) > 0.01
UNION ALL
SELECT 'parcel keys are unique', count(*) - count(DISTINCT (canton, nbident, parcel_number)),
       count(*) = count(DISTINCT (canton, nbident, parcel_number))
  FROM iris_staging.cadastre_switzerland
UNION ALL
SELECT 'EGRIDs are well formed', count(*), count(*) = 0
  FROM iris_staging.cadastre_switzerland WHERE egrid !~ '^CH[0-9A-Z]{12}$'
UNION ALL
-- an EGRID belongs to one land register parcel; in cantons with egrid_parts its parts <article>.<nn> share it
-- :parts is the list of those cantons from config/sources.toml, passed in by `main.py validate`
SELECT 'each EGRID belongs to one parcel', count(*), count(*) = 0
  FROM (SELECT egrid FROM iris_staging.cadastre_switzerland WHERE egrid IS NOT NULL GROUP BY egrid
        HAVING count(DISTINCT (canton, nbident, CASE WHEN canton = ANY(CAST(:parts AS text[])) THEN split_part(parcel_number, '.', 1) ELSE parcel_number END)) > 1) e
UNION ALL
SELECT 'canton and country set', count(*), count(*) = 0
  FROM iris_staging.cadastre_switzerland WHERE canton IS NULL OR country <> 'CH'
UNION ALL
SELECT 'provenance complete', count(*), count(*) = 0
  FROM iris_staging.cadastre_switzerland
 WHERE source_url = '' OR licence = '' OR source_sha256 !~ '^[0-9a-f]{64}$' OR source_crs = ''
UNION ALL
SELECT 'WGS84 copy lies in Switzerland', count(*), count(*) = 0
  FROM iris_staging.cadastre_switzerland
 WHERE NOT ST_Intersects(ST_PointOnSurface(geom_wgs84), ST_MakeEnvelope(5.9, 45.8, 10.5, 47.9, 4326));
