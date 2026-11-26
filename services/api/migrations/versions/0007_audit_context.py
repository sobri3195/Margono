"""Link audit events to device sessions and provisioned accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0007_audit_context"
down_revision = "0006_synthetic_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("device_session_id", sa.Uuid()))
    op.add_column("audit_events", sa.Column("subject_user_id", sa.Uuid()))
    op.create_check_constraint(
        "ck_audit_device_requires_case",
        "audit_events",
        "device_session_id IS NULL OR case_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_audit_device_case",
        "audit_events",
        "synthetic_device_sessions",
        ["case_id", "device_session_id"],
        ["case_id", "id"],
    )
    op.create_foreign_key(
        "fk_audit_subject_user",
        "audit_events",
        "users",
        ["subject_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_audit_events_device_occurred",
        "audit_events",
        ["device_session_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_device_occurred", table_name="audit_events")
    op.drop_constraint("fk_audit_subject_user", "audit_events", type_="foreignkey")
    op.drop_constraint("fk_audit_device_case", "audit_events", type_="foreignkey")
    op.drop_constraint("ck_audit_device_requires_case", "audit_events", type_="check")
    op.drop_column("audit_events", "subject_user_id")
    op.drop_column("audit_events", "device_session_id")
