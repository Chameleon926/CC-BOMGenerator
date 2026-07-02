"""回修链种子测试 —— _build_retry_bom_text 含全精细字段 + 上轮问题（generate 升级 T4）。

验证 M2 修复：回修时 gen_stage1 的 current_bom 种子能看到上轮精细规则
（logic/poison_words/reasoning_chain/scene_judgments）+ red_flags，而非退化为粗规则。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from src.cc_bom_generator.nodes.orchestrator import GenerationOrchestrator
from src.cc_bom_generator.schemas.bom import (
    BOM,
    ExtractionRule,
    ExtractionRules,
    SceneJudgment,
)
from src.cc_bom_generator.schemas.cleaned_test_set import CleanedTestSet
from src.cc_bom_generator.schemas.diagnosis import Verification
from src.cc_bom_generator.schemas.generation_state import GenerationState


def _build_state_with_fine_bom() -> GenerationState:
    """构造一个含全精细字段的 BOM + verification.red_flags 的 state。"""
    bom = BOM(
        clause="保底承诺",
        block_code="BD0000001",
        semantic_definition="保底承诺指商家作出收益/销量兜底保证的条款，命中即放弃。",
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[
                ExtractionRule(
                    rule="出现「保底」承诺词→一票否决",
                    scene="保底承诺",
                    logic="保底类承诺触发合规红线，命中即放弃",
                ),
                ExtractionRule(
                    rule="出现「兜底收益」→拦截",
                    scene="收益兜底",
                    logic="收益兜底属禁止承诺",
                ),
            ],
            core_match_rules=[
                ExtractionRule(
                    rule="出现「分成比例」+「结算周期」→提取",
                    scene="正常分成",
                    logic="正常分成条款需明确比例与周期",
                ),
            ],
            poison_words=["保底", "兜底收益", "无理由退款"],
        ),
        reasoning_chain=[
            "step1: 扫描承诺类词（保底/兜底）",
            "step2: 区分正常分成 vs 收益兜底",
            "step3: 命中保底即放弃",
        ],
        scene_judgments=[
            SceneJudgment(
                scene="保底承诺",
                negative_case="商家承诺月收益不低于 1 万",
                positive_case="按实际销售额分成",
                analysis="区分兜底保证 vs 正常比例分成",
            ),
        ],
    )

    verification = Verification(
        summary="发现 1 个红旗",
        red_flags=["拦截规则可能误伤正常分成条款，需收窄匹配范围"],
    )

    cleaned = CleanedTestSet(
        clause="保底承诺",
        block_code="BD0000001",
        positive_values=["按实际销售额分成", "月结 30 天"],
    )

    return GenerationState(
        cleaned=cleaned,
        bom=bom,
        verification=verification,
        rule_check_passed=False,
        rule_check_details={
            "killed_examples": [
                {"example": "按实际销售额分成", "killed_by": "分成"}
            ]
        },
    )


def test_retry_seed_contains_logic():
    """种子文本含「逻辑：」前缀（拦截 + 匹配规则的 logic）。"""
    state = _build_state_with_fine_bom()
    orch = GenerationOrchestrator(skills=[], max_retries=0)
    text = orch._build_retry_bom_text(state)

    assert "逻辑：" in text, f"种子应含 logic，实际:\n{text}"
    assert "保底类承诺触发合规红线" in text
    assert "正常分成条款需明确比例与周期" in text


def test_retry_seed_contains_poison_words():
    """种子文本含「毒药词」段 + 全部毒药词。"""
    state = _build_state_with_fine_bom()
    orch = GenerationOrchestrator(skills=[], max_retries=0)
    text = orch._build_retry_bom_text(state)

    assert "毒药词" in text
    assert "保底" in text
    assert "兜底收益" in text
    assert "无理由退款" in text


def test_retry_seed_contains_reasoning_chain():
    """种子文本含「思维链」段 + 排雷步骤。"""
    state = _build_state_with_fine_bom()
    orch = GenerationOrchestrator(skills=[], max_retries=0)
    text = orch._build_retry_bom_text(state)

    assert "思维链" in text
    assert "step1: 扫描承诺类词" in text
    assert "step3: 命中保底即放弃" in text


def test_retry_seed_contains_scene_judgments():
    """种子文本含「判例分析」段 + 正反例 + 分析。"""
    state = _build_state_with_fine_bom()
    orch = GenerationOrchestrator(skills=[], max_retries=0)
    text = orch._build_retry_bom_text(state)

    assert "判例分析" in text
    assert "商家承诺月收益不低于 1 万" in text  # negative_case
    assert "按实际销售额分成" in text  # positive_case
    assert "区分兜底保证 vs 正常比例分成" in text  # analysis


def test_retry_seed_contains_previous_issues_section():
    """种子文本含「上轮自检/校验问题」段 + red_flags 内容。"""
    state = _build_state_with_fine_bom()
    orch = GenerationOrchestrator(skills=[], max_retries=0)
    text = orch._build_retry_bom_text(state)

    assert "上轮自检/校验问题" in text
    assert "拦截规则可能误伤正常分成条款" in text  # red_flags 内容
    assert "拦截规则误杀1个正例" in text  # 误杀反馈


def test_retry_seed_scene_prefix_in_rules():
    """拦截/匹配规则带 [scene] 前缀。"""
    state = _build_state_with_fine_bom()
    orch = GenerationOrchestrator(skills=[], max_retries=0)
    text = orch._build_retry_bom_text(state)

    assert "[保底承诺]" in text
    assert "[收益兜底]" in text
    assert "[正常分成]" in text


def test_retry_seed_empty_lists_skipped():
    """空精细字段优雅跳过，不渲染空段。"""
    bom = BOM(
        clause="空条款",
        block_code="X01",
        semantic_definition="无精细字段",
        extraction_rules=ExtractionRules(),  # 全空
    )
    cleaned = CleanedTestSet(
        clause="空条款", block_code="X01", positive_values=["a"]
    )
    state = GenerationState(cleaned=cleaned, bom=bom)
    orch = GenerationOrchestrator(skills=[], max_retries=0)
    text = orch._build_retry_bom_text(state)

    assert "当前定义：无精细字段" in text
    assert "毒药词" not in text
    assert "思维链" not in text
    assert "判例分析" not in text
    assert "拦截" not in text
    assert "匹配" not in text
    # 无 verification + rule_check_passed 默认 True -> 不应出现「上轮问题」段
    assert "上轮自检/校验问题" not in text


def test_retry_seed_bom_none():
    """state.bom 为 None 时返回占位符。"""
    cleaned = CleanedTestSet(
        clause="无", block_code="X02", positive_values=["a"]
    )
    state = GenerationState(cleaned=cleaned, bom=None)
    orch = GenerationOrchestrator(skills=[], max_retries=0)
    text = orch._build_retry_bom_text(state)
    assert text == "（无）"


if __name__ == "__main__":
    test_retry_seed_contains_logic()
    test_retry_seed_contains_poison_words()
    test_retry_seed_contains_reasoning_chain()
    test_retry_seed_contains_scene_judgments()
    test_retry_seed_contains_previous_issues_section()
    test_retry_seed_scene_prefix_in_rules()
    test_retry_seed_empty_lists_skipped()
    test_retry_seed_bom_none()
    print("\n✅ 全部回修链种子测试通过")
