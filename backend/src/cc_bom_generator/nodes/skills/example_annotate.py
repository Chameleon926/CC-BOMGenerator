"""Skill: 典型正例标注 —— LLM 生成锚定 BOM 规则的分析理由 + 程序化一致性校验。

排在 DefinitionRule（BOM 规则就位）+ ProfileBuild 之后、PromptAssemble 之前。
吃 selected_examples（Skill2 选的代表正例）+ BOM 规则 → 产 typical_examples[{value,reason}]。
一致性校验：每个正例 vs BOM 规则，被拦截/未覆盖 → 红旗落日志（不一致= BOM 有问题）。
"""

from __future__ import annotations

from ..base import BaseSkill
from ._example_annotate_logic import annotate_typical_examples
from ._prompt_logic import _format_interception, _format_match, _format_poison_words
from ...llm.client import call_json, render_prompt
from ...logging_config import get_logger
from ...schemas.generation_state import GenerationState

log = get_logger("nodes.skills.example_annotate")


class ExampleAnnotateSkill(BaseSkill):
    name = "ExampleAnnotateSkill"
    use_llm = True
    temperature = 0.2  # 理由要稳定、可复现

    def execute(self, state: GenerationState) -> GenerationState:
        if state.bom is None:
            raise RuntimeError("ExampleAnnotateSkill 需要 state.bom（DefinitionRuleSkill 必须先执行）")
        print(f"  [{self.name}] 典型正例标注（大模型，温度 {self.temperature}）...")

        # 典型正例值：优先 Skill2 选的 selected_examples；退化用 positive_values 前 5
        if state.selected_examples:
            values = [ex.expected_value for ex in state.selected_examples]
        else:
            values = (state.cleaned.positive_values or [])[:5]
        if not values:
            print(f"  [{self.name}] 无正例，typical_examples 留空")
            state.bom.typical_examples = []
            return state

        rules = state.bom.extraction_rules
        user_prompt = render_prompt(
            "example_annotate",
            clause=state.bom.clause,
            definition=state.bom.semantic_definition or "（无）",
            interception_rules=_format_interception(rules.absolute_interception_rules),
            poison_words=_format_poison_words(rules.poison_words),
            match_rules=_format_match(rules.core_match_rules),
            selected_examples="\n".join(f"{i}. {v}" for i, v in enumerate(values, 1)),
            misextract_section=(
                f"\n【误抽内容（反例）】\n" + "\n".join(f"{i}. {v}" for i, v in enumerate(state.selected_misextract, 1))
                if state.selected_misextract else ""
            ),
        )
        # ---- 正例标注（锚定匹配规则）----
        messages = [{"role": "user", "content": user_prompt}]
        result = call_json(messages, temperature=self.temperature, max_retries=2)

        reasons_raw = result.get("reasons") if isinstance(result, dict) else None
        if not isinstance(reasons_raw, list):
            reasons_raw = []
        reasons = [str(r).strip() for r in reasons_raw]
        if len(reasons) < len(values):
            reasons = reasons + [""] * (len(values) - len(reasons))
        else:
            reasons = reasons[:len(values)]

        typical, flags = annotate_typical_examples(values, reasons, state.bom)
        state.bom.typical_examples = typical

        # ---- 反例标注（锚定拦截规则/毒药词）----
        interception = []
        if state.selected_misextract:
            neg_reasons_raw = result.get("negative_reasons") if isinstance(result, dict) else None
            if not isinstance(neg_reasons_raw, list):
                neg_reasons_raw = []
            neg_reasons = [str(r).strip() for r in neg_reasons_raw]
            mis_values = state.selected_misextract
            if len(neg_reasons) < len(mis_values):
                neg_reasons = neg_reasons + [""] * (len(mis_values) - len(neg_reasons))
            else:
                neg_reasons = neg_reasons[:len(mis_values)]
            from ._example_annotate_logic import annotate_interception_examples
            interception, neg_flags = annotate_interception_examples(mis_values, neg_reasons, state.bom)
            flags.extend(neg_flags)

        state.bom.interception_examples = interception

        if flags:
            for f in flags:
                log.warning(f"[示例一致性红旗] {f}")
            print(f"  [{self.name}] ⚠️ {len(flags)} 条一致性红旗（见日志）")
        print(f"  [{self.name}] 标注 {len(typical)} 个正例 + {len(interception)} 个反例（带分析理由）")
        return state
