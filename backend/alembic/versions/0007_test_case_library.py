"""用例库：test_set_imports 改文件级 + 新建 test_cases 表

Revision ID: 0007
Revises: 0006
"""
revision = "0007"
down_revision = "0006"

from alembic import op
import sqlalchemy as sa


def upgrade():
    # test_set_imports 原表未使用（死表无数据），drop + 重建为文件级
    op.drop_table("test_set_imports")
    op.create_table(
        "test_set_imports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("file_name", sa.String(256), nullable=False),
        sa.Column("file_hash", sa.String(64), comment="SHA256 防重复导入"),
        sa.Column("total_cases", sa.Integer, server_default="0", comment="总用例数含负例"),
        sa.Column("positive_cases", sa.Integer, server_default="0", comment="正例数有期望值"),
        sa.Column("negative_cases", sa.Integer, server_default="0", comment="负例数空期望值"),
        sa.Column("clauses_count", sa.Integer, server_default="0", comment="覆盖条款数"),
        sa.Column("imported_at", sa.DateTime, server_default=sa.func.now()),
    )
    # 新建 test_cases（存全部行：正例+负例，保留原始列 JSON）
    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("test_set_id", sa.Integer, sa.ForeignKey("test_set_imports.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("block_code", sa.String(64), index=True),
        sa.Column("doc_id", sa.String(128)),
        sa.Column("expected_value", sa.Text),
        sa.Column("has_expected", sa.Boolean, comment="True=正例 False=负例"),
        sa.Column("row_data", sa.JSON, comment="原始行完整数据保留Excel所有列"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("test_cases")
    op.drop_table("test_set_imports")
    # 重建旧 test_set_imports（原 schema，无数据不严谨但够回滚）
    op.create_table(
        "test_set_imports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("file_name", sa.String(256), nullable=False),
        sa.Column("file_hash", sa.String(64)),
        sa.Column("original_count", sa.Integer),
        sa.Column("after_dedup", sa.Integer),
        sa.Column("domain", sa.String(32)),
        sa.Column("imported_by", sa.String(32), server_default=""),
        sa.Column("imported_at", sa.DateTime, server_default=sa.func.now()),
    )
