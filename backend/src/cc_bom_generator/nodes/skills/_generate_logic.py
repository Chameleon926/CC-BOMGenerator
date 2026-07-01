"""
B 模块第 2 步：语义定义 + 抽取规则生成（用大模型）

输入：CleanedTestSet + 第1步的关键词（辅助参考）
输出：BOM 的 semantic_definition + extraction_rules 部分

使用 prompts/gen_stage1.txt 提示词模板，温度 0.2（收敛，规则要稳定）。
"""

from __future__ import annotations

import json
from typing import List

from ...contracts.bom import BOM, ExtractionRule, ExtractionRules, BomSource
from ...contracts.cleaned_test_set import CleanedTestSet
from ...llm.client import call_json, render_prompt


def generate_definition_and_rules(
    cleaned: CleanedTestSet,
    keywords: List[str] | None = None,
    current_bom: str = "（无）",
) -> BOM:
    """
    调大模型生成语义定义 + 抽取规则。

    Args:
        cleaned: A 模块交付的清洗后测试集
        keywords: 第1步 keyword_extract 抽出的关键词（辅助参考，可选）
        current_bom: 已有定义/规则种子（生成场景一般为"（无）"）

    Returns:
        BOM 对象（只填了 definition + extraction_rules，画像待 profile_build 补全）
    """
    # ---- 组装候选正例文本 ----
    cands_text = _format_candidates(cleaned.positive_values)

    # 如果有关键词，附在候选正例后面作为辅助参考
    if keywords:
        cands_text += f"\n\n（统计抽取的高频特征词参考：{'、'.join(keywords)}）"

    # ---- 渲染提示词 ----
    user_prompt = render_prompt(
        "gen_stage1",
        clause=cleaned.clause,
        current_bom=current_bom,
        cands=cands_text,
    )

    # ---- 调大模型 ----
    system_prompt = render_prompt("system")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = call_json(messages, temperature=0.2)

    # ---- 解析结果，构建 BOM ----
    bom = BOM(
        clause=cleaned.clause,
        block_code=cleaned.block_code,
        source=BomSource.GENERATE,
        semantic_definition=result.get("semantic_definition", ""),
    )

    # 解析抽取规则
    rules_data = result.get("extraction_rules", {})
    bom.extraction_rules = _parse_extraction_rules(rules_data)

    # 保存 coverage_check（不进 BOM 契约，但可用于日志/调试）
    bom._coverage_check = result.get("coverage_check", "")

    return bom


def _format_candidates(values: List[str]) -> str:
    """把期望值列表格式化为提示词里的候选正例文本。"""
    if not values:
        return "（未提供候选）"
    lines = []
    for i, val in enumerate(values, 1):
        lines.append(f"  ({i}) {val}")
    return "\n".join(lines)


def _parse_extraction_rules(rules_data: dict) -> ExtractionRules:
    """把大模型返回的 JSON 解析成 ExtractionRules 契约。"""
    interception_list = rules_data.get("absolute_interception_rules", [])
    match_list = rules_data.get("core_match_rules", [])

    return ExtractionRules(
        absolute_interception_rules=[
            ExtractionRule(
                rule=item.get("rule", "") if isinstance(item, dict) else str(item),
                fixes=item.get("fixes", "") if isinstance(item, dict) else "",
            )
            for item in interception_list
        ],
        core_match_rules=[
            ExtractionRule(
                rule=item.get("rule", "") if isinstance(item, dict) else str(item),
                fixes=item.get("fixes", "") if isinstance(item, dict) else "",
            )
            for item in match_list
        ],
    )
