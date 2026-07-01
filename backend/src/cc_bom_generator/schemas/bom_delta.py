"""optimize 产出的 BOM 改动清单契约（对齐 db.rule_modifications 审计表）。"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional

from ..enums import FixTarget, ModificationType, ModificationAction


class Modification(BaseModel):
    type: ModificationType
    action: ModificationAction = Field(ModificationAction.UPDATE, description="add/update/delete")
    target: str = Field("", description="定位锚点（某条 rule 文本 / 某关键词原文）")
    before: Optional[dict] = Field(None, description="改前片段（对齐 rule_modifications.before_json）")
    after: Optional[dict] = Field(None, description="改后片段（对齐 rule_modifications.after_json）")
    reason: str = Field("", description="改动依据")
    diagnosis_ids: List[str] = Field(default_factory=list, description="反向追溯到触发 badcase")


class BOMDelta(BaseModel):
    block_code: str
    from_version: int = Field(..., description="基于的版本号（存库时 service 转 from_bom_version_id）")
    fix_targets: List[FixTarget]
    modifications: List[Modification] = Field(default_factory=list)
    coverage_note: str = Field("", description="LLM 自评覆盖率影响")
    regression_warnings: List[str] = Field(default_factory=list, description="防回归告警")
