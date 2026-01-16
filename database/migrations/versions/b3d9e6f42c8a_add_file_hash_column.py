"""add_file_hash_column

Revision ID: b3d9e6f42c8a
Revises: a2c8f5e31b7d
Create Date: 2026-01-16 02:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d9e6f42c8a'
down_revision: Union[str, Sequence[str], None] = 'a2c8f5e31b7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add file_hash column for duplicate detection."""
    op.add_column(
        'scanned_documents',
        sa.Column('file_hash', sa.String(64), nullable=True),
    )
    op.create_index(
        'ix_scanned_file_hash',
        'scanned_documents',
        ['file_hash'],
    )


def downgrade() -> None:
    """Remove file_hash column."""
    op.drop_index('ix_scanned_file_hash', table_name='scanned_documents')
    op.drop_column('scanned_documents', 'file_hash')
