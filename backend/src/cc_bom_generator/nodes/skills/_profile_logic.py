"""
B 模块第 3 步：召回画像组装

输入：
- CleanedTestSet（A 模块交付）
- B1 的 keywords / confusion_words / positive_examples（统计抽取，不用大模型）
- B2 的 BOM（含 semantic_definition + extraction_rules）

输出：
- 完整的 RecallProfile，填入 BOM.recall_profile

策略：
- positive_keywords：优先用 B1 统计抽的（程序过滤后），不够再用大模型补充
- confusion_words：优先用 B1 统计抽的，不够用大模型从拦截规则派生
- section_hints：有 sectionPath 就统计，没有就调大模型推断
- semantic_queries：调大模型基于定义改写
- positive_examples：直接用 B1 聚类选的

整体走大模型 gen_stage2.txt 做一次"画像生成 + 校准"，
然后把 B1 统计结果和大模型结果做融合（取并集去重 + 程序过滤）。
"""

from __future__ import annotations

import json
import re
from typing import List

from ...schemas.bom import BOM, RecallProfile
from ...schemas.cleaned_test_set import CleanedTestSet
from ...llm.client import call_json, render_prompt


def build_profile(
    cleaned: CleanedTestSet,
    bom: BOM,
    keywords: List[str] | None = None,
    confusion_words: List[str] | None = None,
    positive_examples: List[str] | None = None,
    nkw: int = 10,
    nsec: int = 6,
    nq: int = 3,
) -> BOM:
    """
    组装召回画像，填入 BOM.recall_profile。

    Args:
        cleaned: A 模块交付的测试集
        bom: B2 生成的 BOM（已有定义+规则）
        keywords: B1 统计抽的关键词
        confusion_words: B1 统计抽的混淆词
        positive_examples: B1 聚类选的正例
        nkw: 关键词数量
        nsec: 章节提示数量
        nq: 语义查询数量

    Returns:
        填好 recall_profile 的 BOM（原 BOM 的 definition/rules 不变）
    """
    # ---- 准备大模型输入 ----
    stage1_json = json.dumps({
        "semantic_definition": bom.semantic_definition,
        "extraction_rules": bom.extraction_rules.model_dump(),
    }, ensure_ascii=False, indent=2)

    cands_text = _format_candidates(cleaned.positive_values)

    # 候选正例（B1 选的）
    examples_text = _format_list(positive_examples or cleaned.positive_values[:5])

    # 章节信息（如果有）
    section_text = _format_list(cleaned.section_paths) if cleaned.section_paths else "（无）"

    # ---- 渲染提示词 ----
    user_prompt = render_prompt(
        "gen_stage2",
        stage1_json=stage1_json,
        cands=cands_text,
        nkw=nkw,
        nsec=nsec,
        nq=nq,
        lang="中文为主。",
    )

    system_prompt = render_prompt("system")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # ---- 调大模型 ----
    result = call_json(messages, temperature=0.5)
    llm_profile = result.get("recall_profile", {})

    # ---- 融合：B1 统计结果 + 大模型结果 ----
    final_profile = _merge_profile(
        llm_profile=llm_profile,
        stat_keywords=keywords or [],
        stat_confusion=confusion_words or [],
        stat_examples=positive_examples or [],
        nkw=nkw,
        nsec=nsec,
        nq=nq,
    )

    # ---- 程序化关键词过滤（防过拟合兜底）----
    final_profile.positive_keywords = _sanitize_keywords(final_profile.positive_keywords)

    bom.recall_profile = final_profile
    return bom


# ==================== 内部函数 ====================

def _merge_profile(
    llm_profile: dict,
    stat_keywords: List[str],
    stat_confusion: List[str],
    stat_examples: List[str],
    nkw: int,
    nsec: int,
    nq: int,
) -> RecallProfile:
    """
    融合 B1 统计结果和大模型结果。
    策略：统计结果优先（更稳定），大模型补充（覆盖面广）。
    """
    # 正向关键词：统计优先，不够用大模型补
    merged_kw = list(stat_keywords)
    for kw in llm_profile.get("positive_keywords", []):
        if kw not in merged_kw and len(merged_kw) < nkw:
            merged_kw.append(kw)

    # 易混淆词：统计优先
    merged_conf = list(stat_confusion)
    for cw in llm_profile.get("confusion_words", []):
        if cw not in merged_conf:
            merged_conf.append(cw)

    # 章节提示：直接用大模型的
    section_hints = llm_profile.get("section_hints", [])[:nsec]

    # 语义查询：直接用大模型的
    semantic_queries = llm_profile.get("semantic_queries", [])[:nq]

    # 正例：统计聚类优先，不够用大模型补
    merged_examples = list(stat_examples)
    for ex in llm_profile.get("positive_examples", []):
        if ex not in merged_examples and len(merged_examples) < 5:
            merged_examples.append(ex)

    return RecallProfile(
        positive_keywords=merged_kw[:nkw],
        confusion_words=merged_conf[:6],
        section_hints=section_hints,
        semantic_queries=semantic_queries,
        positive_examples=merged_examples[:5],
    )


def _sanitize_keywords(keywords: List[str]) -> List[str]:
    """
    程序化过滤：去掉含数字/超长/整句的（防过拟合兜底）。
    即使大模型违反了提示词约束，这里也能兜住。
    """
    result = []
    seen = set()
    for kw in keywords:
        kw = kw.strip()
        if not kw or kw in seen:
            continue
        # 含数字 → 过拟合
        if re.search(r"\d", kw):
            continue
        # 含金额/百分比
        if re.search(r"[%％万元亿]", kw):
            continue
        # 超长（中文 >8 字）
        if len(kw) > 8:
            continue
        # 整句标点
        if re.search(r"[，,；;。.!！？?]", kw):
            continue
        seen.add(kw)
        result.append(kw)
    return result


def _format_candidates(values: List[str]) -> str:
    """格式化候选正例文本。"""
    if not values:
        return "（未提供候选）"
    return "\n".join(f"  ({i}) {v}" for i, v in enumerate(values, 1))


def _format_list(items: List[str]) -> str:
    """格式化列表文本。"""
    if not items:
        return "（无）"
    return "\n".join(f"  - {item}" for item in items)
