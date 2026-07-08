"""Skill 2: 示例匹配 —— TF-IDF + KMeans 聚类选代表性正例。不用大模型。"""

from __future__ import annotations

from ..base import BaseSkill
from ._keyword_logic import _select_diverse, _select_diverse_indices
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
            idxs = _select_diverse_indices(values, n=5)
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
        return state
