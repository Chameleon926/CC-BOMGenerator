"""Skill 3: 定义+规则生成 —— 基于特征词+正例，一次生成语义定义和抽取规则。用大模型，温度 0.2。"""

from __future__ import annotations

from ..base import BaseSkill
from ._generate_logic import generate_definition_and_rules
from ...schemas.generation_state import GenerationState


class DefinitionRuleSkill(BaseSkill):
    name = "DefinitionRuleSkill"
    use_llm = True
    temperature = 0.2

    def __init__(self, current_bom: str = "（无）"):
        self.current_bom = current_bom

    def execute(self, state: GenerationState) -> GenerationState:
        print(f"  [{self.name}] 定义+规则生成（大模型，温度 {self.temperature}）...")

        bom = generate_definition_and_rules(
            cleaned=state.cleaned,
            keywords=state.keywords or None,
            current_bom=self.current_bom,
        )

        state.bom = bom
        print(f"  [{self.name}] 定义: {bom.semantic_definition[:60]}...")
        print(f"  [{self.name}] 拦截规则({len(bom.extraction_rules.absolute_interception_rules)}) + 匹配规则({len(bom.extraction_rules.core_match_rules)})")
        return state
