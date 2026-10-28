from sqlalchemy import Engine, create_engine, text

from .guard import check_schema


def engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def prepare(eng: Engine, schema: str, table: str = "cadastre_switzerland") -> dict:
    """Create the staging schema and tables if they do not exist yet."""
    from .tables import build

    check_schema(schema)
    md, tables = build(schema, table)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    md.create_all(eng)
    return tables
