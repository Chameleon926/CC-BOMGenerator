"""Badcase 归因诊断与规则自检契约。"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List

from ..enums import DiagnosisCategory, ConfidenceLevel, FixTarget, CaseType, RootComponent, Severity


class DiagnosisResult(BaseModel):
    case_id: str = Field(..., description="badcase 标识")
    case_type: CaseType = Field(..., description="漏抽/误抽")
    category: DiagnosisCategory = Field(..., description="5 类归因")
    reason: str = Field("", description="根因分析（文字）")
    suggested_fix: str = Field("", description="建议修法")
    fix_target: FixTarget = Field(FixTarget.RULES, description="修复落点: rules→改规则, recall_profile→改画像, both→两者都改")
    confidence: ConfidenceLevel = Field(ConfidenceLevel.MEDIUM, description="归因置信度（无 trace 时为低）")
    trace_available: bool = Field(False, description="是否有 trace 证据")
    root_component: RootComponent = Field(RootComponent.EXTRACTION, description="归因路由：extraction→进 optimize；dq→交新平台")
    severity: Severity = Field(Severity.NORMAL, description="normal/fatal（方向·主体·金额反转=fatal）")


class Verification(BaseModel):
    """Stage3 规则自检结果。"""
    checks: List[dict] = Field(default_factory=list, description="逐条验证结果（正例/反例）")
    red_flags: List[str] = Field(default_factory=list, description="红旗（必须修复的问题）")
    coverage_estimate: str = Field("", description="覆盖估计, 如 '正例 5/6 ≈ 83%'")
    summary: str = Field("", description="结论: 可直接用 / 需调整")