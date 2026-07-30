"""test_cases 加 actual_value 列（用户填的误抽值）

Revision ID: 0008
Revises: 0007
"""
revision = "0008"
down_revision = "0007"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("test_cases", sa.Column("actual_value", sa.Text, nullable=True, comment="误抽值（用户填的：大模型实际误抽的内容）"))


def downgrade():
    op.drop_column("test_cases", "actual_value")
