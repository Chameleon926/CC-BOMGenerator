"""迁移 0002: 三方审查后 v2 schema（12 张表）。"""

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # ---- 删旧表（0001 建的 6 张 + alembic 补的 FK）----
    op.drop_constraint("fk_pipeline_bom", "pipeline_runs", type_="foreignkey")
    op.drop_constraint("fk_bom_pipeline", "bom_version", type_="foreignkey")
    op.drop_table("rule_modifications")
    op.drop_table("bom_version")
    op.drop_table("llm_calls")
    op.drop_table("node_executions")
    op.drop_table("pipeline_runs")
    op.drop_table("clause")

    # ---- 建 v2 表 ----

    # 1. clauses
    op.create_table(
        "clauses",
        sa.Column("block_code", sa.String(64), primary_key=True),
        sa.Column("block_name", sa.String(128), nullable=False),
        sa.Column("domain", sa.String(32), nullable=False, server_default=""),
        sa.Column("current_version", sa.Integer, server_default="0"),
        sa.Column("coverage_threshold", sa.Float, server_default="0.8"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("block_code", "domain", name="uq_clause_domain"),
    )

    # 2. clause_items
    op.create_table(
        "clause_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=False),
        sa.Column("item_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("block_code", "item_code", name="uq_clause_item"),
    )

    # 3. pipeline_runs
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("run_status", sa.String(16), server_default="running"),
        sa.Column("input_cleaned_json", sa.JSON),
        sa.Column("output_bom_json", sa.JSON),
        sa.Column("output_prompt_text", sa.Text),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("retry_rounds_json", sa.JSON),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
    )
    op.create_index("ix_pipeline_runs_block_code", "pipeline_runs", ["block_code"])

    # 4. node_executions
    op.create_table(
        "node_executions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pipeline_run_id", sa.Integer, sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_name", sa.String(64), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("retry_round", sa.Integer, server_default="0"),
        sa.Column("is_retry", sa.Boolean, server_default="0"),
        sa.Column("input_json", sa.JSON),
        sa.Column("output_json", sa.JSON),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("success", sa.Boolean, server_default="1"),
    )
    op.create_index("ix_node_executions_run", "node_executions", ["pipeline_run_id"])

    # 5. llm_calls
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("node_execution_id", sa.Integer, sa.ForeignKey("node_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("api_format", sa.String(16), server_default="openai"),
        sa.Column("model_name", sa.String(64), server_default=""),
        sa.Column("temperature", sa.Float, server_default="0.3"),
        sa.Column("max_retries", sa.Integer, server_default="1"),
        sa.Column("system_prompt", sa.Text),
        sa.Column("user_prompt", sa.Text),
        sa.Column("assistant_response", sa.Text),
        sa.Column("raw_response", sa.Text),
        sa.Column("tokens_in", sa.Integer),
        sa.Column("tokens_out", sa.Integer),
        sa.Column("cost", sa.Numeric(10, 6)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("success", sa.Boolean, server_default="1"),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_calls_node", "llm_calls", ["node_execution_id"])
    op.create_index("ix_llm_calls_created", "llm_calls", ["created_at"])

    # 6. bom_versions
    op.create_table(
        "bom_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("bom_source", sa.String(16), nullable=False),
        sa.Column("previous_bom_id", sa.Integer, sa.ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("succeeded_by_id", sa.Integer, sa.ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("bom_status", sa.String(16), server_default="draft"),
        sa.Column("semantic_definition", sa.Text),
        sa.Column("full_bom_json", sa.JSON),
        sa.Column("prompt_text", sa.Text),
        sa.Column("prompt_version", sa.String(32), server_default=""),
        sa.Column("pipeline_run_id", sa.Integer, sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.String(32), server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("block_code", "version", name="uq_bom_version"),
    )
    op.create_index("ix_bom_versions_block_code", "bom_versions", ["block_code"])

    # 7. rule_modifications
    op.create_table(
        "rule_modifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bom_version_id", sa.Integer, sa.ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("modification_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("before_json", sa.JSON),
        sa.Column("after_json", sa.JSON),
        sa.Column("operator", sa.String(32), server_default=""),
        sa.Column("approver", sa.String(32), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_rule_mods_bom", "rule_modifications", ["bom_version_id"])

    # 8. test_set_imports
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

    # 9. platform_runs
    op.create_table(
        "platform_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("bom_version_id", sa.Integer, sa.ForeignKey("bom_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accuracy", sa.Float),
        sa.Column("miss_count", sa.Integer, server_default="0"),
        sa.Column("fp_count", sa.Integer, server_default="0"),
        sa.Column("total_samples", sa.Integer, server_default="0"),
        sa.Column("platform_batch", sa.String(64)),
        sa.Column("imported_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_platform_runs_block", "platform_runs", ["block_code"])

    # 10. badcases
    op.create_table(
        "badcases",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("platform_run_id", sa.Integer, sa.ForeignKey("platform_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_code", sa.String(64), sa.ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False),
        sa.Column("doc_id", sa.String(128)),
        sa.Column("case_type", sa.String(16), nullable=False),
        sa.Column("expected", sa.Text),
        sa.Column("actual", sa.Text),
        sa.Column("overall_coverage", sa.Float),
        sa.Column("segment_coverage", sa.Float),
        sa.Column("reason", sa.String(256)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_badcases_run", "badcases", ["platform_run_id"])

    # 11. diagnoses
    op.create_table(
        "diagnoses",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("badcase_id", sa.Integer, sa.ForeignKey("badcases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("root_cause", sa.Text),
        sa.Column("suggested_fix", sa.Text),
        sa.Column("fix_target", sa.String(16), server_default="rules"),
        sa.Column("confidence", sa.String(8), server_default="中"),
        sa.Column("trace_available", sa.Boolean, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_diagnoses_badcase", "diagnoses", ["badcase_id"])

    # 12. desensitization_logs
    op.create_table(
        "desensitization_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("operator", sa.String(32), nullable=False),
        sa.Column("operation_type", sa.String(16), nullable=False),
        sa.Column("block_code", sa.String(64)),
        sa.Column("doc_ids", sa.Text),
        sa.Column("rule_version", sa.String(32)),
        sa.Column("mapping_snapshot", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("desensitization_logs")
    op.drop_table("diagnoses")
    op.drop_table("badcases")
    op.drop_table("platform_runs")
    op.drop_table("test_set_imports")
    op.drop_table("rule_modifications")
    op.drop_table("bom_versions")
    op.drop_table("llm_calls")
    op.drop_table("node_executions")
    op.drop_table("pipeline_runs")
    op.drop_table("clause_items")
    op.drop_table("clauses")