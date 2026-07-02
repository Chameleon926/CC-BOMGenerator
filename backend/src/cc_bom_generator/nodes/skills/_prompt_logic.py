"""
B 模块第 5 步：完整提示词组装（不用大模型）

基于 BOM + 画像，组装旧平台可直接粘贴使用的完整提示词。
纯模板拼装，不调大模型。

组装逻辑：
- 从 BOM 提取定义、规则（分场景 + logic）、毒药词、判例分析、思维链、画像
- 渲染 prompts/assemble.txt（{{var}} 占位）
- 输出 FullPrompt 契约
- 正例/反例（positive_examples/negative_examples）为召回锚点，不放提示词
"""

from __future__ import annotations

from ...llm.client import render_prompt
from ...schemas.bom import (
    BOM,
    ExtractionRule,
    ExtractionRules,
    RecallProfile,
    SceneJudgment,
)
from ...schemas.cleaned_test_set import FullPrompt

_PLACEHOLDER = "（无）"


def assemble_prompt(bom: BOM) -> FullPrompt:
    """
    基于 BOM 组装旧平台可用的完整提示词。

    Args:
        bom: 完整 BOM（定义 + 规则 + 画像，经过自检）

    Returns:
        FullPrompt（可直接粘贴到旧平台）
    """
    rules = bom.extraction_rules
    profile = bom.recall_profile

    prompt_text = render_prompt(
        "assemble",
        clause=bom.clause,
        block_code=bom.block_code,
        definition=bom.semantic_definition,
        interception_rules=_format_interception(rules.absolute_interception_rules),
        poison_words=_format_poison_words(rules.poison_words),
        match_rules=_format_match(rules.core_match_rules),
        scene_judgments=_format_scene_judgments(bom.scene_judgments),
        reasoning_chain=_format_reasoning_chain(bom.reasoning_chain),
        positive_keywords=_format_keywords(profile.positive_keywords),
        confusion_words=_format_keywords(profile.confusion_words),
        section_hints=_format_keywords(profile.section_hints),
        semantic_queries=_format_semantic_queries(profile.semantic_queries),
    )

    return FullPrompt(
        clause=bom.clause,
        prompt_text=prompt_text,
        bom_snapshot=bom,
        assembled_from=[
            "定义",
            "拦截规则",
            "毒药词",
            "匹配规则",
            "判例分析",
            "思维链",
            "画像",
        ],
    )


# ==================== 内部格式化函数 ====================

def _format_rule_line(rule: ExtractionRule) -> str:
    """单条规则 → `[场景] 规则（逻辑：logic）`，无 logic 只输出规则。"""
    parts = []
    scene = (rule.scene or "").strip()
    if scene:
        parts.append(f"[{scene}]")
    parts.append(rule.rule)
    logic = (rule.logic or "").strip()
    if logic:
        parts.append(f"（逻辑：{logic}）")
    return " ".join(parts)


def _format_interception(rules: list[ExtractionRule]) -> str:
    """绝对拦截规则：每条 `[场景] 规则（逻辑：logic）`，空 → （无）。"""
    if not rules:
        return _PLACEHOLDER
    lines = []
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. {_format_rule_line(rule)}")
    return "\n".join(lines)


def _format_match(rules: list[ExtractionRule]) -> str:
    """核心匹配规则：每条 `[场景] 规则（逻辑：logic）`，空 → （无）。"""
    if not rules:
        return _PLACEHOLDER
    lines = []
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. {_format_rule_line(rule)}")
    return "\n".join(lines)


def _format_poison_words(words: list[str]) -> str:
    """毒药词：、连接，空 → （无）。"""
    cleaned = [w.strip() for w in words if w and w.strip()]
    if not cleaned:
        return _PLACEHOLDER
    return "、".join(cleaned)


def _format_scene_judgments(judgments: list[SceneJudgment]) -> str:
    """判例分析：每条 `[场景] 反例：x | 正例：y | 分析：z`，空 → （无）。"""
    if not judgments:
        return _PLACEHOLDER
    lines = []
    for j in judgments:
        scene = (j.scene or "").strip()
        head = f"[{scene}]" if scene else ""
        segs = []
        if (j.negative_case or "").strip():
            segs.append(f"反例：{j.negative_case.strip()}")
        if (j.positive_case or "").strip():
            segs.append(f"正例：{j.positive_case.strip()}")
        if (j.analysis or "").strip():
            segs.append(f"分析：{j.analysis.strip()}")
        body = " | ".join(segs) if segs else "（无内容）"
        lines.append(f"{head} {body}".strip())
    return "\n".join(lines)


def _format_reasoning_chain(chain: list[str]) -> str:
    """思维链：编号列表 `1. xxx\\n2. xxx`，空 → （无）。"""
    cleaned = [s.strip() for s in chain if s and s.strip()]
    if not cleaned:
        return _PLACEHOLDER
    lines = [f"{i}. {s}" for i, s in enumerate(cleaned, 1)]
    return "\n".join(lines)


def _format_keywords(words: list[str]) -> str:
    """关键词列表：、连接，空 → （无）。"""
    cleaned = [w.strip() for w in words if w and w.strip()]
    if not cleaned:
        return _PLACEHOLDER
    return "、".join(cleaned)


def _format_semantic_queries(queries: list[str]) -> str:
    """语义查询：换行 · 列表，空 → （无）。"""
    cleaned = [q.strip() for q in queries if q and q.strip()]
    if not cleaned:
        return _PLACEHOLDER
    return "\n".join(f"  · {q}" for q in cleaned)
