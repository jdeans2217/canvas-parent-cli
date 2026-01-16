"""add_dropbox_fields

Revision ID: c4e7a8b92d1f
Revises: b3d9e6f42c8a
Create Date: 2026-01-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e7a8b92d1f'
down_revision: Union[str, Sequence[str], None] = 'b3d9e6f42c8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Dropbox storage columns."""
    op.add_column(
        'scanned_documents',
        sa.Column('dropbox_path', sa.String(1000), nullable=True),
    )
    op.add_column(
        'scanned_documents',
        sa.Column('dropbox_url', sa.String(1000), nullable=True),
    )


def downgrade() -> None:
    """Remove Dropbox storage columns."""
    op.drop_column('scanned_documents', 'dropbox_url')
    op.drop_column('scanned_documents', 'dropbox_path')
