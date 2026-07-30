"""语义 BOM 核心产物契约。"""

from __future__ import annotations
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional
from datetime import datetime

from ..enums import BomSource, BOMStatus


class ExtractionRule(BaseModel):
    rule: str = Field(..., description="纯规则逻辑（命中/提取条件）, 不改写 platform 预期输出")
    scene: str = Field("", description="场景名（如「供应商主动付款」「退款推演陷阱」），用于分场景归属")
    logic: str = Field("", max_length=120, description="拦截/匹配逻辑，引导推理（限长 120，防 LLM 写长段稀释提示词）")
    fixes: str = Field("", description="修订依据（人审用，不录入 platform 规则）")


class ExtractionRules(BaseModel):
    absolute_interception_rules: List[ExtractionRule] = Field(
        default_factory=list, description="绝对拦截规则（命中即放弃，针对误抽）"
    )
    core_match_rules: List[ExtractionRule] = Field(
        default_factory=list, description="核心匹配规则（提取条件，针对漏抽）"
    )
    poison_words: List[str] = Field(
        default_factory=list, description="毒药词（一票否决，命中即放弃）"
    )

    @model_validator(mode="after")
    def _normalize_poison_words(self) -> "ExtractionRules":
        """契约自守：去重(保序) + trim + 去空。"""
        self.poison_words = list(dict.fromkeys(
            w.strip() for w in self.poison_words if w and w.strip()
        ))
        return self


class SceneJudgment(BaseModel):
    """判例分析：脱敏后的正反例短句 + 分析逻辑，进提示词以引导推理。"""
    scene: str = Field(..., description="场景名")
    negative_case: str = Field("", description="脱敏反例短句")
    positive_case: str = Field("", description="脱敏正例短句")
    analysis: str = Field("", description="分析逻辑（为何此场景需如此判定）")


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
    negative_examples: List[str] = Field(
        default_factory=list, description="反例召回锚点（不进提示词，无分析）"
    )


class TypicalExample(BaseModel):
    """典型正例 + 分析理由（进提示词【正向抽取示例】段，锚定匹配规则）。"""
    value: str = Field(..., description="正例值")
    reason: str = Field("", description="分析理由：为何命中（引用匹配规则）+ 不触发拦截")


class InterceptionExample(BaseModel):
    """典型反例（误抽内容）+ 分析理由（进提示词【反向拦截示例】段，锚定拦截规则）。

    与 TypicalExample 对称：正例锚定匹配规则（为什么命中），反例锚定拦截规则/毒药词（为什么排除）。
    """
    value: str = Field(..., description="误抽内容（不应抽出但被抽了）")
    reason: str = Field("", description="分析理由：为何排除（引用拦截规则/毒药词）")


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
    reasoning_chain: List[str] = Field(
        default_factory=list, description="思维链/排雷步骤，进提示词引导推理"
    )
    scene_judgments: List[SceneJudgment] = Field(
        default_factory=list, description="判例分析（脱敏正反例 + 分析逻辑）"
    )
    typical_examples: List[TypicalExample] = Field(
        default_factory=list, description="典型正例+分析理由，进提示词【正向抽取示例】段（锚定匹配规则）"
    )
    interception_examples: List[InterceptionExample] = Field(
        default_factory=list, description="典型反例(误抽)+分析理由，进提示词【反向拦截示例】段（锚定拦截规则）"
    )
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


BOM.model_rebuild()
ExtractionRules.model_rebuild()
RecallProfile.model_rebuild()
TypicalExample.model_rebuild()
InterceptionExample.model_rebuild()
