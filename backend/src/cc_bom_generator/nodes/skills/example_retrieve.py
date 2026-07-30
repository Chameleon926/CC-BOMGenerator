"""Skill 2: 示例匹配 —— TF-IDF + KMeans 聚类选代表性正例。不用大模型。"""

from __future__ import annotations

from ..base import BaseSkill
from ._keyword_logic import _select_diverse, _select_diverse_indices, select_prompt_misextract
from ...schemas.generation_state import GenerationState


class ExampleRetrieveSkill(BaseSkill):
    name = "ExampleRetrieveSkill"
    use_llm = False

    def execute(self, state: GenerationState) -> GenerationState:
        print(f"  [{self.name}] 正例挑选（聚类，不用大模型）...")

        rows = state.cleaned.positive_examples
        if rows:
            # 优先在全行上聚类（保留 doc_id），选出代表正例
            values = [r.expected_value for r in rows]
            idxs = _select_diverse_indices(values, n=state.num_examples)
            selected = [rows[i] for i in idxs]
            state.selected_examples = selected                       # 行结构（带 doc_id），result/追溯用
            state.selected_values = [r.expected_value for r in selected]  # 字符串，prompt 组装/校验用
        else:
            # 退化（无行结构，旧简版数据）：在去重字符串上选，selected_examples 留空
            state.selected_values = _select_diverse(state.cleaned.positive_values, n=5)
            state.selected_examples = []

        print(
            f"  [{self.name}] 选出 {len(state.selected_values)} 个代表性正例"
            f"（带 doc_id 行: {len(state.selected_examples)}）"
        )

        # ---- 反例选取（误抽值去重 + 相似度排序 + TOP N）----
        if state.misextract_values:
            state.selected_misextract = select_prompt_misextract(
                state.misextract_values,
                state.cleaned.positive_values,
                cap=state.num_interception_examples,
            )
            print(
                f"  [{self.name}] 选取 {len(state.selected_misextract)} 个反例进提示词"
                f"（去重后 {len(set(state.misextract_values))} 条，取 TOP {state.num_interception_examples}）"
            )
        else:
            state.selected_misextract = []
            print(f"  [{self.name}] 无误抽值，跳过反例选取")

        return state
