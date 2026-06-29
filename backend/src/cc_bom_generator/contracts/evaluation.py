"""评估与大盘指标契约。"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional


class RunResult(BaseModel):
    """从平台导入的单条款跑批结果。"""
    block_code: str = Field(..., description="条款编码")
    version: int = Field(..., description="BOM 版本号")
    accuracy: float = Field(0.0, description="准确率")
    miss: int = Field(0, description="漏抽数")
    false_positive: int = Field(0, description="误抽数")
    total_samples: int = Field(0, description="总样本数")
    badcases: List[dict] = Field(default_factory=list, description="错例列表（简化字段）")


class OptGain(BaseModel):
    """一次优化的收益计算。"""
    block_code: str = Field(..., description="条款编码")
    from_version: int = Field(..., description="旧版本")
    to_version: int = Field(..., description="新版本")
    fixed: int = Field(0, description="修复数（旧错→新对）")
    regressed: int = Field(0, description="回归数（旧对→新错）")
    net: int = Field(0, description="净收益 = fixed - regressed")
    missing_guard: List[str] = Field(default_factory=list, description="回归守护告警的条款")


class Metrics(BaseModel):
    """调优成效大盘聚合指标。"""
    overall_accuracy: float = Field(0.0, description="整体准确率")
    accuracy_trend: Optional[float] = Field(None, description="趋势（与上一期相比的百分点变化）")

    total_miss: int = Field(0, description="总漏抽数")
    total_false_positive: int = Field(0, description="总误抽数")

    total_badcases: int = Field(0, description="错例总数")
    diagnosis_breakdown: dict = Field(default_factory=dict, description="归因占比聚合, {'BOM问题':0.41, '召回问题':0.32, ...}")
    diagnosis_details: List[dict] = Field(default_factory=list, description="归因明细（单条类别/置信度）")

    clause_list: List[RunResult] = Field(default_factory=list, description="各条款跑分明细")
    gain_history: List[OptGain] = Field(default_factory=list, description="优化收益历史")
    version_evolution: List[dict] = Field(default_factory=list, description="版本演进历史（版本号/准确率/天数）")