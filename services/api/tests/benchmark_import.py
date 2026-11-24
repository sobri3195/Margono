"""Explicit synthetic benchmark. Run pytest -q -s tests/benchmark_import.py."""

from math import ceil
from statistics import median
from time import perf_counter

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text

from margono_api.main import app
from margono_api.passwords import hash_password

pytestmark = pytest.mark.postgres


def test_benchmark_import(isolated_database):
    config, engine, _ = isolated_database
    command.upgrade(config, "head")
    password = "synthetic-benchmark-only"
    with engine.begin() as connection:
        user = connection.scalar(
            text(
                "INSERT INTO users (username, password_hash) VALUES ('bench', :hash) RETURNING id"
            ),
            {"hash": hash_password(password)},
        )
        connection.execute(
            text(
                "INSERT INTO user_roles (user_id, role_slug) VALUES (:user, 'osint_analyst')"
            ),
            {"user": user},
        )

    samples = {"preview": [], "confirm": [], "replay": []}
    payload = {
        "content": "Nama,Unit\n"
        + "".join(f"Label {i // 2},Fixture\n" for i in range(500))
    }

    def measure(step, callback, sample):
        start = perf_counter()
        response = callback()
        elapsed = (perf_counter() - start) * 1000
        assert response.is_success, response.text
        if sample:
            samples[step].append(elapsed)
        return response.json()

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/sessions", json={"username": "bench", "password": password}
        )
        assert login.status_code == 201
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        case = client.post(
            "/api/v1/cases",
            json={
                "fixture_id": "SYN-001",
                "purpose": "Synthetic benchmark",
                "scope": "CSV only",
            },
            headers=headers,
        )
        assert case.status_code == 201
        path = f"/api/v1/cases/{case.json()['id']}/imports"
        for index in range(28):
            sample = index >= 3
            key = {**headers, "Idempotency-Key": f"benchmark-{index}"}
            preview = measure(
                "preview",
                lambda: client.post(f"{path}/preview", json=payload, headers=headers),
                sample,
            )
            assert len(preview["rows"]) == 500
            confirm = measure(
                "confirm", lambda: client.post(path, json=payload, headers=key), sample
            )
            replay = measure(
                "replay", lambda: client.post(path, json=payload, headers=key), sample
            )
            assert confirm == replay and confirm["row_count"] == 500

    for step, elapsed in samples.items():
        p95 = sorted(elapsed)[ceil(0.95 * len(elapsed)) - 1]
        print(f"{step}: n={len(elapsed)} p50={median(elapsed):.2f} ms p95={p95:.2f} ms")
