"""Write accepted rows and rejections into the staging tables, idempotently."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from geoalchemy2.shape import from_shape, to_shape
from loguru import logger
from sqlalchemy import Engine, bindparam, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.config.sources import Source
from app.database.guard import StagingGuardError, check_schema
from app.database.session import prepare
from app.extractors.av_file import Extract
from app.transformers.parcels import Result, grundstueck

BATCH = 1000
UPDATABLE = (
    "country",
    "canton_name",
    "bfs_nr",
    "municipality",
    "egrid",
    "parcel_type",
    "completeness",
    "validity",
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
    "last_seen_run_id",
)


@dataclass
class LoadStats:
    run_id: uuid.UUID
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    not_in_source: int = 0
    stale_rejected: int = 0


def _rows(result: Result, extract: Extract, source: Source, run_id, skip: set) -> list[dict]:
    rows = []
    for r in result.rows:
        if (r["nbident"], r["parcel_number"]) in skip:
            continue
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
            last_seen_run_id=run_id,
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
        with engine.begin() as conn:
            query = select(parcels.c.nbident, parcels.c.parcel_number, parcels.c.record_hash).where(
                parcels.c.canton == source.canton
            )
            stored = {(n, p): h for n, p, h in conn.execute(query)}
            # rows whose hash is already stored are not sent again, only marked as seen
            same = {
                (r["nbident"], r["parcel_number"])
                for r in result.rows
                if stored.get((r["nbident"], r["parcel_number"])) == r["record_hash"]
            }
            rows = _rows(result, extract, source, stats.run_id, same)
            rows = _drop_egrid_clashes(conn, parcels, rows, result, source.egrid_parts)
            for i in range(0, len(rows), BATCH):
                chunk = rows[i : i + BATCH]
                stmt = insert(parcels)
                excluded = stmt.excluded
                stmt = stmt.on_conflict_do_update(
                    constraint=f"{table}_natural_key",
                    set_={**{c: excluded[c] for c in UPDATABLE}, "updated_at": func.now()},
                    where=parcels.c.record_hash != excluded.record_hash,
                ).returning(text("(xmax = 0) AS inserted"))
                flags = [r.inserted for r in conn.execute(stmt, chunk)]
                stats.inserted += sum(flags)
                stats.updated += len(flags) - sum(flags)
            stats.unchanged = len(same)
            _mark_seen(conn, schema, table, source.canton, stats.run_id, same)
            missing = conn.execute(
                select(parcels.c.nbident, parcels.c.parcel_number).where(
                    parcels.c.canton == source.canton, parcels.c.last_seen_run_id != stats.run_id
                )
            ).all()
            # a stored parcel whose new version was rejected is stale, not gone from the source
            held = {r["key"] for r in result.rejected if r.get("key")}
            stats.stale_rejected = sum(1 for k in missing if tuple(k) in held)
            stats.not_in_source = len(missing) - stats.stale_rejected
            if stats.stale_rejected:
                log.warning("{} stored parcels keep their old version, the new one was rejected", stats.stale_rejected)
            if stats.not_in_source:
                log.warning(
                    "{} stored parcels are no longer in this source file; kept, not deleted", stats.not_in_source
                )
            if result.rejected:
                conn.execute(
                    rejected.insert(),
                    [{**{k: v for k, v in r.items() if k != "key"}, "run_id": stats.run_id} for r in result.rejected],
                )
            stats.rejected = len(result.rejected)
            conn.execute(
                update(runs)
                .where(runs.c.run_id == stats.run_id)
                .values(
                    finished_at=datetime.now(UTC),
                    status="succeeded",
                    read=result.read,
                    accepted=stats.inserted + stats.updated + stats.unchanged,
                    not_in_source=stats.not_in_source,
                    inserted=stats.inserted,
                    updated=stats.updated,
                    unchanged=stats.unchanged,
                    rejected=stats.rejected,
                    repaired=result.repaired,
                    details={
                        "reasons": dict(result.reasons),
                        "merged_parts": result.merged,
                        "stale_rejected": stats.stale_rejected,
                        "warnings": dict(result.warnings),
                        "mapping": result.mapping,
                        "source_crs": result.source_crs,
                        "licence": source.licence,
                        "dataset_date": extract.dataset_date or source.dataset_date,
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


def _drop_egrid_clashes(conn, parcels, rows: list[dict], result: Result, parts: bool) -> list[dict]:
    """An EGRID already stored for another land register parcel is a conflict, not an update."""
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
    # a stored parcel that comes with another EGRID in this file gives its old EGRID up
    now = {(r["canton"], r["nbident"], r["parcel_number"]): r["egrid"] for r in result.rows}
    moved = {e for e, o in taken.items() if now.get(o, e) != e}
    if moved:
        result.warnings["egrid_moved"] += len(moved)
    taken = {e: o for e, o in taken.items() if e not in moved}
    # a stored parcel that left the source was renumbered: the new key takes the EGRID over
    held = {r["key"] for r in result.rejected if r.get("key")}
    gone = {e: o for e, o in taken.items() if o not in now and (o[1], o[2]) not in held}
    for c, n, p in gone.values():
        conn.execute(
            update(parcels)
            .where(parcels.c.canton == c, parcels.c.nbident == n, parcels.c.parcel_number == p)
            .values(egrid=None, updated_at=func.now())
        )
    if gone:
        result.warnings["egrid_taken_by_new_key"] += len(gone)
    taken = {e: o for e, o in taken.items() if e not in gone}
    keep = []
    for r in rows:
        owner = taken.get(r["egrid"]) if r["egrid"] else None
        mine = grundstueck(r["canton"], r["nbident"], r["parcel_number"], parts)
        if owner and grundstueck(*owner, parts) != mine:
            result.rejected.append(
                {
                    "canton": r["canton"],
                    "source_feature_id": r["source_feature_id"],
                    "source_attributes": r["source_attributes"],
                    "geometry_wkt": to_shape(r["geom"]).wkt,
                    "reason": "egrid_already_stored",
                    "key": (r["nbident"], r["parcel_number"]),
                    "detail": "/".join(owner),
                }
            )
            continue
        keep.append(r)
    return keep


def _mark_seen(conn, schema: str, table: str, canton: str, run_id, keys: set) -> None:
    if not keys:
        return
    conn.execute(text("CREATE TEMP TABLE seen_keys (nbident text, parcel_number text) ON COMMIT DROP"))
    conn.execute(text("INSERT INTO seen_keys VALUES (:n, :p)"), [{"n": n, "p": p} for n, p in keys])
    conn.execute(
        text(
            f'UPDATE "{schema}".{table} t SET last_seen_run_id = :run FROM seen_keys s '
            "WHERE t.canton = :canton AND t.nbident = s.nbident AND t.parcel_number = s.parcel_number"
        ),
        {"run": run_id, "canton": canton},
    )
