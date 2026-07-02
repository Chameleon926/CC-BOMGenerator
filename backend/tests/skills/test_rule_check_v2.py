"""RuleCheck 升级单元测试（generate 升级 T4b）。

新增两段校验：
1. 毒药词命中正例 = 硬错误（毒药词选错了，不应命中本条款正例）
2. scene 分桶覆盖率（拦截规则按 .scene 分桶统计，供人审视场景盲区）
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from src.cc_bom_generator.nodes.skills.rule_check import RuleCheckSkill
from src.cc_bom_generator.schemas.bom import (
    BOM,
    BomSource,
    ExtractionRule,
    ExtractionRules,
)
from src.cc_bom_generator.schemas.cleaned_test_set import CleanedTestSet
from src.cc_bom_generator.schemas.generation_state import GenerationState


def _make_state(bom, positives):
    cleaned = CleanedTestSet(
        clause="测试条款",
        block_code="B0001",
        positive_values=list(positives),
    )
    return GenerationState(cleaned=cleaned, bom=bom)


# ---- 1. 毒药词命中正例（硬错误）----

def test_poison_word_hits_positive_fails():
    """poison_words 命中正例 = 硬错误，rule_check 应失败。"""
    bom = BOM(
        clause="最低注册资本",
        block_code="B0001",
        source=BomSource.GENERATE,
        semantic_definition="最低注册资本是指...",
        extraction_rules=ExtractionRules(
            poison_words=["不少于"],
            core_match_rules=[
                ExtractionRule(rule="出现'注册资本'→提取"),
            ],
        ),
    )
    state = _make_state(bom, positives=["公司注册资本不少于 100 万元"])

    skill = RuleCheckSkill()
    state = skill.execute(state)

    assert not state.rule_check_passed, "毒药词'不少于'命中正例，应判失败"
    poison_hits = state.rule_check_details.get("poison_hits", [])
    assert len(poison_hits) > 0, "poison_hits 应非空"
    assert poison_hits[0]["poison_word"] == "不少于"
    assert "不少于" in poison_hits[0]["example"]


def test_no_poison_hit_passes():
    """poison_words 不命中正例 → 不影响 pass。"""
    bom = BOM(
        clause="最低注册资本",
        block_code="B0001",
        source=BomSource.GENERATE,
        semantic_definition="最低注册资本是指...",
        extraction_rules=ExtractionRules(
            poison_words=["无理由退款"],  # 与正例无关
            core_match_rules=[
                ExtractionRule(rule="出现'注册资本'→提取"),
            ],
        ),
    )
    state = _make_state(bom, positives=["公司注册资本为 100 万元"])

    skill = RuleCheckSkill()
    state = skill.execute(state)

    assert state.rule_check_passed, "毒药词未命中正例、拦截规则未误杀，应 pass"
    assert state.rule_check_details.get("poison_hits", []) == []


def test_poison_words_empty_skips():
    """poison_words=[] → 不做毒药词校验，pass（前提是无误杀）。"""
    bom = BOM(
        clause="最低注册资本",
        block_code="B0001",
        source=BomSource.GENERATE,
        semantic_definition="最低注册资本是指...",
        extraction_rules=ExtractionRules(
            poison_words=[],
            core_match_rules=[
                ExtractionRule(rule="出现'注册资本'→提取"),
            ],
        ),
    )
    state = _make_state(bom, positives=["公司注册资本为 100 万元"])

    skill = RuleCheckSkill()
    state = skill.execute(state)

    assert state.rule_check_passed, "poison_words 为空不应导致失败"
    assert state.rule_check_details.get("poison_hits", []) == []


# ---- 2. scene 分桶覆盖率 ----

def test_scene_coverage_bucketed():
    """拦截规则带 scene → scene_coverage 应分桶统计。"""
    bom = BOM(
        clause="付款支持文档",
        block_code="FSB0004",
        source=BomSource.GENERATE,
        semantic_definition="付款支持文档是指...",
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[
                ExtractionRule(rule="出现'非付款用途'→拦截", scene="供应商付款"),
                ExtractionRule(rule="出现'历史退款'→拦截", scene="退款推演"),
                ExtractionRule(rule="出现'押金'→拦截", scene="供应商付款"),
            ],
            core_match_rules=[
                ExtractionRule(rule="出现'付款'→提取"),
            ],
        ),
    )
    state = _make_state(bom, positives=["凭发票付款"])

    skill = RuleCheckSkill()
    state = skill.execute(state)

    scene_coverage = state.rule_check_details.get("scene_coverage", {})
    assert "供应商付款" in scene_coverage, f"应含'供应商付款'桶: {scene_coverage}"
    assert "退款推演" in scene_coverage, f"应含'退款推演'桶: {scene_coverage}"
    assert scene_coverage["供应商付款"] == 2, f"该 scene 有 2 条拦截规则: {scene_coverage}"
    assert scene_coverage["退款推演"] == 1


def test_scene_coverage_aggregates_unspecified_scene():
    """无 scene 的拦截规则归入默认桶（(未指定场景)），仍可人审。"""
    bom = BOM(
        clause="付款支持文档",
        block_code="FSB0004",
        source=BomSource.GENERATE,
        semantic_definition="...",
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[
                ExtractionRule(rule="出现'押金'→拦截"),  # scene 默认空
                ExtractionRule(rule="出现'保证金'→拦截", scene=""),
            ],
            core_match_rules=[
                ExtractionRule(rule="出现'付款'→提取"),
            ],
        ),
    )
    state = _make_state(bom, positives=["凭发票付款"])

    skill = RuleCheckSkill()
    state = skill.execute(state)

    scene_coverage = state.rule_check_details.get("scene_coverage", {})
    # 两条无 scene 规则应聚合到同一桶
    assert any(v == 2 for v in scene_coverage.values()), (
        f"两条空 scene 规则应聚合计数: {scene_coverage}"
    )
