"""Add the synthetic evidence workflow and Procrastinate 3.12 queue."""

import re
from importlib.resources import files

import sqlalchemy as sa
from alembic import op

revision = "0006_synthetic_workflow"
down_revision = "0005_case_retry_audit"
branch_labels = None
depends_on = None


def queue_schema() -> str:
    return files("procrastinate").joinpath("sql", "schema.sql").read_text()


def upgrade() -> None:
    # The exact package version is pinned because its schema is used here.
    op.execute(sa.DDL(queue_schema().replace("%", "%%")))
    op.execute("""
        ALTER TABLE imports ADD COLUMN source_format text NOT NULL DEFAULT 'csv'
            CHECK (source_format IN ('csv', 'xlsx', 'manual'));
        ALTER TABLE device_sessions ADD UNIQUE (case_id, id);
        ALTER TABLE consent_records ADD UNIQUE (session_id, id);
        CREATE TABLE synthetic_device_sessions (
            id uuid PRIMARY KEY,
            case_id uuid NOT NULL,
            consent_id uuid NOT NULL,
            creation_key text NOT NULL,
            UNIQUE (case_id, creation_key),
            UNIQUE (case_id, id),
            FOREIGN KEY (case_id, id) REFERENCES device_sessions (case_id, id),
            FOREIGN KEY (id, consent_id) REFERENCES consent_records (session_id, id)
        );
        ALTER TABLE jobs
            ADD COLUMN device_session_id uuid,
            ADD CONSTRAINT fk_jobs_device_session FOREIGN KEY (case_id, device_session_id)
                REFERENCES synthetic_device_sessions (case_id, id),
            ADD CONSTRAINT ck_jobs_synthetic_device CHECK
                (kind <> 'synthetic_device' OR device_session_id IS NOT NULL),
            ADD COLUMN import_id uuid,
            ADD COLUMN queue_id bigint UNIQUE REFERENCES procrastinate_jobs(id),
            ADD COLUMN failure_code text,
            ADD CONSTRAINT fk_jobs_import FOREIGN KEY (case_id, import_id)
                REFERENCES imports (case_id, id),
            ADD CONSTRAINT ck_jobs_synthetic_import CHECK
                (kind <> 'synthetic_source' OR import_id IS NOT NULL);
        CREATE INDEX ix_jobs_case_created ON jobs (case_id, created_at DESC, id DESC);

        CREATE TABLE case_collaborators (
            case_id uuid NOT NULL REFERENCES cases(id),
            user_id uuid NOT NULL REFERENCES users(id),
            PRIMARY KEY (case_id, user_id)
        );
        CREATE INDEX ix_case_collaborators_user ON case_collaborators (user_id, case_id);

        CREATE TABLE synthetic_device_evidence (
            job_id uuid PRIMARY KEY REFERENCES jobs(id),
            evidence text NOT NULL,
            evidence_sha256 text NOT NULL CHECK
                (evidence_sha256 = encode(sha256(convert_to(evidence, 'UTF8')), 'hex'))
        );
        CREATE TRIGGER synthetic_device_evidence_immutable BEFORE UPDATE OR DELETE
            ON synthetic_device_evidence FOR EACH ROW EXECUTE FUNCTION protect_import_evidence();

        CREATE TABLE synthetic_findings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id uuid NOT NULL UNIQUE REFERENCES jobs(id),
            evidence text NOT NULL,
            evidence_sha256 text NOT NULL CHECK
                (evidence_sha256 = encode(sha256(convert_to(evidence, 'UTF8')), 'hex')),
            threat_status text NOT NULL CHECK
                (threat_status IN ('confirmed', 'suspected', 'inconclusive', 'false_positive')),
            severity text NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
            verification text NOT NULL DEFAULT 'pending' CHECK
                (verification IN ('pending', 'verified', 'inconclusive', 'rejected')),
            review_note text,
            reviewed_at timestamptz,
            reviewed_by uuid REFERENCES users(id),
            CONSTRAINT ck_synthetic_findings_review CHECK (
                (verification = 'pending' AND review_note IS NULL
                    AND reviewed_at IS NULL AND reviewed_by IS NULL)
                OR (verification <> 'pending' AND length(btrim(review_note)) > 0
                    AND review_note IS NOT NULL AND reviewed_at IS NOT NULL
                    AND reviewed_by IS NOT NULL)
            )
        );
        CREATE FUNCTION guard_synthetic_finding_evidence() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Synthetic finding evidence is immutable' USING ERRCODE = '23514';
            END IF;
            IF (NEW.id, NEW.job_id, NEW.evidence, NEW.evidence_sha256, NEW.threat_status, NEW.severity)
                IS DISTINCT FROM
                (OLD.id, OLD.job_id, OLD.evidence, OLD.evidence_sha256, OLD.threat_status, OLD.severity)
            THEN
                RAISE EXCEPTION 'Synthetic finding evidence is immutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER synthetic_finding_evidence_immutable BEFORE UPDATE OR DELETE
            ON synthetic_findings FOR EACH ROW EXECUTE FUNCTION guard_synthetic_finding_evidence();
    """)


def downgrade() -> None:
    op.drop_table("synthetic_findings")
    op.drop_table("synthetic_device_evidence")
    op.drop_column("imports", "source_format")
    op.execute("DROP FUNCTION guard_synthetic_finding_evidence")
    op.drop_table("case_collaborators")
    op.drop_index("ix_jobs_case_created", table_name="jobs")
    op.execute("""
        ALTER TABLE jobs DROP CONSTRAINT fk_jobs_import,
            DROP CONSTRAINT fk_jobs_device_session, DROP CONSTRAINT ck_jobs_synthetic_device,
            DROP COLUMN device_session_id,
            DROP CONSTRAINT ck_jobs_synthetic_import,
            DROP COLUMN import_id, DROP COLUMN queue_id, DROP COLUMN failure_code
    """)
    op.drop_table("synthetic_device_sessions")
    op.drop_constraint(
        "consent_records_session_id_id_key", "consent_records", type_="unique"
    )
    op.drop_constraint(
        "device_sessions_case_id_id_key", "device_sessions", type_="unique"
    )
    op.execute("""
        DROP TABLE procrastinate_events, procrastinate_periodic_defers,
            procrastinate_jobs, procrastinate_workers CASCADE
    """)
    for function in re.findall(
        r"^CREATE FUNCTION (procrastinate_\w+)\(", queue_schema(), re.M
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
    op.execute("""
        DROP TYPE procrastinate_job_to_defer_v2, procrastinate_lock_mode,
            procrastinate_job_event_type, procrastinate_job_status
    """)
