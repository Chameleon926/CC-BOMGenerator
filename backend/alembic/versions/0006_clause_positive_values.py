"""clauses 加 positive_values_json + positive_examples_json（正例存 DB，防重部署丢数据）

Revision ID: 0006
Revises: 0005
"""
revision = "0006"
down_revision = "0005"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("clauses", sa.Column("positive_values_json", sa.JSON, nullable=True, comment="正例值列表（去重）"))
    op.add_column("clauses", sa.Column("positive_examples_json", sa.JSON, nullable=True, comment="正例行（含doc_id等）"))


def downgrade():
    op.drop_column("clauses", "positive_examples_json")
    op.drop_column("clauses", "positive_values_json")
