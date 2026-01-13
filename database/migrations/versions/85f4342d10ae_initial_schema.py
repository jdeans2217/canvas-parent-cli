"""initial_schema

Revision ID: 85f4342d10ae
Revises:
Create Date: 2026-01-13 14:42:51.769516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85f4342d10ae'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables for Canvas Parent CLI."""

    # Students table
    op.create_table(
        'students',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('canvas_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_students_canvas_id', 'students', ['canvas_id'], unique=True)

    # Courses table
    op.create_table(
        'courses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('canvas_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('term', sa.String(100)),
        sa.Column('term_start', sa.DateTime()),
        sa.Column('term_end', sa.DateTime()),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_courses_canvas_id', 'courses', ['canvas_id'])
    op.create_index('ix_course_student_active', 'courses', ['student_id', 'is_active'])
    op.create_unique_constraint('uq_course_student', 'courses', ['canvas_id', 'student_id'])

    # Assignments table
    op.create_table(
        'assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('canvas_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), sa.ForeignKey('courses.id'), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('due_at', sa.DateTime()),
        sa.Column('points_possible', sa.Float()),
        sa.Column('submission_types', sa.String(255)),
        sa.Column('is_submitted', sa.Boolean(), server_default='false'),
        sa.Column('score', sa.Float()),
        sa.Column('grade', sa.String(10)),
        sa.Column('graded_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_assignments_canvas_id', 'assignments', ['canvas_id'])
    op.create_index('ix_assignment_due', 'assignments', ['due_at'])
    op.create_unique_constraint('uq_assignment_course', 'assignments', ['canvas_id', 'course_id'])

    # Scanned documents table
    op.create_table(
        'scanned_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('assignment_id', sa.Integer(), sa.ForeignKey('assignments.id'), nullable=True),

        # File information
        sa.Column('file_path', sa.String(1000), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_size', sa.Integer()),
        sa.Column('mime_type', sa.String(100)),

        # Scan metadata
        sa.Column('scan_date', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('source', sa.String(50)),

        # OCR results
        sa.Column('ocr_text', sa.Text()),
        sa.Column('ocr_confidence', sa.Float()),

        # Parsed data
        sa.Column('detected_title', sa.String(500)),
        sa.Column('detected_date', sa.DateTime()),
        sa.Column('detected_score', sa.Float()),
        sa.Column('detected_max_score', sa.Float()),

        # Canvas comparison
        sa.Column('canvas_score', sa.Float()),
        sa.Column('score_discrepancy', sa.Float()),

        # Matching metadata
        sa.Column('match_confidence', sa.Float()),
        sa.Column('match_method', sa.String(50)),
        sa.Column('verified', sa.Boolean(), server_default='false'),
        sa.Column('verified_at', sa.DateTime()),
        sa.Column('verified_by', sa.String(100)),

        # Cloud storage
        sa.Column('drive_file_id', sa.String(255)),
        sa.Column('drive_url', sa.String(1000)),

        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_scanned_student_date', 'scanned_documents', ['student_id', 'scan_date'])

    # Grade snapshots table
    op.create_table(
        'grade_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('student_id', sa.Integer(), sa.ForeignKey('students.id'), nullable=False),
        sa.Column('course_id', sa.Integer(), sa.ForeignKey('courses.id'), nullable=False),

        # Grade data
        sa.Column('current_score', sa.Float()),
        sa.Column('letter_grade', sa.String(5)),
        sa.Column('final_score', sa.Float()),

        # Statistics
        sa.Column('assignments_total', sa.Integer()),
        sa.Column('assignments_graded', sa.Integer()),
        sa.Column('assignments_missing', sa.Integer()),
        sa.Column('points_earned', sa.Float()),
        sa.Column('points_possible', sa.Float()),

        # Snapshot metadata
        sa.Column('snapshot_date', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_snapshot_date', 'grade_snapshots', ['snapshot_date'])
    op.create_index('ix_snapshot_student_course', 'grade_snapshots', ['student_id', 'course_id'])
    op.create_unique_constraint('uq_grade_snapshot', 'grade_snapshots', ['student_id', 'course_id', 'snapshot_date'])


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table('grade_snapshots')
    op.drop_table('scanned_documents')
    op.drop_table('assignments')
    op.drop_table('courses')
    op.drop_table('students')
