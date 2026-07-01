"""
B 模块第 5 步：完整提示词组装（不用大模型）

基于 BOM + 画像，组装旧平台可直接粘贴使用的完整提示词。
纯模板拼装，不调大模型。

组装逻辑：
- 从 BOM 提取定义、规则、画像
- 格式化成旧平台兼容的 Prompt 格式
- 输出 FullPrompt 契约
"""

from __future__ import annotations

from ...schemas.bom import BOM, ExtractionRules, RecallProfile
from ...schemas.cleaned_test_set import FullPrompt


def assemble_prompt(bom: BOM) -> FullPrompt:
    """
    基于 BOM 组装旧平台可用的完整提示词。

    Args:
        bom: 完整 BOM（定义 + 规则 + 画像，经过自检）

    Returns:
        FullPrompt（可直接粘贴到旧平台）
    """
    rules_text = _format_rules(bom.extraction_rules)
    profile_text = _format_profile(bom.recall_profile)

    prompt_text = _TEMPLATE.format(
        clause=bom.clause,
        block_code=bom.block_code,
        definition=bom.semantic_definition,
        rules=rules_text,
        profile=profile_text,
    )

    return FullPrompt(
        clause=bom.clause,
        prompt_text=prompt_text,
        bom_snapshot=bom,
        assembled_from=["定义", "规则", "画像"],
    )


# ==================== 模板 ====================

_TEMPLATE = """你是一个专业的合同条款抽取助手。请从以下合同原文窗口中抽取语义块：{clause}（{block_code}）。

目标定义：{definition}

【抽取规则 — 必须严格遵守】
{rules}

【目标画像】
{profile}

--- 合同原文窗口 ---

（在此粘贴合同原文）

--- 输出格式 ---
请以 JSON 格式返回抽取结果，严格按照以下 Schema：
```json
{{
  "type": "object",
  "properties": {{
    "blockExtractions": {{
      "type": "array",
      "items": {{
        "type": "object",
        "properties": {{
          "targetType": {{"type": "string", "enum": ["block"]}},
          "blockCode": {{"type": "string"}},
          "status": {{"type": "string", "enum": ["extracted", "unknown", "partial", "needs_review"]}},
          "blockText": {{"type": "string", "description": "从原文中抽取的连续语义块文本片段"}},
          "sourceChunkIds": {{"type": "array", "items": {{"type": "string"}}}},
          "reasoning": {{"type": "string"}}
        }},
        "required": ["targetType", "blockCode", "status", "blockText", "sourceChunkIds"]
      }}
    }}
  }},
  "required": ["blockExtractions"]
}}
```"""


# ==================== 内部格式化函数 ====================

def _format_rules(rules: ExtractionRules) -> str:
    """把抽取规则格式化成提示词文本。"""
    lines = []

    # 拦截规则
    if rules.absolute_interception_rules:
        lines.append("### 1. 命中规则（下面3点命中其中一条即可抽取）")
    else:
        lines.append("### 1. 命中规则")

    if rules.core_match_rules:
        for i, rule in enumerate(rules.core_match_rules, 1):
            lines.append(f"{i}. {rule.rule}")
    else:
        lines.append("（无显式匹配规则，依据目标定义语义判断）")

    lines.append("")

    # 拦截规则
    lines.append("### 2. 否定规则")
    lines.append('- 如果整个合同文本中没有任何条款符合上述语义匹配规则，则输出"无"，严禁输出业务定义、示例或任何解释性文字。')
    lines.append('- 仅有词无内容，即条款中出现了目标术语，但完全没有给出任何具体内容。')
    lines.append('- 仅流程无实质，仅说明"需要提交"这个动作，未说明需要提交什么。')

    if rules.absolute_interception_rules:
        lines.append("")
        lines.append("### 绝对拦截（命中即放弃，输出空集）")
        for i, rule in enumerate(rules.absolute_interception_rules, 1):
            lines.append(f"{i}. {rule.rule}")

    lines.append("")

    # 完整性与边界
    lines.append("# 抽取完整性与边界原则（极其重要！）")
    lines.append("- 精准截取：只抽取与目标条款强相关的核心语句，绝对不要提取包含该条款的整个自然段。")
    lines.append("- 剔除无关信息：必须无情剔除与目标条款无关的表述（支付方式、付款方式、发票不合格时的保留权利、结算周期、付款日、系统名称等）。")
    lines.append("- 表格特例：若目标条款出现在表格中（如付款里程碑表），则抽取包含该信息的完整表格。")

    return "\n".join(lines)


def _format_profile(profile: RecallProfile) -> str:
    """把召回画像格式化成提示词文本。"""
    lines = []

    if profile.positive_keywords:
        lines.append(f"- 别称/同义表述：{', '.join(profile.positive_keywords[:5])}")

    if profile.confusion_words:
        lines.append(f"- 正向关键词：{', '.join(profile.positive_keywords)}")
        lines.append(f"- 易混淆词：{', '.join(profile.confusion_words)}（以下词汇常见于相邻条款，注意根据上下文区分归属）")

    if profile.section_hints:
        lines.append(f"- 可能出现章节：{', '.join(profile.section_hints)}")

    if profile.semantic_queries:
        lines.append("- 语义匹配参考（用于判断语义相似度，不是精确匹配）：")
        for q in profile.semantic_queries:
            lines.append(f"  · {q}")

    if not lines:
        return "（无画像信息）"

    return "\n".join(lines)
