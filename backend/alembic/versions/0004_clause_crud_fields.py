"""clauses 加 positive_count / source_file / imported_at（支持 CRUD + 持久化用例数）

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-06
"""

revision = "0004"
down_revision = "0003"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("clauses", sa.Column("positive_count", sa.Integer, server_default="0", comment="用例数（scan 时写入）"))
    op.add_column("clauses", sa.Column("source_file", sa.String(256), server_default="", comment="来源测试集文件名"))
    op.add_column("clauses", sa.Column("imported_at", sa.DateTime, server_default=sa.func.now(), comment="最近导入时间"))


def downgrade():
    op.drop_column("clauses", "imported_at")
    op.drop_column("clauses", "source_file")
    op.drop_column("clauses", "positive_count")
