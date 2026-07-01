"""badcases 加 trace_json + pending_deltas 表

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-01
"""
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("badcases",
        sa.Column("trace_json", sa.JSON, nullable=True, comment="解析后的 StructuredTrace"))
    op.create_table(
        "pending_deltas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("from_bom_version_id", sa.Integer, sa.ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("delta_json", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("reviewed_by", sa.String(32), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("pending_deltas")
    op.drop_column("badcases", "trace_json")
