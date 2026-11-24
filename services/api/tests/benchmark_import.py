"""Opt-in synthetic benchmarks. Run pytest -q -s tests/benchmark_import.py."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from statistics import median
from time import perf_counter

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text

from margono_api.main import app
from margono_api.passwords import hash_password
from margono_api.synthetic_worker import run_worker

pytestmark = pytest.mark.postgres

WARMUP = 3
SAMPLES = 25
CONCURRENCY = 4
PAYLOAD = {
    "content": "Nama,Unit\n" + "".join(f"Label {i // 2},Fixture\n" for i in range(500))
}


@pytest.fixture
def benchmark_operator(isolated_database):
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

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/sessions", json={"username": "bench", "password": password}
        )
        assert login.status_code == 201
        yield engine, client, {"Authorization": f"Bearer {login.json()['token']}"}


def create_benchmark_case(client, headers):
    case = client.post(
        "/api/v1/cases",
        json={
            "fixture_id": "SYN-001",
            "purpose": "Synthetic benchmark",
            "scope": "Fixture workflow",
        },
        headers=headers,
    )
    assert case.status_code == 201, case.text
    return f"/api/v1/cases/{case.json()['id']}"


def measure_request(callback):
    start = perf_counter()
    response = callback()
    elapsed = (perf_counter() - start) * 1000
    assert response.is_success, response.text
    return response.json(), elapsed


def log_timings(step, elapsed, *, seconds=None):
    p95 = sorted(elapsed)[ceil(0.95 * len(elapsed)) - 1]
    speed = f" rate={len(elapsed) / seconds:.2f}/s" if seconds is not None else ""
    print(
        f"{step}: n={len(elapsed)} p50={median(elapsed):.2f} ms p95={p95:.2f} ms{speed}"
    )


def test_benchmark_import(benchmark_operator):
    _, client, headers = benchmark_operator
    path = f"{create_benchmark_case(client, headers)}/imports"
    samples = {"preview": [], "confirm": [], "replay": []}
    for index in range(WARMUP + SAMPLES):
        key = {**headers, "Idempotency-Key": f"serial-{index}"}
        preview, preview_ms = measure_request(
            lambda: client.post(f"{path}/preview", json=PAYLOAD, headers=headers)
        )
        confirm, confirm_ms = measure_request(
            lambda: client.post(path, json=PAYLOAD, headers=key)
        )
        replay, replay_ms = measure_request(
            lambda: client.post(path, json=PAYLOAD, headers=key)
        )
        assert len(preview["rows"]) == 500
        assert confirm == replay and confirm["row_count"] == 500
        if index >= WARMUP:
            samples["preview"].append(preview_ms)
            samples["confirm"].append(confirm_ms)
            samples["replay"].append(replay_ms)

    for step, elapsed in samples.items():
        log_timings(step, elapsed)


def run_phase(threads, step, items, request, *, log):
    start = perf_counter()
    results = list(
        threads.map(lambda item: measure_request(lambda: request(item)), items)
    )
    seconds = perf_counter() - start
    if log:
        log_timings(step, [elapsed for _, elapsed in results], seconds=seconds)
    return [body for body, _ in results]


def process_jobs(engine, jobs, *, log):
    start = perf_counter()
    asyncio.run(run_worker(once=True))
    drain_seconds = perf_counter() - start
    with engine.connect() as connection:
        events = connection.execute(
            text("""
                SELECT j.status,
                    extract(epoch FROM (
                        max(e.at) FILTER (WHERE e.type = 'succeeded')
                        - min(e.at) FILTER (WHERE e.type = 'started')
                    )) * 1000 AS processing_ms,
                    extract(epoch FROM (
                        max(e.at) FILTER (WHERE e.type = 'succeeded')
                        - min(e.at) FILTER (WHERE e.type = 'deferred')
                    )) * 1000 AS queued_to_finished_ms,
                    count(*) FILTER (WHERE e.type = 'deferred_for_retry') AS retries
                FROM jobs j JOIN procrastinate_events e ON e.job_id = j.queue_id
                WHERE j.id = ANY(CAST(:jobs AS uuid[]))
                GROUP BY j.id, j.status
            """),
            {"jobs": [job["id"] for job in jobs]},
        ).all()
    assert len(events) == len(jobs)
    assert all(
        event.status == "completed" and event.processing_ms >= 0 for event in events
    )
    if log:
        log_timings("worker processing", [event.processing_ms for event in events])
        log_timings(
            "queue to finished", [event.queued_to_finished_ms for event in events]
        )
        retries = sum(event.retries for event in events)
        print(
            f"worker drain: {len(events) / drain_seconds:.2f} jobs/s, retries={retries}"
        )


def benchmark_workflow(engine, client, headers, paths, *, log):
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as threads:
        previews = run_phase(
            threads,
            "preview",
            paths,
            lambda case: client.post(
                f"{case}/imports/preview", json=PAYLOAD, headers=headers
            ),
            log=log,
        )
        assert all(len(preview["rows"]) == 500 for preview in previews)

        def confirm_import(item):
            index, case = item
            return client.post(
                f"{case}/imports",
                json=PAYLOAD,
                headers={**headers, "Idempotency-Key": f"batch-{index}"},
            )

        imports = run_phase(
            threads, "confirm", enumerate(paths), confirm_import, log=log
        )
        assert all(batch["row_count"] == 500 for batch in imports)
        assert len({batch["id"] for batch in imports}) == len(paths)
        replays = run_phase(
            threads, "replay", enumerate(paths), confirm_import, log=log
        )
        assert replays == imports

        jobs = run_phase(
            threads,
            "enqueue",
            zip(paths, imports, strict=True),
            lambda item: client.post(
                f"{item[0]}/imports/{item[1]['id']}/jobs",
                headers={**headers, "Idempotency-Key": item[1]["id"]},
            ),
            log=log,
        )
        process_jobs(engine, jobs, log=log)

        finding_ids = {}
        for case in dict.fromkeys(paths):
            findings = client.get(
                f"{case}/findings?verification=pending", headers=headers
            )
            assert findings.status_code == 200
            finding_ids.update(
                {finding["job_id"]: finding["id"] for finding in findings.json()}
            )
        assert len(finding_ids) == len(jobs)

        decisions = run_phase(
            threads,
            "review",
            zip(paths, jobs, strict=True),
            lambda item: client.patch(
                f"{item[0]}/findings/{finding_ids[item[1]['id']]}/review",
                json={
                    "expected": "pending",
                    "verification": "verified",
                    "note": "Synthetic fixture",
                },
                headers=headers,
            ),
            log=log,
        )
        assert all(decision["verification"] == "verified" for decision in decisions)

        for template in ("executive", "technical"):
            reports = run_phase(
                threads,
                f"report {template}",
                paths,
                lambda case: client.get(f"{case}/reports/{template}", headers=headers),
                log=log,
            )
            for case, report in zip(paths, reports, strict=True):
                assert report["case_id"] == case.rsplit("/", 1)[-1]
                assert report["mode"] == "SYNTHETIC" and report["template"] == template
                assert sum(item["count"] for item in report["summary"]) == paths.count(
                    case
                )


@pytest.mark.parametrize("scope", ["separate-cases", "shared-case"])
def test_benchmark_concurrent_workflow(benchmark_operator, scope):
    engine, client, headers = benchmark_operator
    warmup = create_benchmark_case(client, headers)
    benchmark_workflow(engine, client, headers, [warmup] * WARMUP, log=False)
    count = 1 if scope == "shared-case" else SAMPLES
    paths = [create_benchmark_case(client, headers) for _ in range(count)]
    print(f"\nworkflow: {scope}, clients={CONCURRENCY}, batches={SAMPLES}, rows=500")
    benchmark_workflow(engine, client, headers, paths * (SAMPLES // count), log=True)
