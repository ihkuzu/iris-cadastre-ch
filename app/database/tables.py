"""Table definitions. The schema is a parameter so tests can use their own staging schema."""

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .guard import check_schema


def build(schema: str, table: str = "cadastre_switzerland") -> tuple[MetaData, dict[str, Table]]:
    check_schema(schema)
    md = MetaData(schema=schema)
    parcels = Table(
        table,
        md,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("country", String(2), nullable=False, server_default="CH"),
        Column("canton", String(2), nullable=False),
        Column("canton_name", Text, nullable=False),
        Column("bfs_nr", Integer),
        Column("municipality", Text),
        Column("nbident", Text, nullable=False),
        Column("parcel_number", Text, nullable=False),
        Column("egrid", String(14)),
        Column("parcel_type", Text),
        Column("completeness", Text),
        Column("validity", Text),
        Column("area_m2", Numeric(14, 2), nullable=False),
        Column("area_source_m2", Numeric(14, 2)),
        Column("geom", Geometry("MULTIPOLYGON", srid=2056, spatial_index=False), nullable=False),
        Column("geom_wgs84", Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False),
        Column("geometry_repaired", Boolean, nullable=False, server_default=text("false")),
        Column("source_crs", Text, nullable=False),
        Column("source_name", Text, nullable=False),
        Column("source_url", Text, nullable=False),
        Column("licence", Text, nullable=False),
        Column("licence_url", Text, nullable=False),
        Column("source_file", Text, nullable=False),
        Column("source_sha256", String(64), nullable=False),
        Column("source_layer", Text, nullable=False),
        Column("source_feature_id", Text),
        Column("source_dataset_date", Date),
        Column("source_attributes", JSONB, nullable=False),
        Column("record_hash", String(64), nullable=False),
        Column("run_id", UUID(as_uuid=True), nullable=False),
        # the last run whose source file still contained this parcel; older values mean it left the source
        Column("last_seen_run_id", UUID(as_uuid=True), nullable=False),
        Column("first_seen_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
        UniqueConstraint("canton", "nbident", "parcel_number", name=f"{table}_natural_key"),
        UniqueConstraint("egrid", name=f"{table}_egrid_key"),
        CheckConstraint("country = 'CH'", name=f"{table}_country_ch"),
        CheckConstraint("egrid IS NULL OR egrid ~ '^CH[0-9A-Z]{12}$'", name=f"{table}_egrid_format"),
        CheckConstraint("area_m2 >= 0", name=f"{table}_area_positive"),
    )
    Index(f"{table}_geom_idx", parcels.c.geom, postgresql_using="gist")
    Index(f"{table}_geom_wgs84_idx", parcels.c.geom_wgs84, postgresql_using="gist")
    Index(f"{table}_canton_bfs_idx", parcels.c.canton, parcels.c.bfs_nr)
    runs = Table(
        "ingestion_runs",
        md,
        Column("run_id", UUID(as_uuid=True), primary_key=True),
        Column("canton", String(2), nullable=False),
        Column("source_url", Text, nullable=False),
        Column("source_file", Text, nullable=False),
        Column("source_sha256", String(64), nullable=False),
        Column("source_layer", Text),
        Column("started_at", DateTime(timezone=True), nullable=False),
        Column("finished_at", DateTime(timezone=True)),
        Column("status", Text, nullable=False),
        Column("read", Integer, nullable=False, server_default="0"),
        Column("accepted", Integer, nullable=False, server_default="0"),
        Column("inserted", Integer, nullable=False, server_default="0"),
        Column("updated", Integer, nullable=False, server_default="0"),
        Column("unchanged", Integer, nullable=False, server_default="0"),
        Column("rejected", Integer, nullable=False, server_default="0"),
        Column("repaired", Integer, nullable=False, server_default="0"),
        Column("not_in_source", Integer, nullable=False, server_default="0"),
        Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    rejected = Table(
        "rejected_records",
        md,
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("run_id", UUID(as_uuid=True), nullable=False),
        Column("canton", String(2), nullable=False),
        Column("source_feature_id", Text),
        Column("reason", Text, nullable=False),
        Column("detail", Text),
        Column("source_attributes", JSONB, nullable=False),
        Column("geometry_wkt", Text),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
    Index("rejected_records_run_idx", rejected.c.run_id)
    return md, {"parcels": parcels, "runs": runs, "rejected": rejected}
