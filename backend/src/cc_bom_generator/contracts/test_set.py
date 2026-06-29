"""测试集与 Badcase 契约。"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class Item(BaseModel):
    item_code: str = Field("", description="语义项编码")
    item_name: str = Field("", description="语义项名称")
    expected: str = Field("", description="期望值（空=负例）")


class Block(BaseModel):
    block_code: str = Field("", description="语义块编码（父级）")
    block_name: str = Field("", description="语义块名称")
    context: str = Field("", description="上下文原文（条款期望值或 chunk）")
    items: List[Item] = Field(default_factory=list, description="语义项列表（可空）")


class Document(BaseModel):
    doc_id: str = Field("", description="文档 ID")
    doc_name: str = Field("", description="文档名称")
    domain: str = Field("", description="业务域（采购/销售/服务/工程/框架）")
    blocks: List[Block] = Field(default_factory=list, description="语义块列表")


class TestSet(BaseModel):
    documents: List[Document] = Field(default_factory=list, description="文档列表")


class Badcase(BaseModel):
    case_id: str = Field("", description="badcase 标识, 如 'DOC123_1'")
    doc_id: str = Field("", description="所属文档 ID")
    block_code: str = Field("", description="语义块编码")
    case_type: Literal["miss", "false_positive"] = Field("miss", description="漏抽/误抽")
    expected: str = Field("", description="期望值")
    actual: str = Field("", description="实际抽取值")
    similarity: Optional[float] = Field(None, description="覆盖率/相似度（平台返回）")
    reason: Optional[str] = Field(None, description="平台判定原因")
    text: Optional[str] = Field(None, description="合同原文片段")
    trace_input_path: Optional[str] = Field(None, description="trace 输入文件路径（文本/JSON）")
    trace_output_path: Optional[str] = Field(None, description="trace 输出文件路径（可选）")
    trace_path: Optional[str] = Field(None, description="合并 trace 文件路径（可选）")

    def is_miss(self) -> bool:
        return self.case_type == "miss"

    def is_false_positive(self) -> bool:
        return self.case_type == "false_positive"