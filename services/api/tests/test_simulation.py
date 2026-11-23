from uuid import UUID

from fastapi.testclient import TestClient

from margono_api.fixtures import CATALOG, generate_variation
from margono_api.main import app

client = TestClient(app)


def test_health_and_correlation_ids():
    first = client.get("/api/v1/health")
    second = client.get("/api/v1/health")
    assert first.status_code == 200
    assert first.json() == {"status": "ok", "mode": "SYNTHETIC"}
    assert UUID(first.headers["X-Correlation-ID"]).version == 4
    assert first.headers["X-Correlation-ID"] != second.headers["X-Correlation-ID"]


def test_catalog_contains_twenty_distinct_synthetic_cases_and_known_references():
    response = client.get("/api/v1/simulation/catalog")
    assert response.status_code == 200
    catalog = response.json()
    cases, sources, devices = (catalog[key] for key in ("cases", "sources", "devices"))
    assert len(cases) == len({case["case_id"] for case in cases}) == 20
    assert {case["workspace"] for case in cases} == {"web", "usb"}
    assert catalog["mode"] == "SYNTHETIC"
    assert all(row["mode"] == "SYNTHETIC" for row in cases + sources + devices)
    assert {case["reference_id"] for case in cases if case["workspace"] == "web"} == {
        source["profile_id"] for source in sources
    }
    assert {case["reference_id"] for case in cases if case["workspace"] == "usb"} == {
        device["profile_id"] for device in devices
    }
    assert {device["platform"]: device["result"] for device in devices} == {
        "Android": "sample_available",
        "iPhone": "unsupported",
    }


def test_duplicate_labels_are_distinct_case_resources():
    first = client.get("/api/v1/simulation/cases/SYN-002")
    second = client.get("/api/v1/simulation/cases/SYN-003")
    assert first.status_code == second.status_code == 200
    assert first.json()["label"] == second.json()["label"]
    assert first.json()["case_id"] != second.json()["case_id"]


def test_missing_case_returns_stable_error_and_does_not_reflect_input():
    response = client.get("/api/v1/simulation/cases/not-a-fixture")
    assert response.status_code == 404
    assert response.json() == {
        "code": "case_not_found",
        "message": "Synthetic case not found.",
    }
    assert "X-Correlation-ID" in response.headers


def test_simulation_routes_reject_writes():
    assert client.post("/api/v1/simulation/catalog", json={}).status_code == 405
    assert client.put("/api/v1/simulation/cases/SYN-001", json={}).status_code == 405


def test_seeded_variation_preserves_fixed_fixtures():
    variation = generate_variation(42)
    assert variation == generate_variation(42)
    assert variation != generate_variation(43)
    assert len(variation.case_ids) == len(set(variation.case_ids)) == 6
    web_ids = {case.case_id for case in CATALOG.cases if case.workspace == "web"}
    usb_ids = {case.case_id for case in CATALOG.cases if case.workspace == "usb"}
    assert set(variation.case_ids[:3]) <= web_ids
    assert set(variation.case_ids[3:]) <= usb_ids
