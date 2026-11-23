from os import environ

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

try:
    database_url = make_url(environ.get("MARGONO_DATABASE_URL", ""))
except ArgumentError:
    raise RuntimeError("Set MARGONO_DATABASE_URL to a PostgreSQL URL.") from None
if database_url.drivername != "postgresql+psycopg":
    raise RuntimeError("MARGONO_DATABASE_URL must use the postgresql+psycopg driver.")

if context.is_offline_mode():
    context.configure(url=database_url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
