"""
Database module for Canvas Parent CLI

Provides SQLAlchemy models and database connection handling.
"""

from database.models import (
    Base,
    Student,
    Course,
    Assignment,
    ScannedDocument,
    GradeSnapshot,
)
from database.connection import get_engine, get_session, init_db

__all__ = [
    "Base",
    "Student",
    "Course",
    "Assignment",
    "ScannedDocument",
    "GradeSnapshot",
    "get_engine",
    "get_session",
    "init_db",
]
