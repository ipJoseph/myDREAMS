"""baseline: initial schema captured in PostgreSQL

Revision ID: 28957ed21753
Revises: 
Create Date: 2026-04-20 13:08:37.854546

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28957ed21753'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline revision — no-op.

    The initial PostgreSQL schema (listings, leads, contact_*, pursuits,
    packages, etc.) was created by src/core/database.py's _get_tables_schema
    and the migrate_to_postgres.py script. Existing DEV and PRD databases
    were stamped with this revision rather than re-running DDL.

    All future schema changes must go through new Alembic revisions.
    """
    pass


def downgrade() -> None:
    """Baseline has no downgrade — use the pre-migration SQLite archive."""
    pass
