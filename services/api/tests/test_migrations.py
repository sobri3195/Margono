from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from margono_api.main import app

pytestmark = pytest.mark.postgres


def test_migration_up_down_up(isolated_database):
    config, engine, schema = isolated_database
    assert sa.inspect(engine).get_table_names(schema=schema) == []

    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert set(sa.inspect(engine).get_table_names(schema=schema)) == {
        "alembic_version",
        "audit_events",
        "cases",
        "case_collaborators",
        "case_creation_receipts",
        "consent_decisions",
        "consent_records",
        "device_sessions",
        "import_evidence",
        "import_rows",
        "imports",
        "jobs",
        "roles",
        "procrastinate_events",
        "procrastinate_jobs",
        "procrastinate_periodic_defers",
        "procrastinate_workers",
        "synthetic_findings",
        "synthetic_device_sessions",
        "synthetic_device_evidence",
        "user_roles",
        "user_sessions",
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

        with (
            pytest.raises(IntegrityError, match="Invalid consent transition"),
            connection.begin_nested(),
        ):
            connection.execute(
                sa.text(
                    "UPDATE consent_records SET status = 'granted', revoked_at = NULL WHERE id = :id"
                ),
                {"id": consent_id},
            )
        assert set(
            connection.scalars(sa.text("SELECT status FROM consent_decisions"))
        ) == {
            "granted",
            "revoked",
        }
        with (
            pytest.raises(IntegrityError, match="Consent history cannot be edited"),
            connection.begin_nested(),
        ):
            connection.execute(sa.text("DELETE FROM consent_decisions"))
        with (
            pytest.raises(IntegrityError, match="Consent history cannot be edited"),
            connection.begin_nested(),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO consent_decisions (consent_id, status, occurred_at) VALUES (:id, 'declined', now())"
                ),
                {"id": consent_id},
            )


def test_readiness_distinguishes_unmigrated_and_migrated_postgres(isolated_database):
    config, engine, _ = isolated_database
    with TestClient(app) as client:
        before = client.get("/api/v1/readiness")
        assert before.status_code == 503
        assert before.json()["checks"]["database"] == "migration_required"

        command.upgrade(config, "head")
        after = client.get("/api/v1/readiness")
        assert after.status_code == 503
        assert after.json()["checks"]["database"] == "ready"
        assert after.json()["checks"]["worker"] == "not_observed"
        assert after.json()["pilot"] == "blocked"

        with engine.begin() as connection:
            connection.execute(
                sa.text("INSERT INTO procrastinate_workers DEFAULT VALUES")
            )
        with_worker = client.get("/api/v1/readiness")
        assert with_worker.status_code == 503
        assert with_worker.json()["checks"]["worker"] == "active"


def test_case_and_import_invariants(isolated_database):
    config, engine, _ = isolated_database
    command.upgrade(config, "head")
    with engine.begin() as connection:
        user = connection.scalar(
            sa.text("INSERT INTO users (username) VALUES ('sample') RETURNING id")
        )
        case_sql = sa.text(
            "INSERT INTO cases (owner_id, purpose, scope) "
            "VALUES (:user, :purpose, :scope) RETURNING id"
        )
        for purpose, scope in [("", "Simulation"), ("Simulation", "\t\n")]:
            with (
                pytest.raises(IntegrityError, match="ck_cases_nonblank_purpose_scope"),
                connection.begin_nested(),
            ):
                connection.execute(
                    case_sql, dict(user=user, purpose=purpose, scope=scope)
                )
        case = connection.scalar(
            case_sql, dict(user=user, purpose="Purpose", scope="Scope")
        )
        batch = connection.scalar(
            sa.text(
                "INSERT INTO imports (case_id, submitted_by_id, source_ref) "
                "VALUES (:case, :user, 'synthetic') RETURNING id"
            ),
            dict(case=case, user=user),
        )
        row = sa.text(
            "INSERT INTO import_rows (import_id, row_number, reference_label, status) "
            "VALUES (:batch, 1, :label, :status)"
        )
        for label in (None, " ", "\t"):
            with (
                pytest.raises(IntegrityError, match="ck_import_rows_valid_label"),
                connection.begin_nested(),
            ):
                connection.execute(row, dict(batch=batch, label=label, status="valid"))
        connection.execute(row, dict(batch=batch, label=None, status="invalid"))


def test_upgrade_requires_review_of_invalid_legacy_records(isolated_database):
    config, engine, _ = isolated_database
    command.upgrade(config, "0001_operational_schema")
    with engine.begin() as db:
        db.execute(
            sa.text("""
            WITH owner AS (INSERT INTO users (username) VALUES ('legacy') RETURNING id)
            INSERT INTO cases (owner_id, purpose, scope) SELECT id, '', 'Fixture' FROM owner
        """)
        )
    with pytest.raises(IntegrityError, match="ck_cases_nonblank_purpose_scope"):
        command.upgrade(config, "head")
    with engine.begin() as db:
        assert db.scalar(sa.text("SELECT purpose FROM cases")) == ""
        assert (
            db.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0001_operational_schema"
        )
        db.execute(sa.text("UPDATE cases SET purpose = 'Reviewed synthetic example'"))
    command.upgrade(config, "head")
    with engine.connect() as db:
        assert (
            db.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0006_synthetic_workflow"
        )


def test_audit_upgrade_preserves_old_events_and_rejects_mismatched_imports(
    isolated_database,
):
    config, engine, _ = isolated_database
    command.upgrade(config, "0004_csv_evidence")
    with engine.begin() as db:
        user = db.scalar(
            sa.text("INSERT INTO users (username) VALUES ('legacy') RETURNING id")
        )
        case_ids = (
            db.execute(
                sa.text("""
            INSERT INTO cases (owner_id, purpose, scope)
            VALUES (:user, 'Legacy fixture A', 'Scope'), (:user, 'Legacy fixture B', 'Scope')
            RETURNING id
        """),
                {"user": user},
            )
            .scalars()
            .all()
        )
        batch_id = db.scalar(
            sa.text("""
            INSERT INTO imports (case_id, submitted_by_id, source_ref)
            VALUES (:case, :user, 'legacy') RETURNING id
        """),
            {"case": case_ids[0], "user": user},
        )
        event_id = db.scalar(
            sa.text("""
            INSERT INTO audit_events (case_id, actor_id, action) VALUES (:case, :actor, 'import.confirmed')
            RETURNING id
        """),
            {"case": case_ids[0], "actor": user},
        )

    command.upgrade(config, "head")
    with engine.begin() as db:
        legacy = db.execute(
            sa.text("SELECT * FROM audit_events WHERE id = :id"), {"id": event_id}
        ).one()
        assert legacy.action == "import.confirmed" and legacy.import_id is None
        with (
            pytest.raises(IntegrityError, match="fk_audit_import_case"),
            db.begin_nested(),
        ):
            db.execute(
                sa.text("""
                INSERT INTO audit_events (case_id, import_id, actor_id, action)
                VALUES (:case, :batch, :actor, 'import.evidence_served')
            """),
                {"case": case_ids[1], "batch": batch_id, "actor": user},
            )
