"""Skill 1: 特征挖掘 —— jieba 分词 + 词频统计 + 关键词过滤 + 混淆词。不用大模型。"""

from __future__ import annotations

from ..base import BaseSkill
from ._keyword_logic import extract_keywords, _filter_keywords, _extract_confusion
from ...contracts.generation_state import GenerationState


class FeatureExtractSkill(BaseSkill):
    name = "FeatureExtractSkill"
    use_llm = False

    def execute(self, state: GenerationState) -> GenerationState:
        print(f"  [{self.name}] 特征挖掘（统计，不用大模型）...")

        # 复用现有 keyword_extract，但只要关键词和混淆词（不要正例）
        keywords, confusion_words, _ = extract_keywords(
            state.cleaned, top_n=state.nkw
        )

        state.keywords = keywords
        state.confusion_words = confusion_words
        print(f"  [{self.name}] 关键词({len(keywords)}): {keywords[:5]}...")
        print(f"  [{self.name}] 混淆词({len(confusion_words)}): {confusion_words[:3]}...")
        return state
