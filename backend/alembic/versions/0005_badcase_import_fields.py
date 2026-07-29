"""badcases 加 issue_type/auto_judged/context_text + platform_run_id 改 nullable

Revision ID: 0005
Revises: 0004
"""
revision = "0005"
down_revision = "0004"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("badcases", sa.Column("issue_type", sa.String(16), nullable=True, comment="召回失败/抽取失败"))
    op.add_column("badcases", sa.Column("auto_judged", sa.Boolean, server_default="0", comment="是否系统自动判类"))
    op.add_column("badcases", sa.Column("context_text", sa.Text, nullable=True))
    op.alter_column("badcases", "platform_run_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column("badcases", "platform_run_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("badcases", "context_text")
    op.drop_column("badcases", "auto_judged")
    op.drop_column("badcases", "issue_type")
