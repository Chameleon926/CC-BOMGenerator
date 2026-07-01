"""
SQLAlchemy ORM 模型（v2）—— 三方审查后定稿。

变更清单（vs v1）：
- 避 MySQL 保留字：source→bom_source, status→bom_status, model→model_name, sequence→seq
- 加唯一约束：(block_code, version) on bom_versions, (block_code, item_code) on clause_items
- 加 ondelete=RESTRICT 到所有 FK
- 所有 created_at/updated_at 用 server_default=func.now()
- 补 approver/approved_at 到 rule_modifications（对齐 alembic 0001）
- 补 succeeded_by_id/prompt_version/updated_at 到 bom_versions
- 补 retry_round 到 node_executions
- 补 coverage_threshold 到 clause
- 补 cost 到 llm_calls
- 补 retry_rounds_json 到 pipeline_runs
- 删 pipeline_runs.bom_version_id（消除环形 FK）
- rule_modifications before/after 改 JSON
- 新增 5 张表：clause_items, platform_runs, badcases, diagnoses, desensitization_logs
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, Boolean, Numeric,
    ForeignKey, JSON, UniqueConstraint, Index,
    func,
)
from sqlalchemy.orm import relationship

from . import Base


class Clause(Base):
    """条款注册表。"""
    __tablename__ = "clauses"

    block_code = Column(String(64), primary_key=True)
    block_name = Column(String(128), nullable=False)
    domain = Column(String(32), nullable=False, server_default="")
    current_version = Column(Integer, server_default="0")
    coverage_threshold = Column(Float, server_default="0.8", comment="覆盖率阈值，默认80%")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("block_code", "domain", name="uq_clause_domain"),
    )


class ClauseItem(Base):
    """条款子项表（item 级语义块）。"""
    __tablename__ = "clause_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False)
    item_code = Column(String(64), nullable=False)
    item_name = Column(String(128), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("block_code", "item_code", name="uq_clause_item"),
    )


class BomVersion(Base):
    """BOM 版本快照。"""
    __tablename__ = "bom_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False, index=True)
    version = Column(Integer, nullable=False)

    bom_source = Column(String(16), nullable=False, comment="generate/optimize/manual")
    previous_bom_id = Column(Integer, ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=True)
    succeeded_by_id = Column(Integer, ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=True, comment="被哪个版本取代")

    bom_status = Column(String(16), server_default="draft", comment="draft/reviewed/deactivated")

    semantic_definition = Column(Text, default="")
    full_bom_json = Column(JSON, comment="完整 BOM JSON（权威真源）")
    prompt_text = Column(Text, default="")
    prompt_version = Column(String(32), server_default="", comment="prompt 模板版本")

    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)

    created_by = Column(String(32), server_default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("block_code", "version", name="uq_bom_version"),
    )


class PipelineRun(Base):
    """管线执行记录。"""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False, index=True)
    mode = Column(String(16), nullable=False, comment="generate/optimize")
    run_status = Column(String(16), server_default="running", comment="running/success/fail")

    input_cleaned_json = Column(JSON)
    output_bom_json = Column(JSON)
    output_prompt_text = Column(Text, default="")

    retry_count = Column(Integer, server_default="0")
    retry_rounds_json = Column(JSON, comment="每轮回修的触发原因数组")

    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    nodes = relationship("NodeExecution", back_populates="pipeline_run")


class NodeExecution(Base):
    """Skill 节点执行记录。"""
    __tablename__ = "node_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_name = Column(String(64), nullable=False)
    seq = Column(Integer, nullable=False, comment="执行顺序")
    retry_round = Column(Integer, server_default="0", comment="0=首次，1+=第几次回修")
    is_retry = Column(Boolean, server_default="0")

    input_json = Column(JSON)
    output_json = Column(JSON)

    started_at = Column(DateTime, server_default=func.now())
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, server_default="1")

    pipeline_run = relationship("PipelineRun", back_populates="nodes")
    llm_calls = relationship("LlmCall", back_populates="node_execution")


class LlmCall(Base):
    """大模型调用记录。"""
    __tablename__ = "llm_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_execution_id = Column(Integer, ForeignKey("node_executions.id", ondelete="SET NULL"), nullable=True, index=True)

    api_format = Column(String(16), server_default="openai")
    model_name = Column(String(64), server_default="", comment="模型名称")
    temperature = Column(Float, server_default="0.3")
    max_retries = Column(Integer, server_default="1")

    system_prompt = Column(Text)
    user_prompt = Column(Text)
    assistant_response = Column(Text)
    raw_response = Column(Text, comment="原始返回（含thinking，排查用）")

    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    cost = Column(Numeric(10, 6), nullable=True, comment="单次调用成本")
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, server_default="1")
    error_message = Column(Text)

    created_at = Column(DateTime, server_default=func.now())

    node_execution = relationship("NodeExecution", back_populates="llm_calls")


class RuleModification(Base):
    """规则修订记录。"""
    __tablename__ = "rule_modifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bom_version_id = Column(Integer, ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=False, index=True)
    modification_type = Column(String(32), nullable=False, comment="definition/interception/match/keyword/confusion/profile")
    reason = Column(Text, server_default="")
    before_json = Column(JSON, comment="改动前内容（结构化）")
    after_json = Column(JSON, comment="改动后内容（结构化）")
    operator = Column(String(32), server_default="")
    approver = Column(String(32), nullable=True, comment="审批人")
    approved_at = Column(DateTime, nullable=True, comment="审批时间")
    created_at = Column(DateTime, server_default=func.now())

    bom_version = relationship("BomVersion", foreign_keys=[bom_version_id])


class TestSetImport(Base):
    """测试集导入追溯。"""
    __tablename__ = "test_set_imports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False)
    file_name = Column(String(256), nullable=False)
    file_hash = Column(String(64), comment="MD5/SHA256，防重复导入")
    original_count = Column(Integer)
    after_dedup = Column(Integer)
    domain = Column(String(32))
    imported_by = Column(String(32), server_default="")
    imported_at = Column(DateTime, server_default=func.now())


class PlatformRun(Base):
    """平台跑分记录。"""
    __tablename__ = "platform_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False, index=True)
    bom_version_id = Column(Integer, ForeignKey("bom_versions.id", ondelete="SET NULL"), nullable=True)
    accuracy = Column(Float)
    miss_count = Column(Integer, server_default="0")
    fp_count = Column(Integer, server_default="0")
    total_samples = Column(Integer, server_default="0")
    platform_batch = Column(String(64), comment="平台跑批号")
    imported_at = Column(DateTime, server_default=func.now())


class Badcase(Base):
    """错例记录。"""
    __tablename__ = "badcases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_run_id = Column(Integer, ForeignKey("platform_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    block_code = Column(String(64), ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False)
    doc_id = Column(String(128))
    case_type = Column(String(16), nullable=False, comment="miss/false_positive")
    expected = Column(Text)
    actual = Column(Text)
    overall_coverage = Column(Float, comment="整体覆盖率")
    segment_coverage = Column(Float, comment="单段覆盖率")
    reason = Column(String(256))
    trace_json = Column(JSON, nullable=True, comment="解析后的 StructuredTrace（无 trace 则 NULL）")
    created_at = Column(DateTime, server_default=func.now())


class Diagnosis(Base):
    """归因诊断。"""
    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    badcase_id = Column(Integer, ForeignKey("badcases.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(16), nullable=False, comment="召回问题/混合问题/BOM问题/Prompt模板待优化/大模型推理问题")
    root_cause = Column(Text)
    suggested_fix = Column(Text)
    fix_target = Column(String(16), server_default="rules", comment="rules/recall_profile/both")
    confidence = Column(String(8), server_default="中", comment="高/中/低")
    trace_available = Column(Boolean, server_default="0")
    created_at = Column(DateTime, server_default=func.now())


class DesensitizationLog(Base):
    """脱敏审计日志。"""
    __tablename__ = "desensitization_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    operator = Column(String(32), nullable=False)
    operation_type = Column(String(16), nullable=False, comment="generate/optimize/manual")
    block_code = Column(String(64))
    doc_ids = Column(Text, comment="涉及文档ID（逗号分隔）")
    rule_version = Column(String(32), comment="脱敏规则版本")
    mapping_snapshot = Column(JSON, comment="脱敏映射表快照")
    created_at = Column(DateTime, server_default=func.now())


class PendingDelta(Base):
    """待审 BOMDelta 队列（optimize 产出，apply 确认后转正式 bom_version）。"""
    __tablename__ = "pending_deltas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clauses.block_code", ondelete="RESTRICT"), nullable=False, index=True)
    from_bom_version_id = Column(Integer, ForeignKey("bom_versions.id", ondelete="RESTRICT"), nullable=False, comment="乐观锁基线版本")
    delta_json = Column(JSON, nullable=False, comment="BOMDelta 完整 JSON")
    status = Column(String(16), server_default="pending", comment="pending/approved/rejected")
    reviewed_by = Column(String(32), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())