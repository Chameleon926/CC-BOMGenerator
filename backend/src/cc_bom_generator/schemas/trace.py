"""Trace 解析契约。"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional


class TraceIO(BaseModel):
    """Trace 输入输出文件引用。"""
    input_path: Optional[str] = Field(None, description="trace 输入文件路径（JSON/txt）")
    output_path: Optional[str] = Field(None, description="trace 输出文件路径（JSON/txt，可选）")
    combined_path: Optional[str] = Field(None, description='合并 trace 文件（含"输入:"/"输出:"标记）')


class StructuredTrace(BaseModel):
    """从 trace 中提取的关键字段（喂给归因诊断使用）。"""
    block_code: Optional[str] = Field(None, description="条款编码")
    block_name: Optional[str] = Field(None, description="条款名称")
    current_rules_profile: Optional[str] = Field(None, description="当前规则与描写叙述")
    context_window: Optional[str] = Field(None, description="合同原文窗口内容")
    model_extracted: Optional[str] = Field(None, description="模型抽取的文本")
    model_reasoning: Optional[str] = Field(None, description="模型的 reasoning 输出")
    chunks: List[dict] = Field(default_factory=list, description="可用 chunks 摘要")
    is_llm_judged: bool = Field(False, description="平台是否使用 LLM 判定此 Badcase")
    llm_verdict: Optional[str] = Field(None, description="LLM 判定的结论文本（若存在）")