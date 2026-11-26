from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from os import environ

from fastapi import HTTPException
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from .errors import ApiError, api_error


class DatabaseUnavailable(HTTPException):
    def __init__(self, message: str = "The local database is unavailable.") -> None:
        super().__init__(503, ApiError(code="database_unavailable", message=message))


@lru_cache(maxsize=1)
def database_engine(raw_url: str) -> Engine:
    url = make_url(raw_url)
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Expected a PostgreSQL URL using psycopg.")
    return create_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 2},
        hide_parameters=True,
    )


@contextmanager
def open_database() -> Iterator[Connection]:
    raw_url = environ.get("MARGONO_DATABASE_URL")
    if not raw_url:
        raise DatabaseUnavailable("Configure the local PostgreSQL database.")
    try:
        engine = database_engine(raw_url)
        connection = engine.connect()
    except (SQLAlchemyError, ValueError):
        raise DatabaseUnavailable() from None
    try:
        with connection, connection.begin():
            yield connection
    except DBAPIError as error:
        state = getattr(error.orig, "sqlstate", "") or ""
        if (
            error.connection_invalidated
            or state.startswith("08")
            or state in {"57P01", "57P02", "57P03"}
        ):
            raise DatabaseUnavailable() from None
        if state.startswith("22") or state in {"23502", "23514"}:
            raise api_error(
                422, "invalid_request", "Request data is invalid."
            ) from None
        if isinstance(error, IntegrityError):
            raise api_error(
                409, "data_conflict", "The requested change conflicts with stored data."
            ) from None
        raise


def database_transaction() -> Iterator[Connection]:
    with open_database() as connection:
        yield connection
