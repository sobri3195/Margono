"""Store reproducible synthetic CSV imports and original bytes."""

import sqlalchemy as sa
from alembic import op

revision = "0004_csv_evidence"
down_revision = "0003_synthetic_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("imports", sa.Column("idempotency_key", sa.String(128)))
    op.add_column("imports", sa.Column("selected_column", sa.Text()))
    op.create_unique_constraint(
        "uq_imports_idempotency", "imports", ["case_id", "idempotency_key"]
    )
    op.create_table(
        "import_evidence",
        sa.Column(
            "import_id", sa.Uuid(), sa.ForeignKey("imports.id"), primary_key=True
        ),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "octet_length(content) BETWEEN 1 AND 65536", name="ck_import_evidence_size"
        ),
        sa.CheckConstraint(
            "sha256 = encode(sha256(content), 'hex')", name="ck_import_evidence_hash"
        ),
    )
    op.execute("""
        CREATE FUNCTION protect_import_evidence() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Import evidence cannot be edited' USING ERRCODE = '23514';
        END
        $$
    """)
    op.execute("""
        CREATE TRIGGER protect_import_evidence
        BEFORE UPDATE OR DELETE ON import_evidence
        FOR EACH ROW EXECUTE FUNCTION protect_import_evidence()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER protect_import_evidence ON import_evidence")
    op.execute("DROP FUNCTION protect_import_evidence()")
    op.drop_table("import_evidence")
    op.drop_constraint("uq_imports_idempotency", "imports", type_="unique")
    op.drop_column("imports", "selected_column")
    op.drop_column("imports", "idempotency_key")
