"""Alembic environment.

The database URL comes from application settings (env var DATABASE_URL only —
no .env access, no committed default) and is used in its sync form.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, text

from alembic import context
from src.config.settings import get_settings
from src.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = get_settings().database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. It is a required secret with no committed "
            "default — export DATABASE_URL=postgresql+psycopg://user:password@host:5432/dbname "
            "before running alembic."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.execute("CREATE EXTENSION IF NOT EXISTS citext")
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        # citext is used by the schema, and the extension must exist before any
        # table using it is created. gen_random_uuid() is built into Postgres 15.
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
        connection.commit()

        context.configure(connection=connection, target_metadata=target_metadata) 
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
