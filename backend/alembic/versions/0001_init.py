"""Alembic 迁移脚本 —— 初始建表。"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # clause 表
    op.create_table(
        "clause",
        sa.Column("block_code", sa.String(64), primary_key=True),
        sa.Column("block_name", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(32), server_default=""),
        sa.Column("current_version", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        comment="条款注册表",
    )

    # pipeline_runs 表
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clause.block_code"), nullable=False, index=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="running"),
        sa.Column("input_cleaned_json", sa.JSON, nullable=True),
        sa.Column("output_bom_json", sa.JSON, nullable=True),
        sa.Column("output_prompt_text", sa.Text, default=""),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("bom_version_id", sa.Integer, nullable=True),
        comment="管线执行记录",
    )

    # node_executions 表
    op.create_table(
        "node_executions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pipeline_run_id", sa.Integer, sa.ForeignKey("pipeline_runs.id"), nullable=False, index=True),
        sa.Column("skill_name", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("is_retry", sa.Boolean, server_default="0"),
        sa.Column("input_json", sa.JSON, nullable=True),
        sa.Column("output_json", sa.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, server_default="1"),
        comment="Skill 节点执行记录",
    )

    # llm_calls 表
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("node_execution_id", sa.Integer, sa.ForeignKey("node_executions.id"), nullable=True, index=True),
        sa.Column("api_format", sa.String(16), server_default="openai"),
        sa.Column("model", sa.String(64), default=""),
        sa.Column("temperature", sa.Float, server_default="0.3"),
        sa.Column("max_retries", sa.Integer, server_default="1"),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("user_prompt", sa.Text, nullable=True),
        sa.Column("assistant_response", sa.Text, nullable=True),
        sa.Column("raw_response", sa.Text, nullable=True),
        sa.Column("tokens_in", sa.Integer, nullable=True),
        sa.Column("tokens_out", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, server_default="1"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        comment="大模型调用记录",
    )

    # bom_version 表
    op.create_table(
        "bom_version",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clause.block_code"), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("previous_bom_id", sa.Integer, sa.ForeignKey("bom_version.id"), nullable=True),
        sa.Column("semantic_definition", sa.Text, default=""),
        sa.Column("extraction_rules_json", sa.JSON, nullable=True),
        sa.Column("recall_profile_json", sa.JSON, nullable=True),
        sa.Column("full_bom_json", sa.JSON, nullable=True),
        sa.Column("prompt_text", sa.Text, default=""),
        sa.Column("status", sa.String(16), server_default="draft"),
        sa.Column("pipeline_run_id", sa.Integer, nullable=True),
        sa.Column("created_by", sa.String(32), default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        comment="BOM 版本快照",
    )

    # rule_modifications 表
    op.create_table(
        "rule_modifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bom_version_id", sa.Integer, sa.ForeignKey("bom_version.id"), nullable=False, index=True),
        sa.Column("modification_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text, default=""),
        sa.Column("before_text", sa.Text, nullable=True),
        sa.Column("after_text", sa.Text, nullable=True),
        sa.Column("operator", sa.String(32), default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("approver", sa.String(32), nullable=True, comment="审批人"),
        sa.Column("approved_at", sa.DateTime, nullable=True, comment="审批时间"),
        comment="规则修订记录",
    )

    # 外键：pipeline_runs.bom_version_id → bom_version.id
    op.create_foreign_key("fk_pipeline_bom", "pipeline_runs",
                           "bom_version", ["bom_version_id"], ["id"])

    # 外键：bom_version.pipeline_run_id → pipeline_runs.id
    op.create_foreign_key("fk_bom_pipeline", "bom_version",
                           "pipeline_runs", ["pipeline_run_id"], ["id"])


def downgrade() -> None:
    op.drop_table("rule_modifications")
    op.drop_table("bom_version")
    op.drop_table("llm_calls")
    op.drop_table("node_executions")
    op.drop_table("pipeline_runs")
    op.drop_table("clause")