import pytest
from fastapi.testclient import TestClient

from margono_api import operations
from margono_api.main import app


@pytest.mark.parametrize(
    ("field", "invalid"), [("purpose", "Fixture\x00"), ("scope", "Trial\x1fcase")]
)
def test_case_rejects_control_characters_before_database(field, invalid, monkeypatch):
    def fail():
        pytest.fail("Invalid case input must not open a database transaction.")

    monkeypatch.setattr(operations, "open_database", fail)
    payload = {
        "fixture_id": "SYN-001",
        "purpose": "Simulation",
        "scope": "Fixture",
        field: invalid,
    }
    response = TestClient(app).post("/api/v1/cases", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
