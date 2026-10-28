"""Writes are only allowed into staging schemas, never into iris_core or production."""

import re

STAGING = re.compile(r"^iris_staging(_[a-z0-9_]+)?$")
FORBIDDEN = {"iris_core", "public", "production", "prod"}


class StagingGuardError(RuntimeError):
    pass


def check_schema(schema: str) -> str:
    if schema in FORBIDDEN or not STAGING.match(schema):
        raise StagingGuardError(
            f"refusing to write to schema {schema!r}: only iris_staging or iris_staging_<name> allowed"
        )
    return schema
