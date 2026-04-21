"""add gallery_status to listings

Revision ID: 0f0057317e53
Revises: 28957ed21753
Create Date: 2026-04-20 19:59:31.284375

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f0057317e53'
down_revision: Union[str, Sequence[str], None] = '28957ed21753'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add gallery_status column and seed existing rows.

    Values:
      'ready'   : gallery is trusted — local files on disk, or the source
                  (Navica, MountainLakes) uses non-expiring CDN URLs.
      'pending' : Canopy listing whose gallery still needs local download.
      'skipped' : listing opted out of photos or has zero photos.

    Public-facing routes default to WHERE gallery_status = 'ready' so
    Canopy listings never render with broken CDN-token images.
    """
    op.add_column(
        'listings',
        sa.Column(
            'gallery_status',
            sa.Text(),
            nullable=False,
            server_default='pending',
        ),
    )
    op.create_index(
        'ix_listings_gallery_status',
        'listings',
        ['gallery_status'],
    )

    # Seed existing rows.
    #
    # Non-Canopy sources don't have expiring CDN tokens, so whatever
    # the DB has is fine → 'ready'.
    op.execute(
        """
        UPDATE listings
        SET gallery_status = 'ready'
        WHERE mls_source IN ('NavicaMLS', 'MountainLakesMLS')
        """
    )

    # Canopy listings with zero photos → 'skipped' (not 'pending' — there's
    # nothing to download).
    op.execute(
        """
        UPDATE listings
        SET gallery_status = 'skipped'
        WHERE mls_source = 'CanopyMLS'
          AND (photo_count IS NULL OR photo_count = 0)
        """
    )

    # Canopy listings whose photos array is fully local AND long enough →
    # 'ready'. Anything shorter stays 'pending'.
    op.execute(
        """
        UPDATE listings
        SET gallery_status = 'ready'
        WHERE mls_source = 'CanopyMLS'
          AND photo_count > 0
          AND photos IS NOT NULL
          AND json_array_length(photos::json) >= photo_count - 1
          AND photos::text NOT LIKE '%https://%'
        """
    )


def downgrade() -> None:
    """Drop gallery_status column."""
    op.drop_index('ix_listings_gallery_status', table_name='listings')
    op.drop_column('listings', 'gallery_status')
