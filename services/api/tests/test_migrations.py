from os import environ
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateSchema, DropSchema

from margono_api.main import app

pytestmark = pytest.mark.postgres
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


def test_migration_up_down_up(isolated_database):
    config, engine, schema = isolated_database
    assert sa.inspect(engine).get_table_names(schema=schema) == []

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert set(sa.inspect(engine).get_table_names(schema=schema)) == {
        "alembic_version",
        "audit_events",
        "cases",
        "consent_records",
        "device_sessions",
        "import_rows",
        "imports",
        "jobs",
        "roles",
        "user_roles",
        "users",
    }
    with engine.connect() as connection:
        assert set(connection.scalars(sa.text("SELECT slug FROM roles"))) == {
            "administrator",
            "osint_analyst",
            "forensic_examiner",
            "supervisor",
        }

    command.downgrade(config, "base")
    assert sa.inspect(engine).get_table_names(schema=schema) == ["alembic_version"]
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM alembic_version")) == 0

    command.upgrade(config, "head")
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT count(*) FROM roles")) == 4


def test_cases_imports_jobs_and_audit(isolated_database):
    config, engine, _ = isolated_database
    command.upgrade(config, "head")
    with engine.begin() as connection:
        user_id = connection.scalar(
            sa.text("INSERT INTO users (username) VALUES ('synthetic') RETURNING id")
        )
        connection.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_slug) VALUES (:user_id, 'osint_analyst')"
            ),
            {"user_id": user_id},
        )
        case_id = connection.scalar(
            sa.text(
                "INSERT INTO cases (owner_id, purpose, scope) VALUES (:owner_id, 'Simulation', 'Fixture') RETURNING id"
            ),
            {"owner_id": user_id},
        )
        assert isinstance(case_id, UUID)
        with (
            pytest.raises(IntegrityError, match="ck_cases_status_dates"),
            connection.begin_nested(),
        ):
            connection.execute(
                sa.text("UPDATE cases SET status = 'closed' WHERE id = :case_id"),
                {"case_id": case_id},
            )
        with (
            pytest.raises(IntegrityError, match="user_roles_role_slug_fkey"),
            connection.begin_nested(),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO user_roles (user_id, role_slug) VALUES (:user_id, 'unknown')"
                ),
                {"user_id": user_id},
            )

        import_id = connection.scalar(
            sa.text(
                "INSERT INTO imports (case_id, submitted_by_id, source_ref) "
                "VALUES (:case_id, :user_id, 'SYN-fixture.csv') RETURNING id"
            ),
            {"case_id": case_id, "user_id": user_id},
        )
        insert_row = sa.text(
            "INSERT INTO import_rows (import_id, row_number, reference_label) "
            "VALUES (:import_id, :row, 'Label sintetis') RETURNING id"
        )
        first = connection.scalar(insert_row, {"import_id": import_id, "row": 1})
        second = connection.scalar(insert_row, {"import_id": import_id, "row": 2})
        assert first != second
        with (
            pytest.raises(IntegrityError, match="uq_import_rows_position"),
            connection.begin_nested(),
        ):
            connection.execute(insert_row, {"import_id": import_id, "row": 1})

        insert_job = sa.text(
            "INSERT INTO jobs (case_id, kind, idempotency_key) "
            "VALUES (:case_id, :kind, 'synthetic-key') RETURNING status"
        )
        assert (
            connection.scalar(insert_job, {"case_id": case_id, "kind": "source_review"})
            == "queued"
        )
        with (
            pytest.raises(IntegrityError, match="uq_jobs_idempotency"),
            connection.begin_nested(),
        ):
            connection.execute(
                insert_job, {"case_id": case_id, "kind": "source_review"}
            )
        assert (
            connection.scalar(insert_job, {"case_id": case_id, "kind": "report"})
            == "queued"
        )
        occurred_at = connection.scalar(
            sa.text(
                "INSERT INTO audit_events (case_id, actor_id, action) "
                "VALUES (:case_id, :user_id, 'synthetic.case_created') RETURNING occurred_at"
            ),
            {"case_id": case_id, "user_id": user_id},
        )
        assert occurred_at.utcoffset() is not None


def test_consent_revocation_requires_valid_timestamp(isolated_database):
    config, engine, _ = isolated_database
    command.upgrade(config, "head")
    with engine.begin() as connection:
        user_id = connection.scalar(
            sa.text("INSERT INTO users (username) VALUES ('synthetic') RETURNING id")
        )
        session_id = connection.scalar(
            sa.text(
                "WITH created_case AS ("
                "  INSERT INTO cases (owner_id, purpose, scope) "
                "  VALUES (:user_id, 'Simulation', 'Fixture') RETURNING id"
                ") INSERT INTO device_sessions (case_id, examiner_id, platform) "
                "SELECT id, :user_id, 'android' FROM created_case RETURNING id"
            ),
            {"user_id": user_id},
        )
        consent_id = connection.scalar(
            sa.text(
                "INSERT INTO consent_records "
                "(session_id, recorded_by_id, purpose, scope, disclosure, status, decided_at) "
                "VALUES (:session_id, :user_id, 'Simulation', 'Metadata fixture', "
                "'Disclosure fixture', 'granted', now()) RETURNING id"
            ),
            {"session_id": session_id, "user_id": user_id},
        )
        revoke = sa.text(
            "UPDATE consent_records SET status = 'revoked', revoked_at = :revoked_at WHERE id = :id"
        )
        with (
            pytest.raises(IntegrityError, match="ck_consent_records_status_dates"),
            connection.begin_nested(),
        ):
            connection.execute(revoke, {"id": consent_id, "revoked_at": None})
        earlier = connection.scalar(sa.text("SELECT now() - interval '1 second'"))
        with (
            pytest.raises(IntegrityError, match="ck_consent_records_status_dates"),
            connection.begin_nested(),
        ):
            connection.execute(revoke, {"id": consent_id, "revoked_at": earlier})
        timestamp = connection.scalar(sa.text("SELECT now()"))
        assert (
            connection.execute(
                revoke, {"id": consent_id, "revoked_at": timestamp}
            ).rowcount
            == 1
        )


def test_readiness_distinguishes_unmigrated_and_migrated_postgres(isolated_database):
    config, _, _ = isolated_database
    with TestClient(app) as client:
        before = client.get("/api/v1/readiness")
        assert before.status_code == 503
        assert before.json()["checks"]["database"] == "migration_required"

        command.upgrade(config, "head")
        after = client.get("/api/v1/readiness")
        assert after.status_code == 503
        assert after.json()["checks"]["database"] == "ready"
        assert after.json()["pilot"] == "blocked"
