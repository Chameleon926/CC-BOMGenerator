"""语义 BOM 核心产物契约。"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class BomSource(str, Enum):
    GENERATE = "generate"   # 基于正例初始生成
    OPTIMIZE = "optimize"   # 基于 badcase + trace 优化
    MANUAL = "manual"       # 业务手动写入


class BOMStatus(str, Enum):
    DRAFT = "draft"          # AI 草稿，未审
    REVIEWED = "reviewed"    # 业务已确认
    DEACTIVATED = "deactivated"  # 被新版本取代


class ExtractionRule(BaseModel):
    rule: str = Field(..., description="纯规则逻辑（命中/提取条件）, 不改写 platform 预期输出")
    fixes: str = Field("", description="修订依据（人审用，不录入 platform 规则）")


class ExtractionRules(BaseModel):
    absolute_interception_rules: List[ExtractionRule] = Field(
        default_factory=list, description="绝对拦截规则（命中即放弃，针对误抽）"
    )
    core_match_rules: List[ExtractionRule] = Field(
        default_factory=list, description="核心匹配规则（提取条件，针对漏抽）"
    )


class RecallProfile(BaseModel):
    positive_keywords: List[str] = Field(
        default_factory=list, description="正向关键词（短词，程序化过滤防过拟合）"
    )
    confusion_words: List[str] = Field(
        default_factory=list, description="易混淆词"
    )
    section_hints: List[str] = Field(
        default_factory=list, description="章节提示（预测的合同章节名）"
    )
    semantic_queries: List[str] = Field(
        default_factory=list, description="语义查询句（用于新平台向量召回）"
    )
    positive_examples: List[str] = Field(
        default_factory=list, description="正例参考（召回锚点，不再进抽取提示词）"
    )


class BOM(BaseModel):
    clause: str = Field("", description="条款名称")
    block_code: str = Field("", description="语义块编码")
    version: int = Field(1, description="BOM版本号，自增")
    source: BomSource = Field(BomSource.GENERATE, description="BOM 来源")
    status: BOMStatus = Field(BOMStatus.DRAFT, description="BOM 状态")
    previous_bom_version: Optional[int] = Field(None, description="基于哪个版本优化而来（optimize 时非空）")
    semantic_definition: str = Field("", description="语义定义（自然语言，结尾可附排除说明）")
    extraction_rules: ExtractionRules = Field(
        default_factory=ExtractionRules, description="抽取规则"
    )
    recall_profile: RecallProfile = Field(
        default_factory=RecallProfile, description="召回画像"
    )
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


BOM.model_rebuild()
ExtractionRules.model_rebuild()
RecallProfile.model_rebuild()