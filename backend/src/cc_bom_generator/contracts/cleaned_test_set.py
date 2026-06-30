"""A 模块 → B 模块交接契约 + B 模块最终输出契约。"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List

from .bom import BOM


class CleanedTestSet(BaseModel):
    """A 模块清洗后交付给 B 模块的测试集。"""
    clause: str = Field("", description="条款名称")
    block_code: str = Field("", description="语义块编码")
    domain: str = Field("", description="业务域（采购/销售/服务/工程/框架）")

    positive_values: List[str] = Field(
        default_factory=list, description="去重后的期望值列表（正例，已清洗）"
    )
    positive_contexts: List[str] = Field(
        default_factory=list, description="对应的上下文原文（可选）"
    )

    # 去重统计（可选）
    original_count: int = Field(0, description="原始标注数")
    after_dedup: int = Field(0, description="去重后数量")

    # 章节信息（如果有）
    section_paths: List[str] = Field(
        default_factory=list, description="章节路径列表（从 Excel 的 sectionPath 列统计）"
    )


class FullPrompt(BaseModel):
    """B 模块组装的完整提示词，可直接粘贴到旧平台使用。"""
    clause: str = Field("", description="条款名称")
    prompt_text: str = Field("", description="完整提示词文本")
    bom_snapshot: BOM = Field(..., description="对应的 BOM 快照（可追溯）")
    assembled_from: List[str] = Field(
        default_factory=list, description="用了哪些组件组装"
    )
