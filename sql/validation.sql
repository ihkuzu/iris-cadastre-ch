-- Each check returns the number of offending rows; a check passes when that number is 0.
SELECT 'geometries are valid' AS check_name, count(*) AS found, count(*) = 0 AS passed
  FROM iris_staging.cadastre_switzerland WHERE NOT ST_IsValid(geom)
UNION ALL
SELECT 'geometries are LV95 and WGS84', count(*), count(*) = 0
  FROM iris_staging.cadastre_switzerland WHERE ST_SRID(geom) <> 2056 OR ST_SRID(geom_wgs84) <> 4326
UNION ALL
SELECT 'parcel keys are unique', count(*) - count(DISTINCT (canton, nbident, parcel_number)),
       count(*) = count(DISTINCT (canton, nbident, parcel_number))
  FROM iris_staging.cadastre_switzerland
UNION ALL
SELECT 'EGRIDs are unique and well formed', count(egrid) - count(DISTINCT egrid)
       + count(*) FILTER (WHERE egrid IS NOT NULL AND egrid !~ '^CH[0-9A-Z]{12}$'),
       count(egrid) = count(DISTINCT egrid) AND count(*) FILTER (WHERE egrid !~ '^CH[0-9A-Z]{12}$') = 0
  FROM iris_staging.cadastre_switzerland
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
