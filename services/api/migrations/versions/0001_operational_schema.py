"""Create the first PostgreSQL operational schema."""

import sqlalchemy as sa
from alembic import op

revision = "0001_operational_schema"
down_revision = None
branch_labels = None
depends_on = None


def primary_id() -> sa.Column:
    return sa.Column(
        "id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "users",
        primary_id(),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        created_at(),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint(
            "username <> '' AND username = lower(btrim(username))",
            name="ck_users_username",
        ),
    )
    roles = op.create_table("roles", sa.Column("slug", sa.Text(), primary_key=True))
    op.bulk_insert(
        roles,
        [
            {"slug": role}
            for role in (
                "administrator",
                "osint_analyst",
                "forensic_examiner",
                "supervisor",
            )
        ],
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column(
            "role_slug", sa.Text(), sa.ForeignKey("roles.slug"), primary_key=True
        ),
    )
    op.create_table(
        "cases",
        primary_id(),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        created_at(),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(status = 'open' AND closed_at IS NULL) OR "
            "(status = 'closed' AND closed_at IS NOT NULL AND closed_at >= created_at)",
            name="ck_cases_status_dates",
        ),
    )
    op.create_index("ix_cases_owner_id", "cases", ["owner_id"])
    op.create_table(
        "device_sessions",
        primary_id(),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("examiner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        created_at(),
        sa.CheckConstraint(
            "platform IN ('android', 'iphone')", name="ck_device_sessions_platform"
        ),
    )
    op.create_index("ix_device_sessions_case_id", "device_sessions", ["case_id"])
    op.create_table(
        "consent_records",
        primary_id(),
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("device_sessions.id"), nullable=False
        ),
        sa.Column(
            "recorded_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("disclosure", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(status IN ('granted', 'declined') AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL AND revoked_at >= decided_at)",
            name="ck_consent_records_status_dates",
        ),
    )
    op.create_index("ix_consent_records_session_id", "consent_records", ["session_id"])
    op.create_table(
        "imports",
        primary_id(),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column(
            "submitted_by_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("source_ref", sa.Text(), nullable=False),
        created_at(),
    )
    op.create_index("ix_imports_case_id", "imports", ["case_id"])
    op.create_table(
        "import_rows",
        primary_id(),
        sa.Column("import_id", sa.Uuid(), sa.ForeignKey("imports.id"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("reference_label", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.CheckConstraint("row_number > 0", name="ck_import_rows_row_number"),
        sa.CheckConstraint(
            "status IN ('pending', 'valid', 'invalid')", name="ck_import_rows_status"
        ),
        sa.UniqueConstraint("import_id", "row_number", name="uq_import_rows_position"),
    )
    op.create_table(
        "jobs",
        primary_id(),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        created_at(),
        sa.CheckConstraint(
            "btrim(idempotency_key) <> ''", name="ck_jobs_idempotency_key"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'paused', 'completed', 'failed', 'cancelled')",
            name="ck_jobs_status",
        ),
        sa.UniqueConstraint(
            "case_id", "kind", "idempotency_key", name="uq_jobs_idempotency"
        ),
    )
    op.create_table(
        "audit_events",
        primary_id(),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id")),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.Uuid()),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_audit_events_case_occurred_at", "audit_events", ["case_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("jobs")
    op.drop_table("import_rows")
    op.drop_table("imports")
    op.drop_table("consent_records")
    op.drop_table("device_sessions")
    op.drop_table("cases")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
