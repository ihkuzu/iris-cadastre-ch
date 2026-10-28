-- Example queries on the staging data, used to explain the quality report.
-- The area tolerance (1 m2 and 0.5 %) is the default of IRIS_AREA_TOLERANCE_M2 / _SHARE.
-- Run: docker compose exec -T db psql -U iris -d iris_staging < sql/examples.sql

\pset pager off

-- rejected records of the latest successful run per canton only, so reruns are not counted twice
CREATE TEMP VIEW latest_rejects AS
SELECT r.* FROM iris_staging.rejected_records r
WHERE r.run_id IN (SELECT DISTINCT ON (canton) run_id FROM iris_staging.ingestion_runs
                   WHERE status = 'succeeded' ORDER BY canton, started_at DESC);

\echo '1. Parcels and area per canton and municipality (top 10 by parcels)'
SELECT canton, bfs_nr, municipality, count(*) AS parcels, round(sum(area_m2) / 1e6, 2) AS km2
FROM iris_staging.cadastre_switzerland
GROUP BY canton, bfs_nr, municipality ORDER BY parcels DESC LIMIT 10;

\echo '2. The parcel under a point (Basel Münster, WGS84)'
SELECT canton, municipality, nbident, parcel_number, egrid, area_m2
FROM iris_staging.cadastre_switzerland
WHERE ST_Contains(geom, ST_Transform(ST_SetSRID(ST_MakePoint(7.5925, 47.5565), 4326), 2056));

\echo '3. Rejected because one EGRID sits on several parcel keys: how many keys per EGRID'
SELECT copies, count(*) AS egrids FROM (
    SELECT detail, count(*) AS copies FROM latest_rejects
    WHERE reason = 'duplicate_egrid' GROUP BY detail) d
GROUP BY copies ORDER BY copies;

\echo '4. Examples of such EGRIDs with their keys, municipality and attributes'
SELECT detail AS egrid,
       string_agg(concat_ws(' ', source_attributes->>'NBIdent', source_attributes->>'Nummer',
                  'bfs', source_attributes->>'BFSNr', source_attributes->>'Gueltigkeit',
                  source_attributes->>'Vollstaendigkeit', 'area', source_attributes->>'Flaeche'), ' | ') AS keys
FROM latest_rejects WHERE reason = 'duplicate_egrid'
GROUP BY detail ORDER BY detail LIMIT 12;

\echo '5. Do the rejected EGRID copies share NBIdent, number or municipality?'
SELECT count(*) AS egrids,
       count(*) FILTER (WHERE nbidents = 1) AS same_nbident,
       count(*) FILTER (WHERE numbers = 1) AS same_number,
       count(*) FILTER (WHERE bfs = 1) AS same_municipality
FROM (SELECT detail, count(DISTINCT source_attributes->>'NBIdent') AS nbidents,
             count(DISTINCT source_attributes->>'Nummer') AS numbers,
             count(DISTINCT source_attributes->>'BFSNr') AS bfs
      FROM latest_rejects WHERE reason = 'duplicate_egrid' GROUP BY detail) d;

\echo '6. Same parcel key with different content'
SELECT detail, source_feature_id,
       concat_ws(' ', 'bfs', source_attributes->>'BFSNr', source_attributes->>'EGRIS_EGRID',
                 source_attributes->>'Gueltigkeit', 'area', source_attributes->>'Flaeche') AS attributes,
       round(ST_Area(ST_GeomFromText(geometry_wkt, 2056))::numeric, 1) AS wkt_area
FROM latest_rejects WHERE reason = 'conflicting_duplicate' ORDER BY detail;

\echo '7. Computed area against the stated area (Flaeche), per canton'
SELECT canton, count(*) AS parcels,
       count(*) FILTER (WHERE abs(area_m2 - area_source_m2) > greatest(1, 0.005 * area_source_m2)) AS mismatch,
       count(*) FILTER (WHERE area_source_m2 = round(area_source_m2)) AS stated_whole_m2,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(area_m2 - area_source_m2))::numeric, 2) AS median_diff_m2
FROM iris_staging.cadastre_switzerland WHERE area_source_m2 IS NOT NULL
GROUP BY canton ORDER BY canton;

\echo '8. Mismatches by size of the difference'
SELECT canton,
       CASE WHEN d <= 0.05 THEN 'a) up to 5 %' WHEN d <= 0.5 THEN 'b) 5-50 %'
            WHEN d <= 2 THEN 'c) 50-200 %' ELSE 'd) over 200 %' END AS difference,
       count(*) AS parcels,
       count(*) FILTER (WHERE area_source_m2 > area_m2) AS stated_larger,
       count(*) FILTER (WHERE ST_NumGeometries(geom) > 1) AS multipart,
       count(*) FILTER (WHERE completeness IS DISTINCT FROM 'vollstaendig') AS not_complete
FROM (SELECT *, abs(area_m2 - area_source_m2) / nullif(area_source_m2, 0) AS d
      FROM iris_staging.cadastre_switzerland
      WHERE abs(area_m2 - area_source_m2) > greatest(1, 0.005 * area_source_m2)) m
GROUP BY canton, difference ORDER BY canton, difference;

\echo '9. Examples of large mismatches'
SELECT canton, bfs_nr, nbident, parcel_number, area_m2, area_source_m2, completeness, validity,
       ST_NumGeometries(geom) AS parts, ST_NumInteriorRings(ST_GeometryN(geom, 1)) AS holes
FROM iris_staging.cadastre_switzerland
WHERE abs(area_m2 - area_source_m2) > greatest(1, 0.005 * area_source_m2)
ORDER BY abs(area_m2 - area_source_m2) DESC LIMIT 12;

\echo '10. Values of completeness and validity per canton'
SELECT canton, completeness, validity, count(*) FROM iris_staging.cadastre_switzerland
GROUP BY 1, 2, 3 ORDER BY 1, 4 DESC;
