import asyncio
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from margono_api import provision
from margono_api.fixtures import CATALOG
from margono_api.main import app
from margono_api.synthetic_worker import QUEUE, run_worker

pytestmark = pytest.mark.postgres


def test_fixture_import_queue_review_report_and_recovery(
    isolated_database, monkeypatch
):
    config, engine, _ = isolated_database
    command.upgrade(config, "head")
    password = "fixture-operator-test"
    for name, role in [
        ("owner", "osint_analyst"),
        ("reviewer", "osint_analyst"),
        ("supervisor", "supervisor"),
        ("examiner", "forensic_examiner"),
        ("admin", "administrator"),
    ]:
        monkeypatch.setattr("sys.argv", ["provision", name, role])
        monkeypatch.setattr(provision, "getpass", lambda _: password)
        provision.main()

    with TestClient(app) as client:

        def login(name):
            value = client.post(
                "/api/v1/sessions", json={"username": name, "password": password}
            )
            assert value.status_code == 201, value.text
            return {"Authorization": f"Bearer {value.json()['token']}"}

        owner, reviewer, supervisor, examiner, admin = map(
            login, ("owner", "reviewer", "supervisor", "examiner", "admin")
        )
        cases = {}
        for fixture in CATALOG.cases:
            created = client.post(
                "/api/v1/cases",
                json={
                    "fixture_id": fixture.case_id,
                    "purpose": "Fixture exercise",
                    "scope": "Test data",
                },
                headers={**owner, "Idempotency-Key": f"case:{fixture.case_id}"},
            )
            assert created.status_code == 201, created.text
            case_id = created.json()["id"]
            path = f"/api/v1/cases/{case_id}"
            saved = client.post(
                f"{path}/imports",
                json={
                    "content": "Nama\nLabel berulang\nLabel berulang\n",
                    "column": "Nama",
                },
                headers={**owner, "Idempotency-Key": "fixture-batch"},
            )
            assert saved.status_code == 201, saved.text
            import_id = saved.json()["id"]
            batch = f"{path}/imports/{import_id}"
            headers = {**owner, "Idempotency-Key": "fixture-source"}
            queued = client.post(f"{batch}/jobs", headers=headers)
            assert queued.status_code == 201, queued.text
            job = queued.json()
            assert UUID(job["id"])
            assert job["status"] == "queued"
            assert (
                client.post(f"{batch}/jobs", headers=headers).json()["id"] == job["id"]
            )
            cases[fixture.case_id] = (path, case_id, batch, import_id, job["id"])

        path, case_id, batch, _, job_id = cases["SYN-001"]
        assert client.get("/api/v1/jobs", headers=reviewer).json() == []
        assert client.get("/api/v1/jobs", headers=admin).json() == []
        assert client.get(f"{path}/jobs", headers=reviewer).status_code == 404
        assert client.get(f"{batch}/details", headers=reviewer).status_code == 404
        assert (
            client.put(f"{path}/collaborators/reviewer", headers=owner).status_code
            == 403
        )
        for name in ("reviewer", "examiner"):
            assert (
                client.put(
                    f"{path}/collaborators/{name}", headers=supervisor
                ).status_code
                == 204
            )
        assert client.get(f"{path}/collaborators", headers=reviewer).json() == [
            "examiner",
            "reviewer",
        ]
        assert (
            client.get(f"{path}/reports/technical", headers=examiner).status_code == 403
        )
        assert (
            client.get("/api/v1/jobs", headers=reviewer).json()[0]["case_id"] == case_id
        )

        job_path = f"{path}/jobs/{job_id}"
        assert (
            client.patch(f"{job_path}?action=pause", headers=reviewer).json()["status"]
            == "paused"
        )
        assert (
            client.patch(f"{job_path}?action=resume", headers=reviewer).json()["status"]
            == "queued"
        )
        aborted = client.post(
            f"{batch}/jobs", headers={**owner, "Idempotency-Key": "cancel-fixture"}
        )
        assert aborted.status_code == 201, aborted.text
        cancelled_job = f"{path}/jobs/{aborted.json()['id']}"
        assert (
            client.patch(f"{cancelled_job}?action=cancel", headers=owner).json()[
                "status"
            ]
            == "cancelled"
        )
        assert (
            client.patch(f"{cancelled_job}?action=resume", headers=owner).status_code
            == 409
        )

        # Represent a process leaving a claimed job behind, then start a fresh worker.
        with engine.begin() as db:
            worker = db.scalar(
                text("""
                INSERT INTO procrastinate_workers (last_heartbeat)
                VALUES (now() - interval '1 minute') RETURNING id
            """)
            )
            claimed = db.execute(
                text(
                    "SELECT id FROM procrastinate_fetch_job_v2(ARRAY[:queue]::varchar[], :worker)"
                ),
                {"queue": QUEUE, "worker": worker},
            ).scalar_one()
            assert claimed is not None
        asyncio.run(run_worker(once=True))
        timeout_path = cases["SYN-006"][0]
        retrying = client.get(f"{timeout_path}/jobs", headers=owner).json()[0]
        assert retrying["status"] == "queued"
        assert retrying["failure_code"] == "fixture_timeout"
        assert retrying["scheduled_at"] is not None
        assert client.get(f"{timeout_path}/findings", headers=owner).json() == []
        with engine.begin() as db:
            db.execute(
                text(
                    "UPDATE procrastinate_jobs SET scheduled_at = now() WHERE status = 'todo'"
                )
            )
        asyncio.run(run_worker(once=True))
        asyncio.run(run_worker(once=True))

        for fixture_id, (path, case_id, batch, import_id, job_id) in cases.items():
            found = client.get(f"{path}/findings?verification=pending", headers=owner)
            assert found.status_code == 200, found.text
            [finding] = found.json()
            assert finding["job_id"] == job_id
            assert finding["evidence"]["fixture_id"] == fixture_id
            assert finding["evidence"]["import_id"] == import_id
            assert finding["evidence"]["indicator"] == "margono.test"
            assert "Label berulang" not in found.text
            review = f"{path}/findings/{finding['id']}/review"
            verification = {"SYN-009": "inconclusive", "SYN-010": "rejected"}.get(
                fixture_id, "verified"
            )
            decision = {
                "expected": "pending",
                "verification": verification,
                "note": "Sesuai fixture",
            }
            actor = reviewer if fixture_id == "SYN-001" else owner
            accepted = client.patch(review, json=decision, headers=actor)
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["threat_status"] == finding["threat_status"]
            assert accepted.json()["severity"] == finding["severity"]
            assert (
                client.patch(review, json=decision, headers=actor).json()
                == accepted.json()
            )
            assert (
                client.patch(
                    review,
                    json={
                        **decision,
                        "verification": "verified"
                        if verification == "rejected"
                        else "rejected",
                    },
                    headers=owner,
                ).status_code
                == 409
            )
            executive = client.get(f"{path}/reports/executive", headers=owner).json()
            technical = client.get(f"{path}/reports/technical", headers=owner).json()
            assert executive["case_id"] == technical["case_id"] == case_id
            assert executive["mode"] == technical["mode"] == "SYNTHETIC"
            assert "findings" not in executive
            assert technical["findings"] == [accepted.json()]
            details = client.get(f"{batch}/details", headers=owner).json()
            assert len(details["rows"]) == 2
            assert all(row["duplicate"] for row in details["rows"])
            assert {
                "import.confirmed",
                "job.source.queued",
                "job.source.completed",
                f"finding.{verification}",
            } <= {event["action"] for event in details["events"]}

        path = cases["SYN-001"][0]
        assert (
            client.delete(
                f"{path}/collaborators/reviewer", headers=supervisor
            ).status_code
            == 204
        )
        assert client.get(f"{path}/findings", headers=reviewer).status_code == 404
        assert client.get("/api/v1/jobs", headers=reviewer).json() == []

        batch = cases["SYN-001"][2]
        extra = client.post(
            f"{batch}/jobs", headers={**owner, "Idempotency-Key": "manual-retry"}
        )
        assert extra.status_code == 201, extra.text
        job_id = extra.json()["id"]
        assert (
            client.patch(f"{path}/status?status=closed", headers=supervisor).status_code
            == 200
        )
        asyncio.run(run_worker(once=True))
        [failed] = [
            job
            for job in client.get(f"{path}/jobs", headers=owner).json()
            if job["id"] == job_id
        ]
        assert (failed["status"], failed["failure_code"]) == ("failed", "case_closed")
        assert (
            client.patch(
                f"{path}/jobs/{job_id}?action=retry", headers=owner
            ).status_code
            == 409
        )
        assert (
            client.patch(f"{path}/status?status=open", headers=supervisor).status_code
            == 200
        )
        assert (
            client.patch(f"{path}/jobs/{job_id}?action=retry", headers=owner).json()[
                "status"
            ]
            == "queued"
        )
        asyncio.run(run_worker(once=True))
        [recovered] = [
            job
            for job in client.get(f"{path}/jobs", headers=owner).json()
            if job["id"] == job_id
        ]
        assert recovered["status"] == "completed"

    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text("UPDATE synthetic_findings SET evidence = 'changed'"))


def test_fixture_device_consent_outcomes_and_reports(isolated_database, monkeypatch):
    config, engine, _ = isolated_database
    command.upgrade(config, "head")
    for name, role in (
        ("examiner", "forensic_examiner"),
        ("other", "forensic_examiner"),
        ("supervisor", "supervisor"),
    ):
        monkeypatch.setattr("sys.argv", ["provision", name, role])
        monkeypatch.setattr(provision, "getpass", lambda _: "synthetic-fixture-test")
        provision.main()

    with TestClient(app) as client:

        def login(name):
            response = client.post(
                "/api/v1/sessions",
                json={"username": name, "password": "synthetic-fixture-test"},
            )
            assert response.status_code == 201, response.text
            return {"Authorization": f"Bearer {response.json()['token']}"}

        examiner = login("examiner")
        other = login("other")
        supervisor = login("supervisor")
        paths = {}
        for fixture_id in [
            "SYN-011",
            "SYN-012",
            "SYN-013",
            "SYN-014",
            "SYN-015",
            "SYN-018",
            "SYN-019",
        ]:
            created = client.post(
                "/api/v1/cases",
                json={
                    "fixture_id": fixture_id,
                    "purpose": "Simulasi",
                    "scope": "Fixture",
                },
                headers={**examiner, "Idempotency-Key": fixture_id},
            )
            assert created.status_code == 201, created.text
            case_id = created.json()["id"]
            case = f"/api/v1/cases/{case_id}"
            path = f"{case}/devices"
            description = client.get(path, headers=examiner)
            assert description.status_code == 200, description.text
            assert description.json()["sessions"] == []
            assert "fiktif" in description.json()["disclosure"]
            assert client.get(path, headers=other).status_code == 404
            status = "declined" if fixture_id == "SYN-013" else "granted"
            keyed = {**examiner, "Idempotency-Key": "fixture-consent"}
            recovery_path = f"{path}/decision"
            assert client.get(recovery_path, headers=keyed).json() is None
            consent = client.post(
                path,
                json={"status": status},
                headers=keyed,
            )
            assert consent.status_code == 201, consent.text
            recovered = client.get(recovery_path, headers=keyed)
            assert recovered.json() == consent.json()
            assert recovered.headers["Cache-Control"] == "no-store"
            assert (
                client.post(path, json={"status": status}, headers=keyed).json()
                == consent.json()
            )
            session = f"{path}/{consent.json()['id']}"
            queue = client.post(f"{session}/jobs", headers=examiner)
            assert client.post(f"{session}/jobs", headers=other).status_code == 404
            if status == "declined":
                assert queue.status_code == 409
            else:
                assert queue.status_code == 201, queue.text
                assert (
                    client.post(f"{session}/jobs", headers=examiner).json()["id"]
                    == queue.json()["id"]
                )
            if fixture_id == "SYN-014":
                revoked = client.post(f"{session}/revoke", headers=examiner)
                assert revoked.status_code == 200, revoked.text
                assert revoked.json()["status"] == "revoked"
                assert client.get(recovery_path, headers=keyed).json() == revoked.json()
                assert (
                    client.post(f"{session}/revoke", headers=examiner).json()
                    == revoked.json()
                )
            paths[fixture_id] = case

        asyncio.run(run_worker(once=True))
        for fixture_id, case in paths.items():
            scopes = client.get(f"{case}/devices", headers=examiner).json()
            [item] = scopes["sessions"]
            jobs = client.get(f"{case}/jobs", headers=examiner).json()
            technical = client.get(f"{case}/reports/technical", headers=examiner)
            assert technical.status_code == 200, technical.text
            executive = client.get(f"{case}/reports/executive", headers=examiner).json()
            assert "device_jobs" not in executive
            assert technical.json()["case_id"] == executive["case_id"]
            if fixture_id == "SYN-013":
                assert item["status"] == "declined" and item["job_id"] is None
                assert jobs == []
                continue
            [job] = jobs
            [evidence_job] = technical.json()["device_jobs"]
            assert evidence_job["id"] == job["id"]
            if fixture_id in {"SYN-014", "SYN-015"}:
                assert item["evidence"] is None
                expect = (
                    ("cancelled", "consent_revoked")
                    if fixture_id == "SYN-014"
                    else ("failed", "fixture_disconnected")
                )
                assert (job["status"], job["failure_code"]) == expect
            else:
                assert job["status"] == "completed"
                expected = (
                    "unsupported" if fixture_id == "SYN-012" else "sample_available"
                )
                assert item["evidence"]["result"] == expected
                assert item["evidence_sha256"] == evidence_job["evidence_sha256"]

        path = paths["SYN-015"]
        [item] = client.get(f"{path}/devices", headers=examiner).json()["sessions"]
        job_path = f"{path}/jobs/{item['job_id']}?action=retry"
        assert client.patch(job_path, headers=supervisor).status_code == 403
        assert client.patch(job_path, headers=other).status_code == 404
        retry = client.patch(job_path, headers=examiner)
        assert retry.status_code == 200, retry.text
        assert retry.json()["status"] == "queued"
        assert retry.json()["id"] == item["job_id"]
        assert retry.json()["consent_active"] is True
        assert client.patch(job_path, headers=examiner).status_code == 409
        asyncio.run(run_worker(once=True))
        [job] = client.get(f"{path}/jobs", headers=examiner).json()
        assert job["failure_code"] == "fixture_disconnected"
        assert (
            client.post(
                f"{path}/devices/{item['id']}/revoke", headers=examiner
            ).status_code
            == 200
        )
        denied = client.patch(job_path, headers=examiner)
        assert denied.status_code == 409
        assert denied.json()["code"] == "consent_required"
        assert (
            client.get(f"{path}/jobs", headers=examiner).json()[0]["consent_active"]
            is False
        )

        path = paths["SYN-011"]
        assert (
            client.put(f"{path}/collaborators/other", headers=supervisor).status_code
            == 204
        )
        wrong_actor = client.get(
            f"{path}/devices/decision",
            headers={**other, "Idempotency-Key": "fixture-consent"},
        )
        assert wrong_actor.status_code == 200 and wrong_actor.json() is None

    with engine.connect() as db:
        assert (
            db.scalar(
                text("SELECT count(*) FROM consent_decisions WHERE status = 'revoked'")
            )
            == 2
        )
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM audit_events WHERE action = 'device.consent.granted'"
                )
            )
            == 6
        )
    with pytest.raises(IntegrityError), engine.begin() as db:
        db.execute(text("DELETE FROM synthetic_device_evidence"))


def test_activity_pages_include_the_101st_job_and_pending_finding(
    isolated_database, monkeypatch
):
    config, _, _ = isolated_database
    command.upgrade(config, "head")
    password = "fixture-operator-test"
    for name in ("owner", "other"):
        monkeypatch.setattr("sys.argv", ["provision", name, "osint_analyst"])
        monkeypatch.setattr(provision, "getpass", lambda _: password)
        provision.main()

    with TestClient(app) as client:

        def login(name):
            result = client.post(
                "/api/v1/sessions", json={"username": name, "password": password}
            )
            return {"Authorization": f"Bearer {result.json()['token']}"}

        owner, other = login("owner"), login("other")
        created = client.post(
            "/api/v1/cases",
            headers=owner,
            json={"fixture_id": "SYN-001", "purpose": "Review", "scope": "Fixture"},
        )
        path = f"/api/v1/cases/{created.json()['id']}"
        batch = client.post(
            f"{path}/imports",
            headers={**owner, "Idempotency-Key": "batch"},
            json={"content": "Nama\nFixture\n"},
        )
        for index in range(101):
            job = client.post(
                f"{path}/imports/{batch.json()['id']}/jobs",
                headers={**owner, "Idempotency-Key": f"job-{index}"},
            )
            assert job.status_code == 201, job.text
        asyncio.run(run_worker(once=True))

        for resource, parameter, filters in (
            ("jobs", "before", {}),
            ("findings", "after", {"verification": "pending"}),
        ):
            url = f"{path}/{resource}"
            first = client.get(url, headers=owner, params=filters)
            assert first.headers["X-Total-Count"] == "101"
            assert len(first.json()) == 100
            cursor = first.headers["X-Next-Cursor"]
            assert cursor == first.json()[-1]["id"]
            following = client.get(
                url, headers=owner, params={**filters, parameter: cursor}
            )
            assert following.headers["X-Total-Count"] == "101"
            assert "X-Next-Cursor" not in following.headers
            [last] = following.json()
            assert last["id"] not in {item["id"] for item in first.json()}
            assert (
                client.get(url, headers=owner, params={parameter: uuid4()}).status_code
                == 404
            )
            assert (
                client.get(url, headers=other, params={parameter: cursor}).status_code
                == 404
            )

        portal = client.get("/api/v1/jobs", headers=owner)
        assert len(portal.json()) == 100 and portal.headers["X-Total-Count"] == "101"
        assert portal.headers["X-Pending-Review-Count"] == "101"
        assert portal.headers["X-Failed-Count"] == "0"
        inaccessible = client.get("/api/v1/jobs", headers=other)
        assert (
            inaccessible.json() == [] and inaccessible.headers["X-Total-Count"] == "0"
        )
        reviewed = client.patch(
            f"{path}/findings/{last['id']}/review",
            headers=owner,
            json={"expected": "pending", "verification": "verified", "note": "Fixture"},
        )
        assert reviewed.json()["verification"] == "verified"
        pending = client.get(f"{path}/findings?verification=pending", headers=owner)
        assert pending.headers["X-Total-Count"] == "100"
        assert "X-Next-Cursor" not in pending.headers
        assert all(item["id"] != last["id"] for item in pending.json())
