from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from research_navigator.data_plane.database import database_dialect
from research_navigator.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
if os.getenv("RN_DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", os.environ["RN_DATABASE_URL"])
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    sqlalchemy_url = config.get_main_option("sqlalchemy.url")
    if not sqlalchemy_url:
        raise RuntimeError("sqlalchemy.url is required for migrations")
    connect_args: dict[str, object] = {}
    if database_dialect(sqlalchemy_url).name == "turso":
        token = os.getenv("TURSO_AUTH_TOKEN")
        if not token:
            raise RuntimeError("TURSO_AUTH_TOKEN is required for Turso migrations")
        connect_args["auth_token"] = token
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
