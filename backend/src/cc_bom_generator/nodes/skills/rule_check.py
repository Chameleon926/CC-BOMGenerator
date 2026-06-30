"""Skill 5: 程序化规则校验 —— 把拦截规则落成正则，在正例上实跑。不用大模型。

准确率保障：确定性检查，替代 LLM 盲测。
- 正例被拦截规则命中 = 硬错误
- 匹配规则关键词对正例的命中率 = 覆盖率代理
"""

from __future__ import annotations

import re
from typing import List

from ..base import BaseSkill
from ...contracts.generation_state import GenerationState


class RuleCheckSkill(BaseSkill):
    name = "RuleCheckSkill"
    use_llm = False

    def execute(self, state: GenerationState) -> GenerationState:
        if state.bom is None:
            raise RuntimeError("RuleCheckSkill 需要 state.bom")

        print(f"  [{self.name}] 程序化规则校验（不用大模型）...")

        positives = state.positive_examples or state.cleaned.positive_values
        interception_rules = state.bom.extraction_rules.absolute_interception_rules
        match_rules = state.bom.extraction_rules.core_match_rules

        # 从拦截规则中提取关键词/正则模式
        interception_keywords = _extract_rule_keywords(interception_rules)
        # 从匹配规则中提取关键词
        match_keywords = _extract_rule_keywords(match_rules)

        # 1. 正例被拦截规则命中 = 硬错误
        killed = []
        for ex in positives:
            for kw in interception_keywords:
                if kw and len(kw) >= 2 and kw in ex:
                    killed.append({"example": ex[:40], "killed_by": kw})
                    break

        # 2. 匹配规则对正例的命中率
        hit = 0
        miss = []
        for ex in positives:
            matched = any(kw and len(kw) >= 2 and kw in ex for kw in match_keywords)
            if matched:
                hit += 1
            else:
                miss.append(ex[:40])

        hit_rate = hit / len(positives) if positives else 0

        state.rule_check_passed = len(killed) == 0
        state.rule_check_details = {
            "interception_keywords": interception_keywords,
            "match_keywords": match_keywords,
            "killed_examples": killed,
            "hit_rate": f"{hit}/{len(positives)} = {hit_rate:.0%}",
            "missed_examples": miss,
        }

        if killed:
            print(f"  [{self.name}] ❌ {len(killed)} 个正例被拦截规则误杀！")
            for k in killed:
                print(f"           '{k['example']}...' 被关键词 '{k['killed_by']}' 命中")
        else:
            print(f"  [{self.name}] ✅ 无正例被误杀")

        print(f"  [{self.name}] 匹配命中率: {hit}/{len(positives)} = {hit_rate:.0%}")
        if miss:
            print(f"  [{self.name}] ⚠️ {len(miss)} 个正例未命中匹配规则关键词（可能规则太窄）")

        return state


def _extract_rule_keywords(rules) -> List[str]:
    """从规则的 rule 文本中提取引号内的词和明显的关键词。"""
    keywords = []
    for rule_obj in rules:
        text = rule_obj.rule if hasattr(rule_obj, 'rule') else str(rule_obj)
        # 提取引号内的词（中文引号和英文引号）
        quoted = re.findall(r'[""\']([^""\']{2,8})[""\']', text)
        keywords.extend(quoted)
        # 提取→后面的词
        arrows = re.findall(r'[→>]([^，,。.]{2,8})', text)
        keywords.extend(arrows)
    # 去重 + 去空
    seen = set()
    result = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw not in seen and len(kw) >= 2:
            seen.add(kw)
            result.append(kw)
    return result
