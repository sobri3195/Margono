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

from .synthetic_worker import WORKER_TIMEOUT_SECONDS

DatabaseStatus = Literal["ready", "not_configured", "unavailable", "migration_required"]


class Dependencies(BaseModel):
    database: DatabaseStatus
    worker: Literal["active", "not_observed", "unavailable"] = "unavailable"
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


def dependency_status() -> Dependencies:
    raw_url = environ.get("MARGONO_DATABASE_URL")
    if not raw_url:
        return Dependencies(database="not_configured")

    try:
        url = make_url(raw_url)
        if url.drivername != "postgresql+psycopg":
            return Dependencies(database="unavailable")

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
                return Dependencies(database="migration_required")
            versions = connection.scalars(
                text("SELECT version_num FROM alembic_version")
            )
            if frozenset(versions) != expected_heads():
                return Dependencies(database="migration_required")
            active = connection.scalar(
                text("""
                SELECT EXISTS (
                    SELECT 1 FROM procrastinate_workers
                    WHERE last_heartbeat > now() - (:timeout * interval '1 second')
                )
            """),
                {"timeout": WORKER_TIMEOUT_SECONDS},
            )
    except (SQLAlchemyError, ValueError):
        return Dependencies(database="unavailable")

    return Dependencies(database="ready", worker="active" if active else "not_observed")
