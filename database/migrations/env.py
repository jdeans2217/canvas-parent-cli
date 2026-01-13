"""
Alembic migration environment configuration.

Loads database URL from config and uses our SQLAlchemy models.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add the project root to sys.path so we can import our modules
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import our models and config
from database.models import Base
from config import get_config

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the target metadata from our models
target_metadata = Base.metadata

# Get database URL from our config
app_config = get_config()
# Store URL directly (avoid configparser % interpolation issues)
_database_url = app_config.database.url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    if not _database_url:
        raise ValueError(
            "DATABASE_URL not configured. Set it in .env file.\n"
            "Example: DATABASE_URL=postgresql://user:pass@localhost:5432/canvas_parent"
        )

    context.configure(
        url=_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    from sqlalchemy import create_engine

    if not _database_url:
        raise ValueError(
            "DATABASE_URL not configured. Set it in .env file.\n"
            "Example: DATABASE_URL=postgresql://user:pass@localhost:5432/canvas_parent"
        )

    connectable = create_engine(_database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
