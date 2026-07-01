"""Skill 2: 示例匹配 —— TF-IDF + KMeans 聚类选代表性正例。不用大模型。"""

from __future__ import annotations

from ..base import BaseSkill
from ._keyword_logic import _select_diverse
from ...contracts.generation_state import GenerationState


class ExampleRetrieveSkill(BaseSkill):
    name = "ExampleRetrieveSkill"
    use_llm = False

    def execute(self, state: GenerationState) -> GenerationState:
        print(f"  [{self.name}] 正例挑选（聚类，不用大模型）...")

        examples = _select_diverse(state.cleaned.positive_values, n=5)

        state.positive_examples = examples
        print(f"  [{self.name}] 选出 {len(examples)} 个代表性正例")
        return state
