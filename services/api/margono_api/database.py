from collections.abc import Iterator
from functools import lru_cache
from os import environ

from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from .errors import api_error


@lru_cache(maxsize=1)
def database_engine(raw_url: str) -> Engine:
    url = make_url(raw_url)
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Expected a PostgreSQL URL using psycopg.")
    return create_engine(
        url, poolclass=pool.NullPool, connect_args={"connect_timeout": 2}
    )


def database_transaction() -> Iterator[Connection]:
    raw_url = environ.get("MARGONO_DATABASE_URL")
    if not raw_url:
        raise api_error(
            503, "database_unavailable", "Configure the local PostgreSQL database."
        )
    try:
        engine = database_engine(raw_url)
    except (SQLAlchemyError, ValueError):
        raise api_error(
            503, "database_unavailable", "The local database is unavailable."
        ) from None
    try:
        with engine.begin() as connection:
            yield connection
    except SQLAlchemyError:
        raise api_error(
            503, "database_unavailable", "The local database is unavailable."
        ) from None
