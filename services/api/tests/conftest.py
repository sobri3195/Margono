from os import environ
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_database(monkeypatch):
    test_url = environ.get("MARGONO_TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("Set MARGONO_TEST_DATABASE_URL to run PostgreSQL migration tests.")

    schema = f"test_{uuid4().hex}"
    url = make_url(test_url)
    admin_engine = sa.create_engine(url)
    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema))

    scoped_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    scoped_engine = sa.create_engine(scoped_url)
    monkeypatch.setenv(
        "MARGONO_DATABASE_URL", scoped_url.render_as_string(hide_password=False)
    )
    try:
        yield Config(str(API_DIR / "alembic.ini")), scoped_engine, schema
    finally:
        scoped_engine.dispose()
        try:
            with admin_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        finally:
            admin_engine.dispose()
