from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from margono_api import main
from margono_api.fixtures import generate_variation

client = TestClient(main.app)
PLAN_URL = "/api/v1/simulation/plans"


def test_plan_matches_seeded_generator_and_is_read_only():
    response = client.get(PLAN_URL, params={"seed": 42})
    assert response.status_code == 200
    assert response.json() == generate_variation(42).model_dump(mode="json")
    assert client.get(PLAN_URL, params={"seed": 42}).json() == response.json()
    assert len(response.json()["case_ids"]) == 6
    assert client.post(PLAN_URL, json={"seed": 42}).status_code == 405


@pytest.mark.parametrize(
    "params", [{}, {"seed": "private-value"}, {"seed": 2**31}, {"seed": -(2**31) - 1}]
)
def test_plan_validation_has_stable_safe_error(params):
    response = client.get(PLAN_URL, params=params)
    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_request",
        "message": "Request parameters are invalid.",
    }
    assert UUID(response.headers["X-Correlation-ID"]).version == 4


@pytest.mark.parametrize("field", ["name", "profile", "source_url", "device_id"])
def test_plan_rejects_inputs_outside_synthetic_scope(field, monkeypatch):
    def unexpected_plan(_seed: int):
        pytest.fail("Rejected inputs must not reach the plan generator.")

    monkeypatch.setattr(main, "generate_variation", unexpected_plan)
    response = client.get(PLAN_URL, params={"seed": 42, field: "synthetic-placeholder"})
    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_request",
        "message": "Request parameters are invalid.",
    }


def test_case_timestamps_use_rfc3339_utc():
    response = client.get("/api/v1/simulation/cases/SYN-001")
    assert response.json()["created_at"] == "2026-01-01T00:00:00Z"
    catalog = client.get("/api/v1/simulation/catalog").json()
    assert catalog["cases"][0]["created_at"] == response.json()["created_at"]


def test_correlation_id_is_created_by_server():
    incoming_id = str(uuid4())
    response = client.get(
        PLAN_URL, params={"seed": 42}, headers={"X-Correlation-ID": incoming_id}
    )
    assert UUID(response.headers["X-Correlation-ID"]).version == 4
    assert response.headers["X-Correlation-ID"] != incoming_id


def test_router_errors_follow_contract_and_keep_allow_header():
    missing = client.get("/api/v1/unknown")
    assert missing.status_code == 404
    assert missing.json() == {"code": "not_found", "message": "Resource not found."}

    wrong_method = client.post(PLAN_URL)
    assert wrong_method.status_code == 405
    assert wrong_method.json() == {
        "code": "method_not_allowed",
        "message": "Method not allowed.",
    }
    assert "GET" in wrong_method.headers["Allow"]


def test_internal_errors_have_correlation_id_and_hide_details(monkeypatch, caplog):
    def fail(_seed: int):
        raise RuntimeError("private detail")

    monkeypatch.setattr(main, "generate_variation", fail)
    response = TestClient(main.app, raise_server_exceptions=False).get(
        PLAN_URL, params={"seed": 42}
    )
    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "An internal error occurred.",
    }
    assert UUID(response.headers["X-Correlation-ID"]).version == 4

    assert response.headers["X-Correlation-ID"] in caplog.text
    assert "private detail" not in caplog.text


def test_openapi_declares_the_error_contract():
    schema = client.get("/openapi.json").json()
    responses = schema["paths"][PLAN_URL]["get"]["responses"]
    for status in ("422", "500"):
        assert responses[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ApiError",
        }
