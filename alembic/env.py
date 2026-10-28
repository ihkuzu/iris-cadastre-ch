from sqlalchemy import create_engine, text

from alembic import context
from app.config.settings import get_settings
from app.database.guard import check_schema

settings = get_settings()
check_schema(settings.db_schema)


def run_migrations_online() -> None:
    with create_engine(settings.database_url).connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))
        conn.commit()
        context.configure(connection=conn, version_table_schema=settings.db_schema)
        with context.begin_transaction():
            context.run_migrations(schema=settings.db_schema, table=settings.table)


run_migrations_online()
