from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from margono_api import readiness
from margono_api.main import app


def test_liveness_and_catalog_work_without_postgres(monkeypatch):
    monkeypatch.delenv("MARGONO_DATABASE_URL", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json() == {
            "status": "ok",
            "mode": "SYNTHETIC",
        }
        assert client.get("/api/v1/simulation/catalog").status_code == 200
        response = client.get("/api/v1/readiness")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "mode": "SYNTHETIC",
        "pilot": "blocked",
        "checks": {
            "database": "not_configured",
            "worker": "not_implemented",
            "sync": "not_implemented",
        },
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert UUID(response.headers["X-Correlation-ID"]).version == 4


def test_database_failure_reports_status_without_details(monkeypatch, caplog):
    def fail(*_args, **_kwargs):
        raise OperationalError(None, None, RuntimeError("sensitive driver detail"))

    monkeypatch.setenv("MARGONO_DATABASE_URL", "postgresql+psycopg://localhost/db")
    monkeypatch.setattr(readiness, "create_engine", fail)
    response = TestClient(app).get("/api/v1/readiness")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"
    assert response.headers["X-Correlation-ID"] in caplog.text
    assert "sensitive driver detail" not in response.text
    assert "sensitive driver detail" not in caplog.text


@pytest.mark.parametrize("mode", ["pilot", "production", "simulaton"])
def test_unsupported_mode_blocks_startup(mode, monkeypatch):
    monkeypatch.setenv("MARGONO_MODE", mode)
    with (
        pytest.raises(RuntimeError, match="supports MARGONO_MODE=simulation only"),
        TestClient(app),
    ):
        pass
