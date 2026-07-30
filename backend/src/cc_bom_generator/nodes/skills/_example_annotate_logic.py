"""典型正例标注逻辑：LLM 生成理由 + 程序化一致性校验。

一致性校验（check_consistency）是纯函数，核心保证：正例理由与 BOM 规则不冲突——
- 正例不该被拦截规则/毒药词命中（命中 → BOM 拦截过宽 或 正例不当）
- 正例该被匹配规则/recall 关键词覆盖（未覆盖 → BOM 匹配过窄 或 正例不当）
红旗 → 进自检/回修（改 BOM，不是让理由将就）。
"""
from __future__ import annotations
from typing import List

from ...schemas.bom import BOM, TypicalExample, InterceptionExample
from .rule_check import _extract_rule_keywords


def check_consistency(value: str, bom: BOM) -> dict:
    """检查正例 value 与 BOM 规则的一致性（纯函数）。

    返回 {intercepted, matched, flags}：
    - intercepted=True（被拦截规则/毒药词命中）→ 红旗
    - matched=False（未被匹配规则/recall 关键词覆盖）→ 红旗
    """
    rules = bom.extraction_rules
    inter_kws = [k for k in _extract_rule_keywords(rules.absolute_interception_rules) if len(k) >= 2]
    match_kws = [k for k in _extract_rule_keywords(rules.core_match_rules) if len(k) >= 2]
    match_kws += [k for k in (bom.recall_profile.positive_keywords or []) if len(k) >= 2]
    poison = [w for w in (rules.poison_words or []) if w and len(w) >= 2]
    v = value or ""

    intercepted_by = [kw for kw in inter_kws if kw in v]
    poisoned_by = [pw for pw in poison if pw in v]
    matched_by = [kw for kw in match_kws if kw in v]

    flags: List[str] = []
    if intercepted_by:
        flags.append(f"被拦截规则关键词命中：{intercepted_by}（BOM 拦截过宽 或 正例不当）")
    if poisoned_by:
        flags.append(f"被毒药词命中：{poisoned_by}")
    if not matched_by:
        flags.append("未被匹配规则/recall 关键词覆盖（BOM 匹配过窄 或 正例不当）")

    return {
        "intercepted": bool(intercepted_by or poisoned_by),
        "matched": bool(matched_by),
        "flags": flags,
    }


def annotate_typical_examples(
    values: List[str],
    reasons: List[str],
    bom: BOM,
) -> tuple[List[TypicalExample], List[str]]:
    """组装 typical_examples + 跑一致性校验，返回 (typical_examples, all_flags)。

    values/reasons 等长（LLM 产）；对每个 value 校验一致性，汇总红旗。
    """
    typical: List[TypicalExample] = []
    all_flags: List[str] = []
    for val, reason in zip(values, reasons):
        typical.append(TypicalExample(value=val, reason=reason or ""))
        ck = check_consistency(val, bom)
        for i, f in enumerate(ck["flags"]):
            all_flags.append(f"正例「{val[:30]}」{f}")
    return typical, all_flags


def annotate_interception_examples(
    values: List[str],
    reasons: List[str],
    bom: BOM,
) -> tuple[List[InterceptionExample], List[str]]:
    """组装 interception_examples + 跑反向一致性校验。

    反向校验：反例内容**不应被匹配规则命中**（命中 = 规则太宽，误抽风险）。
    """
    from .rule_check import _extract_rule_keywords
    interception: List[InterceptionExample] = []
    all_flags: List[str] = []
    match_kws = [k for k in _extract_rule_keywords(bom.extraction_rules.core_match_rules) if len(k) >= 2]
    for val, reason in zip(values, reasons):
        interception.append(InterceptionExample(value=val, reason=reason or ""))
        # 反向校验：误抽内容不应被匹配规则命中
        matched_by = [kw for kw in match_kws if kw in val]
        if matched_by:
            all_flags.append(f"反例「{val[:30]}」被匹配规则关键词命中：{matched_by}（规则太宽）")
    return interception, all_flags
