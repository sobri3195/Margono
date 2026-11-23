from functools import lru_cache
from os import environ
from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import BaseModel
from sqlalchemy import create_engine, pool, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

DatabaseStatus = Literal["ready", "not_configured", "unavailable", "migration_required"]


class Dependencies(BaseModel):
    database: DatabaseStatus
    worker: Literal["not_implemented"] = "not_implemented"
    sync: Literal["not_implemented"] = "not_implemented"


class Readiness(BaseModel):
    status: Literal["not_ready"] = "not_ready"
    mode: Literal["SYNTHETIC"] = "SYNTHETIC"
    pilot: Literal["blocked"] = "blocked"
    checks: Dependencies


@lru_cache(maxsize=1)
def expected_heads() -> frozenset[str]:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def database_status() -> DatabaseStatus:
    raw_url = environ.get("MARGONO_DATABASE_URL")
    if not raw_url:
        return "not_configured"

    try:
        url = make_url(raw_url)
        if url.drivername != "postgresql+psycopg":
            return "unavailable"

        engine = create_engine(
            url,
            poolclass=pool.NullPool,
            connect_args={"connect_timeout": 2},
        )
        with engine.connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '1500ms'"))
            version_table = connection.scalar(
                text("SELECT to_regclass('alembic_version')")
            )
            if version_table is None:
                return "migration_required"
            versions = connection.scalars(
                text("SELECT version_num FROM alembic_version")
            )
            if frozenset(versions) != expected_heads():
                return "migration_required"
    except (SQLAlchemyError, ValueError):
        return "unavailable"

    return "ready"
