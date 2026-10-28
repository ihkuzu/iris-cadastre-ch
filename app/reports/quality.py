"""The quality report, built from what is in the staging tables, not from memory."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, text

from app.database.guard import check_schema

REASONS = {
    "missing_key": "NBIdent or parcel number missing",
    "malformed_egrid": "EGRID present but not CH + 12 characters",
    "empty_geometry": "no geometry",
    "not_polygon": "geometry is not an area",
    "invalid_geometry": "invalid polygon that could not be repaired within tolerance",
    "exact_duplicate": "identical copy of another feature, kept once",
    "conflicting_duplicate": "same parcel key with different content, all copies held back",
    "duplicate_egrid": "same EGRID on different land register parcels in one file",
    "egrid_already_stored": "EGRID already stored for a different land register parcel",
    "canton_mismatch": "canton attribute differs from the configured canton",
}


def gather(engine: Engine, schema: str, table: str) -> dict:
    check_schema(schema)
    q = lambda sql: [dict(r._mapping) for r in conn.execute(text(sql.format(s=schema, t=table)))]  # noqa: E731
    with engine.connect() as conn:
        return {
            "generated": datetime.now(UTC).isoformat(timespec="seconds"),
            "by_canton": q("""SELECT canton, canton_name, count(*) AS parcels,
                count(DISTINCT bfs_nr) AS municipalities, count(egrid) AS with_egrid,
                count(*) FILTER (WHERE bfs_nr IS NULL) AS without_municipality,
                count(*) FILTER (WHERE geometry_repaired) AS repaired,
                round(sum(area_m2) / 1e6, 2) AS area_km2,
                count(*) FILTER (WHERE area_source_m2 IS NOT NULL
                    AND abs(area_m2 - area_source_m2) > greatest(1, 0.005 * area_source_m2)) AS area_mismatch,
                min(source_dataset_date) AS dataset_date, max(licence) AS licence, max(source_crs) AS source_crs
                FROM "{s}".{t} GROUP BY canton, canton_name ORDER BY canton"""),
            "runs": q("""SELECT run_id::text, canton, source_file, left(source_sha256, 12) AS sha256, status,
                read, accepted, inserted, updated, unchanged, rejected, repaired, not_in_source,
                to_char(started_at, 'YYYY-MM-DD HH24:MI') AS started, details
                FROM "{s}".ingestion_runs ORDER BY started_at DESC LIMIT 20"""),
            "rejected": q("""SELECT canton, reason, count(*) AS n FROM "{s}".rejected_records
                WHERE run_id IN (SELECT DISTINCT ON (canton) run_id FROM "{s}".ingestion_runs
                                 WHERE status = 'succeeded' ORDER BY canton, started_at DESC)
                GROUP BY canton, reason ORDER BY canton, n DESC"""),
            "checks": q("""SELECT
                count(*) FILTER (WHERE NOT ST_IsValid(geom)) AS invalid_geometries,
                count(*) FILTER (WHERE ST_SRID(geom) <> 2056 OR ST_SRID(geom_wgs84) <> 4326) AS wrong_srid,
                count(*) FILTER (WHERE ST_IsEmpty(geom)) AS empty_geometries,
                count(*) - count(DISTINCT (canton, nbident, parcel_number)) AS duplicate_keys,
                (SELECT count(*) FROM (SELECT egrid FROM "{s}".{t} WHERE egrid IS NOT NULL GROUP BY egrid
                    HAVING count(DISTINCT (canton, nbident, split_part(parcel_number, '.', 1))) > 1) e)
                    AS egrids_on_two_parcels,
                count(*) FILTER (WHERE country <> 'CH') AS wrong_country
                FROM "{s}".{t}"""),
            # five parcels per canton, picked by EGRID so the sample is spread over the canton
            "sample": q("""SELECT canton, bfs_nr, municipality, nbident, parcel_number, egrid, area_m2,
                round(ST_X(ST_PointOnSurface(geom_wgs84))::numeric, 6) AS lon,
                round(ST_Y(ST_PointOnSurface(geom_wgs84))::numeric, 6) AS lat
                FROM (SELECT *, row_number() OVER (
                          PARTITION BY canton ORDER BY md5(coalesce(egrid, nbident || parcel_number))) AS n
                      FROM "{s}".{t}) p
                WHERE n <= 5 ORDER BY canton, nbident, parcel_number"""),
        }


def _table(rows: list[dict], cols: list[str]) -> str:
    if not rows:
        return "_none_\n"
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join("" if r.get(c) is None else str(r[c]) for c in cols) + " |\n" for r in rows)


def write(data: dict, report: Path, results: Path, notes: Path | None = None) -> None:
    results.mkdir(parents=True, exist_ok=True)
    (results / "summary.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    if data["sample"]:
        with open(results / "sample_parcels.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data["sample"][0]))
            w.writeheader()
            w.writerows(data["sample"])
    checks = data["checks"][0] if data["checks"] else {}
    ok = all(v == 0 for v in checks.values())
    lines = [
        "# Quality report: Swiss cadastre (AV) ingestion\n",
        f"Generated {data['generated']} from the staging tables.\n",
        "## Coverage by canton\n",
        _table(
            data["by_canton"],
            [
                "canton",
                "canton_name",
                "parcels",
                "municipalities",
                "with_egrid",
                "without_municipality",
                "repaired",
                "area_mismatch",
                "area_km2",
                "dataset_date",
                "source_crs",
                "licence",
            ],
        ),
        "\n## Integrity checks\n",
        f"All checks {'pass' if ok else 'do NOT pass'}.\n\n",
        _table([checks], list(checks)) if checks else "_none_\n",
        "\n## Rejected records (latest successful run per canton)\n",
        _table(
            [{**r, "meaning": REASONS.get(r["reason"], "")} for r in data["rejected"]],
            ["canton", "reason", "n", "meaning"],
        ),
        "\n## Runs\n",
        _table(
            data["runs"],
            [
                "started",
                "canton",
                "source_file",
                "sha256",
                "status",
                "read",
                "accepted",
                "inserted",
                "updated",
                "unchanged",
                "rejected",
                "repaired",
            ],
        ),
        "\n## Sample rows\n",
        _table(data["sample"], list(data["sample"][0]) if data["sample"] else []),
    ]
    if notes and notes.exists():
        lines += ["\n", notes.read_text(encoding="utf-8")]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("".join(lines), encoding="utf-8")
