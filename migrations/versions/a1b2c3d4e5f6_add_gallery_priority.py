"""add gallery_priority to listings

Revision ID: a1b2c3d4e5f6
Revises: 0f0057317e53
Create Date: 2026-04-21 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '0f0057317e53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add gallery_priority column.

    Per PHOTO_PIPELINE_SPEC.md: when a user views the detail page of a
    listing whose gallery is not 'ready', the API sets gallery_priority=10
    as a non-blocking side effect. The gallery worker orders its queue by
    gallery_priority DESC, photos_change_timestamp ASC so user-visited
    listings jump the line. Default 0 means "not user-prioritized."
    """
    op.add_column(
        'listings',
        sa.Column(
            'gallery_priority',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ),
    )
    # Partial index: only rows where priority has been set.
    # Keeps the index tiny (a handful of rows at a time) without
    # maintenance cost on the 78k-row table.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_listings_gallery_priority_active "
        "ON listings (gallery_priority DESC) WHERE gallery_priority > 0"
    )


def downgrade() -> None:
    """Drop gallery_priority column."""
    op.execute("DROP INDEX IF EXISTS ix_listings_gallery_priority_active")
    op.drop_column('listings', 'gallery_priority')
