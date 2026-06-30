"""Skill 6: 自检+回修 —— LLM 自检（温度 0.0），有红旗时回修1次。"""

from __future__ import annotations

from ..base import BaseSkill
from ..verify import verify_bom, has_blocking_issues
from ...contracts.generation_state import GenerationState


class SelfCheckSkill(BaseSkill):
    name = "SelfCheckSkill"
    use_llm = True
    temperature = 0.0

    def execute(self, state: GenerationState) -> GenerationState:
        if state.bom is None:
            raise RuntimeError("SelfCheckSkill 需要 state.bom")

        if state.skip_verify:
            print(f"  [{self.name}] 跳过自检（skip_verify=True）")
            return state

        print(f"  [{self.name}] 规则自检（大模型，温度 {self.temperature}）...")

        positives = state.positive_examples or state.cleaned.positive_values[:5]

        verification = verify_bom(
            bom=state.bom,
            positive_examples=positives,
        )

        state.verification = verification

        if has_blocking_issues(verification):
            print(f"  [{self.name}] ⚠️ 自检发现 {len(verification.red_flags)} 个红旗")
            for flag in verification.red_flags:
                print(f"           - {flag[:60]}")
        else:
            print(f"  [{self.name}] ✅ 自检通过")

        return state
