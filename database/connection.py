#!/usr/bin/env python3
"""
Database Connection - SQLAlchemy engine and session management

Provides database connection handling with connection pooling.
"""

import os
from typing import Optional, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from config import get_config
from database.models import Base

# Global engine and session factory
_engine = None
_SessionLocal = None


def get_engine(database_url: Optional[str] = None):
    """
    Get or create the SQLAlchemy engine.

    Args:
        database_url: Optional database URL (uses config if not provided)

    Returns:
        SQLAlchemy engine instance
    """
    global _engine

    if _engine is None:
        if database_url is None:
            config = get_config()
            database_url = config.database.url

        if not database_url:
            raise ValueError(
                "DATABASE_URL not configured. Set it in .env file.\n"
                "Example: DATABASE_URL=postgresql://user:pass@localhost:5432/canvas_parent"
            )

        _engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before use
            echo=False,  # Set to True for SQL debugging
        )

    return _engine


def get_session_factory():
    """
    Get or create the session factory.

    Returns:
        SQLAlchemy sessionmaker instance
    """
    global _SessionLocal

    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )

    return _SessionLocal


def get_session() -> Session:
    """
    Create a new database session.

    Returns:
        SQLAlchemy Session instance

    Note:
        Caller is responsible for closing the session.
    """
    SessionLocal = get_session_factory()
    return SessionLocal()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db() as db:
            db.query(Student).all()

    Automatically handles commit/rollback and closing.
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(database_url: Optional[str] = None):
    """
    Initialize the database by creating all tables.

    Args:
        database_url: Optional database URL

    Note:
        This creates tables directly. For production, use Alembic migrations.
    """
    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully.")


def drop_db(database_url: Optional[str] = None):
    """
    Drop all database tables.

    Args:
        database_url: Optional database URL

    Warning:
        This will delete all data. Use with caution.
    """
    engine = get_engine(database_url)
    Base.metadata.drop_all(bind=engine)
    print("Database tables dropped.")


def test_connection(database_url: Optional[str] = None) -> bool:
    """
    Test database connection.

    Args:
        database_url: Optional database URL

    Returns:
        True if connection successful, False otherwise
    """
    try:
        engine = get_engine(database_url)
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == "__main__":
    print("Database Connection Test")
    print("=" * 50)

    config = get_config()
    if not config.database.url:
        print("\nDATABASE_URL not set in .env file.")
        print("Example: DATABASE_URL=postgresql://user:pass@localhost:5432/canvas_parent")
        print("\nTo create the database:")
        print("  createdb canvas_parent")
        exit(1)

    print(f"\nDatabase URL: {config.database.url[:30]}...")

    if test_connection():
        print("Connection: OK")

        # Optionally create tables
        response = input("\nCreate tables? (y/N): ").strip().lower()
        if response == "y":
            init_db()
    else:
        print("Connection: FAILED")
