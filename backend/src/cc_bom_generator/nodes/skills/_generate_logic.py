"""
B 模块第 2 步：语义定义 + 精细抽取规则生成（用大模型）

输入：CleanedTestSet + 第1步的关键词（辅助参考）
输出：BOM 的 semantic_definition + extraction_rules（分场景 + 拦截逻辑 + 毒药词）
      + reasoning_chain（排雷思维链） + scene_judgments（判例分析）

使用 prompts/gen_stage1.txt 提示词模板（含业务场景分类框架 + JSON 骨架），
外置 few-shot 骨架 prompts/_fewshot_deposit_cap.txt（异构条款元判断）。
温度 0.2（收敛，规则要稳定），retry=2（JSON 损坏兜底）。
"""

from __future__ import annotations

from typing import List

from ...schemas.bom import BOM, ExtractionRule, ExtractionRules, SceneJudgment, BomSource
from ...schemas.cleaned_test_set import CleanedTestSet
from ...llm.client import call_json, render_prompt, get_temperature
from ...logging_config import get_logger

log = get_logger("nodes.skills._generate_logic")


def generate_definition_and_rules(
    cleaned: CleanedTestSet,
    keywords: List[str] | None = None,
    current_bom: str = "（无）",
) -> BOM:
    """
    调大模型生成语义定义 + 精细抽取规则 + 思维链 + 判例分析。

    Args:
        cleaned: A 模块交付的清洗后测试集
        keywords: 第1步 keyword_extract 抽出的关键词（辅助参考，可选）
        current_bom: 已有定义/规则种子（生成场景一般为"（无）"）

    Returns:
        BOM 对象（填了 definition + extraction_rules + reasoning_chain
        + scene_judgments，画像待 profile_build 补全）
    """
    # ---- 组装候选正例文本 ----
    cands_text = _format_candidates(cleaned.positive_values)

    # 如果有关键词，附在候选正例后面作为辅助参考
    if keywords:
        cands_text += f"\n\n（统计抽取的高频特征词参考：{'、'.join(keywords)}）"

    # ---- 渲染提示词（含外置 few-shot 异构骨架）----
    few_shot = render_prompt("_fewshot_deposit_cap")
    user_prompt = render_prompt(
        "gen_stage1",
        clause=cleaned.clause,
        current_bom=current_bom,
        cands=cands_text,
        few_shot=few_shot,
    )

    # ---- 调大模型（retry=2，防 JSON 损坏）----
    system_prompt = render_prompt("system")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = call_json(messages, temperature=get_temperature("stage1"), max_retries=2)

    # ---- 解析结果，构建 BOM ----
    bom = BOM(
        clause=cleaned.clause,
        block_code=cleaned.block_code,
        source=BomSource.GENERATE,
        semantic_definition=result.get("semantic_definition", ""),
    )

    # 解析抽取规则（含 scene/logic/poison_words）
    rules_data = result.get("extraction_rules", {})
    bom.extraction_rules = _parse_extraction_rules(rules_data)

    # 思维链 / 判例分析
    bom.reasoning_chain = _parse_reasoning_chain(result.get("reasoning_chain", []))
    bom.scene_judgments = _parse_scene_judgments(result.get("scene_judgments", []))

    # coverage_check 不进 BOM 契约（M7：原写 bom._coverage_check 在 Pydantic v2 会报错），
    # 改为日志输出，便于人审但不挂 BOM。
    log.info(f"coverage_check: {result.get('coverage_check', '')}")

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
    """把大模型返回的 JSON 解析成 ExtractionRules 契约（含 scene/logic/poison_words）。"""
    interception_list = rules_data.get("absolute_interception_rules", []) or []
    match_list = rules_data.get("core_match_rules", []) or []

    return ExtractionRules(
        absolute_interception_rules=[_to_extraction_rule(item) for item in interception_list],
        core_match_rules=[_to_extraction_rule(item) for item in match_list],
        poison_words=_sanitize_poison_words(rules_data.get("poison_words", [])),
    )


def _to_extraction_rule(item) -> ExtractionRule:
    """单条规则 dict/str -> ExtractionRule（兜底 str 场景）。"""
    if isinstance(item, dict):
        return ExtractionRule(
            rule=item.get("rule", ""),
            scene=item.get("scene", ""),
            logic=item.get("logic", ""),
            fixes=item.get("fixes", ""),
        )
    return ExtractionRule(rule=str(item))


def _sanitize_poison_words(raw) -> List[str]:
    """解析层兜底 trim + 去空（契约 model_validator 也会做，双保险）。"""
    if not isinstance(raw, list):
        return []
    return [w.strip() for w in raw if isinstance(w, str) and w.strip()]


def _parse_reasoning_chain(raw) -> List[str]:
    """思维链兜底：保证是 str 列表。"""
    if not isinstance(raw, list):
        return []
    return [str(step).strip() for step in raw if step is not None and str(step).strip()]


def _parse_scene_judgments(raw) -> List[SceneJudgment]:
    """判例分析：[{scene, negative_case, positive_case, analysis}] -> SceneJudgment。"""
    if not isinstance(raw, list):
        return []
    judgments = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        scene = item.get("scene")
        if not scene:
            continue  # scene 必填，缺则丢弃
        judgments.append(
            SceneJudgment(
                scene=scene,
                negative_case=item.get("negative_case", ""),
                positive_case=item.get("positive_case", ""),
                analysis=item.get("analysis", ""),
            )
        )
    return judgments
