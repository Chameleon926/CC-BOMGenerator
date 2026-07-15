# -*- coding: utf-8 -*-
"""TE-2: 典型正例一致性校验纯函数测试。

注：_extract_rule_keywords 只认直引号 "（rule_check 既有行为），测试规则用直引号。
真实 BOM 规则引号风格不定 → 一致性校验是 best-effort 备份，主靠 LLM prompt 锚定规则。
"""
from src.cc_bom_generator.schemas.bom import BOM, ExtractionRule, ExtractionRules, RecallProfile
from src.cc_bom_generator.nodes.skills._example_annotate_logic import check_consistency


def _bom(inter_rule, match_rule, poison, pos_kw=None):
    return BOM(
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[ExtractionRule(rule=inter_rule)] if inter_rule else [],
            core_match_rules=[ExtractionRule(rule=match_rule)] if match_rule else [],
            poison_words=poison,
        ),
        recall_profile=RecallProfile(positive_keywords=pos_kw or []),
    )


def test_consistency_ok_matched_not_intercepted():
    bom = _bom('含"无关词"的拦截', '含"分成"即命中', ["虚假验收"], pos_kw=["收入"])
    r = check_consistency("收入分成比例归华为所有", bom)
    assert r["matched"] is True
    assert r["intercepted"] is False
    assert r["flags"] == []


def test_consistency_intercepted_flag():
    bom = _bom('含"返利禁止"即拦截', '含"分成"', [])
    r = check_consistency("返利禁止的情形分成", bom)  # 命中拦截"返利禁止"
    assert r["intercepted"] is True
    assert any("拦截" in f for f in r["flags"])


def test_consistency_poisoned_flag():
    bom = _bom('', '含"分成"', ["虚假验收"])
    r = check_consistency("分成但涉及虚假验收", bom)  # 命中毒药词
    assert r["intercepted"] is True
    assert any("毒药词" in f for f in r["flags"])


def test_consistency_unmatched_flag():
    bom = _bom('', '含"分成"', [], pos_kw=["收入"])
    r = check_consistency("某完全无关的表述xyz123", bom)  # 不命中匹配也不命中 recall
    assert r["matched"] is False
    assert any("匹配" in f or "未覆盖" in f for f in r["flags"])


def test_consistency_matched_via_recall_keyword():
    # 匹配规则关键词没命中，但 recall positive_keyword 命中 → 仍算 matched
    bom = _bom('', '含"分成"', [], pos_kw=["返点"])
    r = check_consistency("返点金额约定", bom)
    assert r["matched"] is True
