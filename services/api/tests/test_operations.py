from hashlib import sha256
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from margono_api import provision
from margono_api.main import app

pytestmark = pytest.mark.postgres


def test_synthetic_case_with_scoped_sessions_and_immutable_csv(
    isolated_database, monkeypatch
):
    config, engine, _ = isolated_database
    command.upgrade(config, "head")
    password = "synthetic-test-only"
    for username, role in (
        ("owner", "osint_analyst"),
        ("other", "osint_analyst"),
        ("admin", "administrator"),
        ("supervisor", "supervisor"),
    ):
        monkeypatch.setattr("sys.argv", ["provision", username, role])
        monkeypatch.setattr(provision, "getpass", lambda _: password)
        provision.main()

    with TestClient(app) as client:

        def login(username):
            response = client.post(
                "/api/v1/sessions", json={"username": username, "password": password}
            )
            assert response.status_code == 201, response.text
            assert response.headers["Cache-Control"] == "no-store"
            return {"Authorization": f"Bearer {response.json()['token']}"}

        assert client.get("/api/v1/cases").status_code == 401
        assert (
            client.post(
                "/api/v1/sessions", json={"username": "owner", "password": "wrong"}
            ).status_code
            == 401
        )

        owner, other, admin, supervisor = [
            login(name) for name in ("owner", "other", "admin", "supervisor")
        ]
        payload = {"fixture_id": "SYN-001", "purpose": "Exercise", "scope": "Fixture"}
        assert (
            client.post(
                "/api/v1/cases", json={**payload, "purpose": " \t"}, headers=owner
            ).status_code
            == 422
        )
        assert (
            client.post("/api/v1/cases", json=payload, headers=admin).status_code == 403
        )
        assert (
            client.post(
                "/api/v1/cases",
                json={**payload, "fixture_id": "SYN-999"},
                headers=owner,
            ).status_code
            == 404
        )
        created = client.post("/api/v1/cases", json=payload, headers=owner)
        assert created.status_code == 201, created.text
        case = created.json()
        path = f"/api/v1/cases/{case['id']}"
        assert case["synthetic_fixture_id"] == "SYN-001"
        assert client.get(path, headers=other).status_code == 404
        assert client.get(path, headers=admin).status_code == 403
        assert client.get("/api/v1/cases", headers=other).json() == []
        assert client.get(path, headers=supervisor).json() == case

        raw = "Nama,Unit\nLabel A,1\nlabel a,2\n,3\n"
        csv = {"content": raw}
        import_path = f"{path}/imports"
        assert (
            client.post(f"{import_path}/preview", json=csv, headers=other).status_code
            == 404
        )
        assert (
            client.post(f"{import_path}/columns", json=csv, headers=other).status_code
            == 404
        )
        columns = client.post(f"{import_path}/columns", json=csv, headers=owner)
        assert columns.json() == {"columns": ["Nama", "Unit"]}
        preview = client.post(f"{import_path}/preview", json=csv, headers=owner)
        assert preview.status_code == 200, preview.text
        assert [row["duplicate"] for row in preview.json()["rows"]] == [
            True,
            True,
            False,
        ]
        assert [row["status"] for row in preview.json()["rows"]] == [
            "valid",
            "valid",
            "invalid",
        ]
        assert (
            client.post(
                f"{import_path}/preview", json={"content": 'Nama\n"bad'}, headers=owner
            ).status_code
            == 422
        )
        assert client.post(import_path, json=csv, headers=owner).status_code == 422

        keyed = {**owner, "Idempotency-Key": "synthetic-001"}
        first = client.post(import_path, json=csv, headers=keyed)
        assert first.status_code == 201, first.text
        stored = first.json()
        assert (
            stored["row_count"] == 3
            and stored["valid_count"] == 2
            and stored["invalid_count"] == 1
            and stored["sha256"] == sha256(raw.encode()).hexdigest()
        )
        assert client.post(import_path, json=csv, headers=keyed).json() == stored
        assert (
            client.post(
                import_path, json={**csv, "column": "Unit"}, headers=keyed
            ).status_code
            == 409
        )
        assert client.get(import_path, headers=other).status_code == 404
        page = client.get(import_path, headers=supervisor).json()
        assert page["next_cursor"] is None
        summary = page["items"][0]
        assert summary["id"] == stored["id"]
        assert summary["selected_column"] == "Nama"
        assert summary["sha256"] == stored["sha256"]
        assert summary["invalid_count"] == 1
        evidence = f"{import_path}/{stored['id']}/evidence"
        assert client.get(evidence, headers=other).status_code == 404
        retrieved = client.get(evidence, headers=supervisor)
        assert retrieved.content == raw.encode()
        assert retrieved.headers["X-Content-SHA256"] == stored["sha256"]

        assert (
            client.patch(f"{path}/status?status=closed", headers=owner).status_code
            == 403
        )
        closed = client.patch(f"{path}/status?status=closed", headers=supervisor)
        assert closed.status_code == 200, closed.text
        assert closed.json()["status"] == "closed" and closed.json()["closed_at"]
        assert client.post(import_path, json=csv, headers=keyed).json() == stored
        assert (
            client.post(
                import_path, json=csv, headers={**keyed, "Idempotency-Key": "other"}
            ).status_code
            == 409
        )
        reopened = client.patch(f"{path}/status?status=open", headers=supervisor)
        assert reopened.status_code == 200 and reopened.json()["closed_at"] is None

        assert (
            client.delete("/api/v1/sessions/current", headers=owner).status_code == 204
        )
        assert client.get(path, headers=owner).status_code == 401
        with engine.begin() as db:
            db.execute(text("UPDATE user_sessions SET expires_at = now()"))
        assert client.get(path, headers=supervisor).status_code == 401

    with engine.begin() as db:
        assert db.scalar(text("SELECT count(*) FROM imports")) == 1
        assert db.scalar(text("SELECT count(*) FROM import_rows")) == 3
        assert (
            db.scalar(
                text(
                    "SELECT count(*) FROM audit_events WHERE action = 'import.confirmed'"
                )
            )
            == 1
        )
        with (
            pytest.raises(IntegrityError, match="Import evidence cannot be edited"),
            db.begin_nested(),
        ):
            db.execute(text("DELETE FROM import_evidence"))
        with (
            pytest.raises(IntegrityError, match="ck_import_evidence_hash"),
            db.begin_nested(),
        ):
            extra = db.scalar(
                text(
                    "INSERT INTO imports (case_id, submitted_by_id, source_ref) "
                    "SELECT id, owner_id, 'fixture' FROM cases LIMIT 1 RETURNING id"
                )
            )
            db.execute(
                text("INSERT INTO import_evidence VALUES (:id, :content, :sha)"),
                dict(id=extra, content=b"wrong", sha=uuid4().hex),
            )


def test_import_history_pages_through_legacy_rows(isolated_database, monkeypatch):
    config, engine, _ = isolated_database
    command.upgrade(config, "head")
    monkeypatch.setattr("sys.argv", ["provision", "owner", "osint_analyst"])
    monkeypatch.setattr(provision, "getpass", lambda _: "synthetic-test-only")
    provision.main()
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/sessions",
            json={
                "username": "owner",
                "password": "synthetic-test-only",
            },
        )
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        case = client.post(
            "/api/v1/cases",
            headers=headers,
            json={
                "fixture_id": "SYN-001",
                "purpose": "Exercise",
                "scope": "Fixture",
            },
        ).json()
        path = f"/api/v1/cases/{case['id']}/imports"
        with engine.begin() as db:
            older = db.scalar(
                text("""
                INSERT INTO imports (case_id, submitted_by_id, source_ref, created_at)
                SELECT id, owner_id, 'legacy', now() - interval '1 day' FROM cases
                RETURNING id
            """)
            )
            db.execute(
                text("INSERT INTO import_rows (import_id, row_number) VALUES (:id, 2)"),
                {"id": older},
            )
        saved = client.post(
            path,
            headers={**headers, "Idempotency-Key": "current"},
            json={"content": "Label\nFixture\n", "column": "Label"},
        )
        assert saved.status_code == 201, saved.text
        latest = saved.json()["id"]

        first = client.get(path, headers=headers, params={"limit": 1}).json()
        assert [item["id"] for item in first["items"]] == [latest]
        assert first["next_cursor"] == latest
        second = client.get(
            path, headers=headers, params={"before": latest, "limit": 1}
        ).json()
        assert second["next_cursor"] is None
        legacy = second["items"][0]
        assert legacy["id"] == str(older)
        assert legacy["sha256"] is None
        assert (
            legacy["row_count"] == 1
            and legacy["valid_count"] == legacy["invalid_count"] == 0
        )
        assert (
            client.get(
                path, headers=headers, params={"before": str(uuid4())}
            ).status_code
            == 404
        )
