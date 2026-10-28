"""Write accepted rows and rejections into the staging tables, idempotently."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from geoalchemy2.shape import from_shape
from loguru import logger
from sqlalchemy import Engine, bindparam, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.config.sources import Source
from app.database.guard import StagingGuardError, check_schema
from app.database.session import prepare
from app.extractors.av_file import Extract
from app.transformers.parcels import Result

BATCH = 1000
UPDATABLE = (
    "country",
    "canton_name",
    "bfs_nr",
    "municipality",
    "egrid",
    "parcel_type",
    "completeness",
    "area_m2",
    "area_source_m2",
    "geom",
    "geom_wgs84",
    "geometry_repaired",
    "source_crs",
    "source_name",
    "source_url",
    "licence",
    "licence_url",
    "source_file",
    "source_sha256",
    "source_layer",
    "source_feature_id",
    "source_dataset_date",
    "source_attributes",
    "record_hash",
    "run_id",
)


@dataclass
class LoadStats:
    run_id: uuid.UUID
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0


def _rows(result: Result, extract: Extract, source: Source, run_id) -> list[dict]:
    rows = []
    for r in result.rows:
        row = dict(r)
        if isinstance(row["source_dataset_date"], str):
            row["source_dataset_date"] = date.fromisoformat(row["source_dataset_date"])
        row["geom"] = from_shape(r["geom"], srid=2056)
        row["geom_wgs84"] = from_shape(r["geom_wgs84"], srid=4326)
        row.update(
            source_name=f"{source.name} ({source.dataset})",
            source_url=source.url,
            licence=source.licence,
            licence_url=source.licence_url,
            source_file=extract.path.name,
            source_sha256=extract.sha256,
            source_layer=extract.layer,
            run_id=run_id,
        )
        rows.append(row)
    return rows


def load(engine: Engine, schema: str, table: str, result: Result, extract: Extract, source: Source) -> LoadStats:
    check_schema(schema)
    if source.synthetic and schema == "iris_staging":
        raise StagingGuardError("synthetic fixtures may only go into an iris_staging_<test> schema")
    if not source.lawful:
        raise StagingGuardError(f"{source.canton}: access is {source.access!r}, not open; not ingesting")
    t = prepare(engine, schema, table)
    parcels, runs, rejected = t["parcels"], t["runs"], t["rejected"]
    stats = LoadStats(run_id=uuid.uuid4())
    log = logger.bind(run_id=str(stats.run_id), canton=source.canton, file=extract.path.name)
    started = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            runs.insert().values(
                run_id=stats.run_id,
                canton=source.canton,
                source_url=source.url,
                source_file=extract.path.name,
                source_sha256=extract.sha256,
                source_layer=extract.layer,
                started_at=started,
                status="running",
            )
        )
    try:
        rows = _rows(result, extract, source, stats.run_id)
        with engine.begin() as conn:
            rows = _drop_egrid_clashes(conn, parcels, rows, result)
            for i in range(0, len(rows), BATCH):
                chunk = rows[i : i + BATCH]
                stmt = insert(parcels).values(chunk)
                excluded = stmt.excluded
                stmt = stmt.on_conflict_do_update(
                    constraint=f"{table}_natural_key",
                    set_={**{c: excluded[c] for c in UPDATABLE}, "updated_at": func.now()},
                    # only rows whose content changed are touched, so a rerun leaves everything as it was
                    where=parcels.c.record_hash != excluded.record_hash,
                ).returning(text("(xmax = 0) AS inserted"))
                flags = [r.inserted for r in conn.execute(stmt)]
                stats.inserted += sum(flags)
                stats.updated += len(flags) - sum(flags)
            stats.unchanged = len(rows) - stats.inserted - stats.updated
            if result.rejected:
                conn.execute(rejected.insert(), [{**r, "run_id": stats.run_id} for r in result.rejected])
            stats.rejected = len(result.rejected)
            conn.execute(
                update(runs)
                .where(runs.c.run_id == stats.run_id)
                .values(
                    finished_at=datetime.now(UTC),
                    status="succeeded",
                    read=result.read,
                    accepted=len(rows),
                    inserted=stats.inserted,
                    updated=stats.updated,
                    unchanged=stats.unchanged,
                    rejected=stats.rejected,
                    repaired=result.repaired,
                    details={
                        "reasons": dict(result.reasons),
                        "warnings": dict(result.warnings),
                        "mapping": result.mapping,
                        "source_crs": result.source_crs,
                        "licence": source.licence,
                        "dataset_date": source.dataset_date,
                    },
                )
            )
    except Exception as error:
        with engine.begin() as conn:
            conn.execute(
                update(runs)
                .where(runs.c.run_id == stats.run_id)
                .values(finished_at=datetime.now(UTC), status="failed", details={"error": str(error)[:2000]})
            )
        log.exception("load failed, nothing from this run was kept")
        raise
    log.info(
        "inserted {}, updated {}, unchanged {}, rejected {}",
        stats.inserted,
        stats.updated,
        stats.unchanged,
        stats.rejected,
    )
    return stats


def _drop_egrid_clashes(conn, parcels, rows: list[dict], result: Result) -> list[dict]:
    """An EGRID already stored under another parcel key is a conflict, not an update."""
    egrids = [r["egrid"] for r in rows if r["egrid"]]
    if not egrids:
        return rows
    stmt = select(parcels.c.egrid, parcels.c.canton, parcels.c.nbident, parcels.c.parcel_number).where(
        parcels.c.egrid.in_(bindparam("egrids", expanding=True))
    )
    taken = {}
    for i in range(0, len(egrids), 5000):
        for e, c, n, p in conn.execute(stmt, {"egrids": egrids[i : i + 5000]}):
            taken[e] = (c, n, p)
    keep = []
    for r in rows:
        owner = taken.get(r["egrid"]) if r["egrid"] else None
        if owner and owner != (r["canton"], r["nbident"], r["parcel_number"]):
            result.rejected.append(
                {
                    "canton": r["canton"],
                    "source_feature_id": r["source_feature_id"],
                    "source_attributes": r["source_attributes"],
                    "geometry_wkt": None,
                    "reason": "egrid_already_stored",
                    "detail": "/".join(owner),
                }
            )
            continue
        keep.append(r)
    return keep
