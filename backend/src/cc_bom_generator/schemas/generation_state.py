"""生成场景流转状态 —— Skill 之间传递的数据载体。"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

from .bom import BOM
from .cleaned_test_set import CleanedTestSet, FullPrompt, PositiveExample
from .diagnosis import Verification


class GenerationState(BaseModel):
    """贯穿整个生成管线的流转状态。每个 Skill 读一部分、写一部分。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ---- 输入（初始化时填入）----
    cleaned: CleanedTestSet
    nkw: int = Field(10, description="关键词数量")
    nsec: int = Field(6, description="章节提示数量")
    nq: int = Field(3, description="语义查询数量")
    num_examples: int = Field(5, description="正例选取数量（典型正例/召回锚点数）")
    skip_verify: bool = Field(False, description="跳过自检")

    # ---- Skill 1 (FeatureExtract) 产出 ----
    keywords: List[str] = Field(default_factory=list, description="正向关键词（统计抽取）")
    confusion_words: List[str] = Field(default_factory=list, description="易混淆词")

    # ---- Skill 2 (ExampleRetrieve) 产出 ----
    # 注意命名：selected_values=选取正例的期望值字符串(prompt/校验用)；selected_examples=对应行(带doc_id,result用)。
    # 两者同源同步：selected_values[i] == selected_examples[i].expected_value。不叫 positive_examples 以免与
    # CleanedTestSet.positive_examples(行) 同名异类型混淆。
    selected_values: List[str] = Field(default_factory=list, description="Skill2 聚类选取代表正例的期望值字符串（prompt 组装/校验用）")
    selected_examples: List[PositiveExample] = Field(default_factory=list, description="Skill2 聚类选取的代表正例（带 doc_id 行结构，result/追溯用）")

    # ---- Skill 3 (DefinitionRule) 产出 ----
    bom: Optional[BOM] = Field(None, description="语义 BOM（逐步填充）")

    # ---- Skill 5 (RuleCheck) 产出 ----
    rule_check_passed: bool = Field(True, description="程序化规则校验是否通过")
    rule_check_details: dict = Field(default_factory=dict, description="校验详情")

    # ---- Skill 6 (SelfCheck) 产出 ----
    verification: Optional[Verification] = Field(None, description="自检结果")

    # ---- Skill 7 (PromptAssemble) 产出 ----
    full_prompt: Optional[FullPrompt] = Field(None, description="完整提示词")

    # ---- 内部状态 ----
    retry_count: int = Field(0, description="回修次数（上限 1）")
