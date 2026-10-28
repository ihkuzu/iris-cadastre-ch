"""create iris_staging.cadastre_switzerland, ingestion_runs and rejected_records

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from sqlalchemy import text

from alembic import op
from app.database.tables import build

revision = "0001"
down_revision = None


def upgrade(schema: str, table: str) -> None:
    bind = op.get_bind()
    bind.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    bind.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    build(schema, table)[0].create_all(bind)


def downgrade(schema: str, table: str) -> None:
    build(schema, table)[0].drop_all(op.get_bind())
