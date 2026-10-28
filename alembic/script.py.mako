"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}


def upgrade(schema: str, table: str) -> None:
    ${upgrades if upgrades else "pass"}


def downgrade(schema: str, table: str) -> None:
    ${downgrades if downgrades else "pass"}
