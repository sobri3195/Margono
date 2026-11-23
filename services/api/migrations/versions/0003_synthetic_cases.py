"""Add local sessions and link persisted cases to synthetic catalog entries."""

import sqlalchemy as sa
from alembic import op

revision = "0003_synthetic_cases"
down_revision = "0002_case_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text()))
    op.add_column("cases", sa.Column("synthetic_fixture_id", sa.String(7)))
    op.create_check_constraint(
        "ck_cases_synthetic_fixture_id",
        "cases",
        "synthetic_fixture_id IS NULL OR synthetic_fixture_id ~ '^SYN-[0-9]{3}$'",
    )
    op.create_table(
        "user_sessions",
        sa.Column("token_digest", sa.LargeBinary(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_sessions")
    op.drop_constraint("ck_cases_synthetic_fixture_id", "cases", type_="check")
    op.drop_column("cases", "synthetic_fixture_id")
    op.drop_column("users", "password_hash")
