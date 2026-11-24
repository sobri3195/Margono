import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from margono_api.database import open_database


def test_invalid_database_configuration_is_unavailable(monkeypatch):
    monkeypatch.setenv("MARGONO_DATABASE_URL", "sqlite://")
    with pytest.raises(HTTPException) as failed, open_database():
        pytest.fail("The transaction must not start with an unsupported driver.")
    assert failed.value.status_code == 503
    assert failed.value.detail.code == "database_unavailable"


@pytest.mark.postgres
def test_data_errors_are_not_database_unavailability(isolated_database):
    with pytest.raises(HTTPException) as failed, open_database() as db:
        db.execute(text("SELECT CAST('synthetic' AS integer)"))
    assert failed.value.status_code == 422
    assert failed.value.detail.code == "invalid_request"

    with pytest.raises(ProgrammingError), open_database() as db:
        db.execute(text("SELECT missing_synthetic_column"))
    with open_database() as db:
        assert db.scalar(text("SELECT 1")) == 1
