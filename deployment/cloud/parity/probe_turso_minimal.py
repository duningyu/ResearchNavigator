"""Minimal Turso transport probe; intentionally excludes app lifespan and R2."""

from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, text


def preflight() -> None:
    import libsql_experimental  # noqa: F401
    import sqlalchemy_libsql  # noqa: F401

    from research_navigator.config import normalize_turso_database_url
    from research_navigator.data_plane.database import database_dialect

    url = normalize_turso_database_url("libsql://example.turso.io")
    if database_dialect(url).name != "turso":
        raise RuntimeError("Turso dialect classification failed")
    engine = create_engine(url)
    engine.dispose()
    print("TURSO_MINIMAL_PROBE_PREFLIGHT=PASS")


def live() -> None:
    raw_url = os.environ.get("TURSO_DATABASE_URL")
    if not raw_url or not os.environ.get("TURSO_AUTH_TOKEN"):
        raise RuntimeError("Turso probe configuration is incomplete")
    from research_navigator.config import normalize_turso_database_url
    from research_navigator.db import Database

    database = Database.from_url(normalize_turso_database_url(raw_url))
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        database.engine.dispose()
    print("TURSO_MINIMAL_PROBE=PASS")


parser = argparse.ArgumentParser()
parser.add_argument("--preflight", action="store_true")
parser.add_argument("--live", action="store_true")
args = parser.parse_args()
if args.preflight == args.live:
    parser.error("select exactly one of --preflight or --live")
if args.preflight:
    preflight()
else:
    live()
