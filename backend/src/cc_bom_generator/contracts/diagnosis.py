"""Badcase 归因诊断与规则自检契约。"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class DiagnosisResult(BaseModel):
    case_id: str = Field(..., description="badcase 标识")
    case_type: Literal["miss", "false_positive"] = Field(..., description="漏抽/误抽")
    category: Literal["召回问题", "混合问题", "BOM问题", "Prompt模板待优化", "大模型推理问题"] = Field(
        ..., description="5 类归因"
    )
    reason: str = Field("", description="根因分析（文字）")
    suggested_fix: str = Field("", description="建议修法")
    fix_target: Literal["rules", "recall_profile", "both"] = Field(
        "rules", description="修复落点: rules→改规则, recall_profile→改画像, both→两者都改"
    )
    confidence: Literal["高", "中", "低"] = Field(
        "中", description="归因置信度（无 trace 时为低）"
    )
    trace_available: bool = Field(False, description="是否有 trace 证据")


class Verification(BaseModel):
    """Stage3 规则自检结果。"""
    checks: List[dict] = Field(default_factory=list, description="逐条验证结果（正例/反例）")
    red_flags: List[str] = Field(default_factory=list, description="红旗（必须修复的问题）")
    coverage_estimate: str = Field("", description="覆盖估计, 如 '正例 5/6 ≈ 83%'")
    summary: str = Field("", description="结论: 可直接用 / 需调整")