"""Skill 7: 提示词组装 —— 基于 BOM 模板拼装完整提示词。不用大模型。"""

from __future__ import annotations

from ..base import BaseSkill
from ._prompt_logic import assemble_prompt
from ...contracts.generation_state import GenerationState


class PromptAssembleSkill(BaseSkill):
    name = "PromptAssembleSkill"
    use_llm = False

    def execute(self, state: GenerationState) -> GenerationState:
        if state.bom is None:
            raise RuntimeError("PromptAssembleSkill 需要 state.bom")

        print(f"  [{self.name}] 提示词组装（模板拼装，不用大模型）...")

        state.full_prompt = assemble_prompt(state.bom)

        print(f"  [{self.name}] 提示词长度: {len(state.full_prompt.prompt_text)} 字")
        return state
