"""SQLAlchemy ORM 模型 —— 版本追溯 + LLM 交互 + 管线执行 + 修订原因。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, Boolean,
    ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import relationship

from . import Base


# ==================== 核心模型 ====================

class Clause(Base):
    """条款注册表。"""
    __tablename__ = "clause"

    block_code = Column(String(64), primary_key=True, comment="语义块编码")
    block_name = Column(String(128), nullable=False, comment="条款名称")
    domain = Column(String(32), default="", comment="业务域（采购/销售/服务/工程/框架）")
    current_version = Column(Integer, default=0, comment="当前最新 BOM 版本号")

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class BomVersion(Base):
    """BOM 版本快照 —— 每版 BOM + 提示词 + LLM 调用链路。"""
    __tablename__ = "bom_version"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clause.block_code"), nullable=False, index=True)
    version = Column(Integer, nullable=False, comment="版本号，自增")

    # 来源
    source = Column(String(16), nullable=False, comment="generate / optimize / manual")
    previous_bom_id = Column(Integer, ForeignKey("bom_version.id"), nullable=True, comment="基于哪个版本优化而来")

    # BOM 快照（三个核心字段分拆，方便前端高亮 diff）
    semantic_definition = Column(Text, default="", comment="语义定义")
    extraction_rules_json = Column(JSON, default=dict, comment="抽取规则 JSON")
    recall_profile_json = Column(JSON, default=dict, comment="召回画像 JSON")

    # 完整产物
    full_bom_json = Column(JSON, default=dict, comment="完整 BOM JSON")
    prompt_text = Column(Text, default="", comment="该版本对应的完整提示词")

    # 状态
    status = Column(String(16), default="draft", comment="draft / reviewed / deactivated")

    # 管线执行
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), nullable=True, comment="对应的管线执行记录")

    # 审计
    created_by = Column(String(32), default="", comment="操作人")
    created_at = Column(DateTime, default=datetime.now)

    # 关系
    clause = relationship("Clause", foreign_keys=[block_code])
    previous_bom = relationship("BomVersion", remote_side=[id], foreign_keys=[previous_bom_id])


# ==================== 管线执行追溯 ====================

class PipelineRun(Base):
    """每次 generate / optimize 管线执行记录。"""
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    block_code = Column(String(64), ForeignKey("clause.block_code"), nullable=False, index=True)
    mode = Column(String(16), nullable=False, comment="generate / optimize")
    status = Column(String(16), default="running", comment="running / success / fail")

    # 入参/产出快照
    input_cleaned_json = Column(JSON, default=dict, comment="入参快照（CleanedTestSet）")
    output_bom_json = Column(JSON, nullable=True, comment="产出 BOM JSON（最终版）")
    output_prompt_text = Column(Text, default="", comment="产出完整提示词")

    # 性能
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True, comment="总耗时")
    error_message = Column(Text, nullable=True, comment="错误信息（fail 时填写）")

    # 回修记录
    retry_count = Column(Integer, default=0, comment="回修次数")
    bom_version_id = Column(Integer, ForeignKey("bom_version.id"), nullable=True, comment="产出的 BOM 版本")

    # 关系
    clause = relationship("Clause", foreign_keys=[block_code])
    nodes = relationship("NodeExecution", back_populates="pipeline_run")


class NodeExecution(Base):
    """每个 Skill 节点的执行记录。"""
    __tablename__ = "node_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id = Column(Integer, ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    skill_name = Column(String(64), nullable=False, comment="Skill 名称，如 DefinitionRuleSkill")
    sequence = Column(Integer, nullable=False, comment="执行顺序（1/2/3...）")
    is_retry = Column(Boolean, default=False, comment="是否是回修执行")

    # 输入/输出快照
    input_json = Column(JSON, nullable=True, comment="输入快照")
    output_json = Column(JSON, nullable=True, comment="输出快照（LLM 回调时记录）")

    # 性能
    started_at = Column(DateTime, default=datetime.now)
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)

    # 关系
    pipeline_run = relationship("PipelineRun", back_populates="nodes")
    llm_calls = relationship("LlmCall", back_populates="node_execution")


class LlmCall(Base):
    """每次大模型调用的完整记录。"""
    __tablename__ = "llm_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_execution_id = Column(Integer, ForeignKey("node_executions.id"), nullable=True, index=True)

    api_format = Column(String(16), default="openai", comment="openai / anthropic")
    model = Column(String(64), default="", comment="使用的模型名称")
    temperature = Column(Float, default=0.3)
    max_retries = Column(Integer, default=1)

    # 核心：完整的输入输出
    system_prompt = Column(Text, nullable=True, comment="system prompt 内容")
    user_prompt = Column(Text, nullable=True, comment="user prompt 内容")
    assistant_response = Column(Text, nullable=True, comment="assistant 返回文本")
    raw_response = Column(Text, nullable=True, comment="原始返回（含 thinking 等）")

    # 调用结果
    tokens_in = Column(Integer, nullable=True, comment="输入 tokens（非精确，后端有项即填）")
    tokens_out = Column(Integer, nullable=True, comment="输出 tokens")
    duration_ms = Column(Integer, nullable=True, comment="此次调用的网络耗时")
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True, comment="失败时的错误信息")

    created_at = Column(DateTime, default=datetime.now)

    # 关系
    node_execution = relationship("NodeExecution", back_populates="llm_calls")


# ==================== 修订原因 ====================

class RuleModification(Base):
    """每次规则/定义改动的记录（为什么改、谁改的）。"""
    __tablename__ = "rule_modifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bom_version_id = Column(Integer, ForeignKey("bom_version.id"), nullable=False, index=True)
    modification_type = Column(String(32), nullable=False, comment="definition / interception / match / keyword / confusion / profile")
    reason = Column(Text, default="", comment="为什么改（fixes字段内容）")

    # 改动前后的内容（用于 diff 高亮）
    before_text = Column(Text, nullable=True, comment="改动前的内容")
    after_text = Column(Text, nullable=True, comment="改动后的内容")

    operator = Column(String(32), default="", comment="操作人")
    created_at = Column(DateTime, default=datetime.now)

    bom_version = relationship("BomVersion", foreign_keys=[bom_version_id])