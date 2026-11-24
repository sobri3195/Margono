"""Persist case creation receipts and scope import references on audit events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_case_retry_audit"
down_revision = "0004_csv_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_creation_receipts",
        sa.Column(
            "operator_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True
        ),
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column(
            "case_id", sa.Uuid(), sa.ForeignKey("cases.id"), nullable=False, unique=True
        ),
        sa.Column("response", JSONB(), nullable=False),
    )
    op.create_unique_constraint("uq_imports_case_id_id", "imports", ["case_id", "id"])
    op.add_column("audit_events", sa.Column("import_id", sa.Uuid()))
    op.create_check_constraint(
        "ck_audit_import_requires_case",
        "audit_events",
        "import_id IS NULL OR case_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_audit_import_case",
        "audit_events",
        "imports",
        ["case_id", "import_id"],
        ["case_id", "id"],
    )
    op.create_index("ix_audit_events_import_id", "audit_events", ["import_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_import_id", table_name="audit_events")
    op.drop_constraint("fk_audit_import_case", "audit_events", type_="foreignkey")
    op.drop_constraint("ck_audit_import_requires_case", "audit_events", type_="check")
    op.drop_column("audit_events", "import_id")
    op.drop_constraint("uq_imports_case_id_id", "imports", type_="unique")
    op.drop_table("case_creation_receipts")
