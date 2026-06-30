"""Skill 4: 召回画像组装 —— 统计+大模型融合。用大模型，温度 0.5。"""

from __future__ import annotations

from ..base import BaseSkill
from ..profile_build import build_profile
from ...contracts.generation_state import GenerationState


class ProfileBuildSkill(BaseSkill):
    name = "ProfileBuildSkill"
    use_llm = True
    temperature = 0.5

    def execute(self, state: GenerationState) -> GenerationState:
        if state.bom is None:
            raise RuntimeError("ProfileBuildSkill 需要 state.bom（DefinitionRuleSkill 必须先执行）")

        print(f"  [{self.name}] 画像组装（统计+大模型融合，温度 {self.temperature}）...")

        state.bom = build_profile(
            cleaned=state.cleaned,
            bom=state.bom,
            keywords=state.keywords,
            confusion_words=state.confusion_words,
            positive_examples=state.positive_examples,
            nkw=state.nkw,
            nsec=state.nsec,
            nq=state.nq,
        )

        rp = state.bom.recall_profile
        print(f"  [{self.name}] 关键词({len(rp.positive_keywords)}) 混淆词({len(rp.confusion_words)}) 章节({len(rp.section_hints)}) 语义查询({len(rp.semantic_queries)})")
        return state
