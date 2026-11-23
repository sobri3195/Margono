"""Protect case scope, import validation, and consent decisions."""

from alembic import op

revision = "0002_case_integrity"
down_revision = "0001_operational_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_cases_nonblank_purpose_scope",
        "cases",
        "purpose ~ '[^[:space:]]' AND scope ~ '[^[:space:]]'",
    )
    op.create_check_constraint(
        "ck_import_rows_valid_label",
        "import_rows",
        "status <> 'valid' OR (reference_label IS NOT NULL AND reference_label ~ '[^[:space:]]')",
    )
    op.execute("""
        CREATE TABLE consent_decisions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            consent_id uuid NOT NULL REFERENCES consent_records(id),
            status text NOT NULL CHECK (status IN ('granted', 'declined', 'revoked')),
            occurred_at timestamptz NOT NULL,
            UNIQUE (consent_id, status)
        )
    """)
    op.execute("""
        INSERT INTO consent_decisions (consent_id, status, occurred_at)
        SELECT id, status, COALESCE(revoked_at, decided_at) FROM consent_records
    """)
    op.execute("""
        CREATE FUNCTION protect_consent_record() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status = 'revoked' THEN
                    RAISE EXCEPTION 'Consent must record an initial decision' USING ERRCODE = '23514';
                END IF;
            ELSIF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Consent records cannot be deleted' USING ERRCODE = '23514';
            ELSIF NEW IS DISTINCT FROM OLD AND (
                OLD.status <> 'granted' OR NEW.status <> 'revoked'
                OR ROW(NEW.id, NEW.session_id, NEW.recorded_by_id, NEW.purpose,
                    NEW.scope, NEW.disclosure, NEW.decided_at)
                IS DISTINCT FROM ROW(OLD.id, OLD.session_id, OLD.recorded_by_id, OLD.purpose,
                    OLD.scope, OLD.disclosure, OLD.decided_at)
            ) THEN
                RAISE EXCEPTION 'Invalid consent transition' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER protect_consent_record
        BEFORE INSERT OR UPDATE OR DELETE ON consent_records
        FOR EACH ROW EXECUTE FUNCTION protect_consent_record()
    """)
    op.execute("""
        CREATE FUNCTION record_consent_decision() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
                INSERT INTO consent_decisions (consent_id, status, occurred_at)
                VALUES (NEW.id, NEW.status, COALESCE(NEW.revoked_at, NEW.decided_at));
            END IF;
            RETURN NEW;
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER record_consent_decision
        AFTER INSERT OR UPDATE ON consent_records
        FOR EACH ROW EXECUTE FUNCTION record_consent_decision()
    """)
    op.execute("""
        CREATE FUNCTION protect_consent_decision() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'INSERT' AND pg_catalog.pg_trigger_depth() = 2 THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'Consent history cannot be edited' USING ERRCODE = '23514';
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER protect_consent_decision
        BEFORE INSERT OR UPDATE OR DELETE ON consent_decisions
        FOR EACH ROW EXECUTE FUNCTION protect_consent_decision()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER protect_consent_decision ON consent_decisions")
    op.execute("DROP FUNCTION protect_consent_decision()")
    op.execute("DROP TRIGGER record_consent_decision ON consent_records")
    op.execute("DROP FUNCTION record_consent_decision()")
    op.execute("DROP TRIGGER protect_consent_record ON consent_records")
    op.execute("DROP FUNCTION protect_consent_record()")
    op.drop_table("consent_decisions")
    op.drop_constraint("ck_import_rows_valid_label", "import_rows", type_="check")
    op.drop_constraint("ck_cases_nonblank_purpose_scope", "cases", type_="check")
