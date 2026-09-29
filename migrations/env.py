"""Alembic migrations of the hosted app (web/models.py). The database URL comes from DATABASE_URL, never a file.

    .venv/bin/alembic upgrade head                        # local: database eclass_web_dev
    .venv/bin/alembic revision --autogenerate -m "..."    # after changing web/models.py; review the result
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from web.config import database_url
from web.models import Base

config = context.config
# The CLI configures logging from alembic.ini; callers that run migrations in-process (tests) keep their own
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or database_url()  # tests pass their own database


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
