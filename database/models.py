#!/usr/bin/env python3
"""
Database Models - SQLAlchemy models for Canvas Parent CLI

Tables:
- students: Observed students from Canvas
- courses: Student courses synced from Canvas
- assignments: Course assignments synced from Canvas
- scanned_documents: Scanned homework/tests matched to assignments
- grade_snapshots: Historical grade data for trend analysis
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Student(Base):
    """
    Student record synced from Canvas.

    Maps to observed students (children) linked to the parent account.
    """
    __tablename__ = "students"

    id = Column(Integer, primary_key=True)
    canvas_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    courses = relationship("Course", back_populates="student", cascade="all, delete-orphan")
    scanned_documents = relationship("ScannedDocument", back_populates="student", cascade="all, delete-orphan")
    grade_snapshots = relationship("GradeSnapshot", back_populates="student", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Student(id={self.id}, canvas_id={self.canvas_id}, name='{self.name}')>"


class Course(Base):
    """
    Course record synced from Canvas.

    Tracks student enrollment in courses with term information.
    """
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)
    canvas_id = Column(Integer, nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    name = Column(String(255), nullable=False)
    term = Column(String(100))
    term_start = Column(DateTime)
    term_end = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one course per student per Canvas course ID
    __table_args__ = (
        UniqueConstraint("canvas_id", "student_id", name="uq_course_student"),
        Index("ix_course_student_active", "student_id", "is_active"),
    )

    # Relationships
    student = relationship("Student", back_populates="courses")
    assignments = relationship("Assignment", back_populates="course", cascade="all, delete-orphan")
    grade_snapshots = relationship("GradeSnapshot", back_populates="course", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Course(id={self.id}, canvas_id={self.canvas_id}, name='{self.name}')>"


class Assignment(Base):
    """
    Assignment record synced from Canvas.

    Tracks assignments with due dates, points, and submission status.
    """
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True)
    canvas_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    name = Column(String(500), nullable=False)
    description = Column(Text)
    due_at = Column(DateTime, index=True)
    points_possible = Column(Float)
    submission_types = Column(String(255))  # Comma-separated list
    is_submitted = Column(Boolean, default=False)
    score = Column(Float)
    grade = Column(String(10))
    graded_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: one assignment per course per Canvas assignment ID
    __table_args__ = (
        UniqueConstraint("canvas_id", "course_id", name="uq_assignment_course"),
        Index("ix_assignment_due", "due_at"),
    )

    # Relationships
    course = relationship("Course", back_populates="assignments")
    scanned_documents = relationship("ScannedDocument", back_populates="assignment")

    def __repr__(self):
        return f"<Assignment(id={self.id}, canvas_id={self.canvas_id}, name='{self.name[:30]}...')>"


class ScannedDocument(Base):
    """
    Scanned document record.

    Stores scanned homework/tests with OCR data and Canvas assignment matching.
    """
    __tablename__ = "scanned_documents"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=True)  # Nullable for pending docs
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=True)  # May be unmatched

    # File information
    file_path = Column(String(1000), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer)  # Bytes
    mime_type = Column(String(100))
    file_hash = Column(String(64), index=True)  # SHA256 hash for duplicate detection

    # Scan metadata
    scan_date = Column(DateTime, default=datetime.utcnow)
    source = Column(String(50))  # e.g., "snap_scan", "email", "manual_upload"

    # Document status for smart detection workflow
    status = Column(String(20), default="processed")  # processed, pending, failed
    detection_confidence = Column(Float)  # 0-100, confidence of student detection
    detection_method = Column(String(50))  # e.g., "ocr_name", "course_match", "assignment_match", "ambiguous"

    # OCR results
    ocr_text = Column(Text)
    ocr_confidence = Column(Float)  # 0-100

    # Parsed data
    detected_title = Column(String(500))
    detected_date = Column(DateTime)
    detected_score = Column(Float)
    detected_max_score = Column(Float)

    # Canvas comparison
    canvas_score = Column(Float)
    score_discrepancy = Column(Float)  # detected_score - canvas_score

    # Matching metadata
    match_confidence = Column(Float)  # 0-100
    match_method = Column(String(50))  # e.g., "auto_title", "auto_date", "manual"
    verified = Column(Boolean, default=False)
    verified_at = Column(DateTime)
    verified_by = Column(String(100))

    # Google Drive storage
    drive_file_id = Column(String(255))  # Google Drive file ID
    drive_url = Column(String(1000))

    # Dropbox storage
    dropbox_path = Column(String(1000))  # Full path in Dropbox app folder
    dropbox_url = Column(String(1000))   # Shared link URL

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_scanned_student_date", "student_id", "scan_date"),
        Index("ix_scanned_unmatched", "assignment_id", postgresql_where=(assignment_id.is_(None))),
        Index("ix_scanned_pending", "status", postgresql_where=(status == "pending")),
    )

    # Relationships
    student = relationship("Student", back_populates="scanned_documents")
    assignment = relationship("Assignment", back_populates="scanned_documents")

    def __repr__(self):
        return f"<ScannedDocument(id={self.id}, file_name='{self.file_name}', matched={self.assignment_id is not None})>"


class GradeSnapshot(Base):
    """
    Historical grade snapshot.

    Stores periodic snapshots of grades for trend analysis.
    Typically captured daily or weekly.
    """
    __tablename__ = "grade_snapshots"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    # Grade data
    current_score = Column(Float)  # Percentage (0-100)
    letter_grade = Column(String(5))  # e.g., "A", "B+", etc.
    final_score = Column(Float)

    # Statistics
    assignments_total = Column(Integer)
    assignments_graded = Column(Integer)
    assignments_missing = Column(Integer)
    points_earned = Column(Float)
    points_possible = Column(Float)

    # Snapshot metadata
    snapshot_date = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        # Unique snapshot per student/course/date
        UniqueConstraint("student_id", "course_id", "snapshot_date", name="uq_grade_snapshot"),
        Index("ix_snapshot_student_course", "student_id", "course_id"),
    )

    # Relationships
    student = relationship("Student", back_populates="grade_snapshots")
    course = relationship("Course", back_populates="grade_snapshots")

    def __repr__(self):
        return f"<GradeSnapshot(id={self.id}, course_id={self.course_id}, score={self.current_score}, date={self.snapshot_date})>"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def create_all_tables(engine):
    """Create all tables in the database."""
    Base.metadata.create_all(engine)


def drop_all_tables(engine):
    """Drop all tables in the database."""
    Base.metadata.drop_all(engine)
