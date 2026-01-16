"""add_smart_detection_columns

Revision ID: a2c8f5e31b7d
Revises: 85f4342d10ae
Create Date: 2026-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2c8f5e31b7d'
down_revision: Union[str, Sequence[str], None] = '85f4342d10ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add smart detection columns to scanned_documents table."""

    # Make student_id nullable for pending documents
    op.alter_column(
        'scanned_documents',
        'student_id',
        existing_type=sa.Integer(),
        nullable=True,
    )

    # Add status column for document workflow state
    op.add_column(
        'scanned_documents',
        sa.Column('status', sa.String(20), server_default='processed', nullable=False),
    )

    # Add detection confidence (0-100)
    op.add_column(
        'scanned_documents',
        sa.Column('detection_confidence', sa.Float(), nullable=True),
    )

    # Add detection method (ocr_name, course_match, assignment_match, ambiguous)
    op.add_column(
        'scanned_documents',
        sa.Column('detection_method', sa.String(50), nullable=True),
    )

    # Add partial index for pending documents
    op.create_index(
        'ix_scanned_pending',
        'scanned_documents',
        ['status'],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Remove smart detection columns."""

    # Drop the index
    op.drop_index('ix_scanned_pending', table_name='scanned_documents')

    # Remove columns
    op.drop_column('scanned_documents', 'detection_method')
    op.drop_column('scanned_documents', 'detection_confidence')
    op.drop_column('scanned_documents', 'status')

    # Make student_id non-nullable again
    # Note: This will fail if there are any rows with NULL student_id
    op.alter_column(
        'scanned_documents',
        'student_id',
        existing_type=sa.Integer(),
        nullable=False,
    )
