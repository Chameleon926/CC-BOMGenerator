"""BOM 精细化契约升级单元测试（generate 升级 T1）。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from pydantic import ValidationError

from src.cc_bom_generator.schemas.bom import (
    BOM,
    ExtractionRule,
    ExtractionRules,
    RecallProfile,
    SceneJudgment,
)


# ---- ExtractionRule：scene + logic ----

def test_extraction_rule_scene_logic_default():
    """scene/logic 默认空串，且字段顺序不破坏旧用法。"""
    r = ExtractionRule(rule="命中「保底」即拦截")
    assert r.scene == ""
    assert r.logic == ""
    assert r.fixes == ""


def test_extraction_rule_scene_logic_set():
    """可设置场景名与拦截逻辑。"""
    r = ExtractionRule(
        rule="命中「保底」即拦截",
        scene="保底承诺",
        logic="出现保底类承诺词即一票否决",
        fixes="依据：合规红线",
    )
    assert r.scene == "保底承诺"
    assert r.logic == "出现保底类承诺词即一票否决"


def test_extraction_rule_logic_max_length():
    """logic 限长 120，超长应抛 ValidationError。"""
    too_long = "x" * 121
    with pytest.raises(ValidationError):
        ExtractionRule(rule="r", logic=too_long)


# ---- ExtractionRules：poison_words + model_validator ----

def test_extraction_rules_poison_words_default():
    """poison_words 默认空。"""
    er = ExtractionRules()
    assert er.poison_words == []


def test_extraction_rules_poison_words_set():
    er = ExtractionRules(poison_words=["保底", "无理由退款"])
    assert er.poison_words == ["保底", "无理由退款"]


def test_extraction_rules_poison_words_dedup_trim_dropempty():
    """model_validator：去重保序 + trim + 去空。

    输入 ["保底","保底"," 不少于 ",""] -> ["保底","不少于"]
    """
    er = ExtractionRules(poison_words=["保底", "保底", " 不少于 ", ""])
    assert er.poison_words == ["保底", "不少于"]


def test_extraction_rules_poison_words_all_empty():
    """全空输入 -> 空列表。"""
    er = ExtractionRules(poison_words=["", "  ", ""])
    assert er.poison_words == []


# ---- SceneJudgment（新增类） ----

def test_scene_judgment_required_scene():
    """scene 必填。"""
    with pytest.raises(ValidationError):
        SceneJudgment()  # type: ignore[call-arg]


def test_scene_judgment_fields():
    """四字段：scene / negative_case / positive_case / analysis。"""
    sj = SceneJudgment(
        scene="退款推演陷阱",
        negative_case="商家承诺 7 天无理由",
        positive_case="仅质量问题可退",
        analysis="区分无理由 vs 质量问题",
    )
    assert sj.scene == "退款推演陷阱"
    assert sj.negative_case == "商家承诺 7 天无理由"
    assert sj.positive_case == "仅质量问题可退"
    assert sj.analysis == "区分无理由 vs 质量问题"


def test_scene_judgment_optional_defaults():
    """除 scene 外其他字段默认空。"""
    sj = SceneJudgment(scene="保底承诺")
    assert sj.negative_case == ""
    assert sj.positive_case == ""
    assert sj.analysis == ""


# ---- RecallProfile：negative_examples ----

def test_recall_profile_negative_examples_default():
    rp = RecallProfile()
    assert rp.negative_examples == []


def test_recall_profile_negative_examples_set():
    rp = RecallProfile(
        positive_examples=["甲"], negative_examples=["乙", "丙"]
    )
    assert rp.negative_examples == ["乙", "丙"]


# ---- BOM：reasoning_chain + scene_judgments ----

def test_bom_reasoning_chain_default():
    bom = BOM()
    assert bom.reasoning_chain == []
    assert bom.scene_judgments == []


def test_bom_reasoning_chain_and_scene_judgments_set():
    sj = SceneJudgment(scene="保底承诺", analysis="x")
    bom = BOM(
        reasoning_chain=["step1: 识别承诺词", "step2: 排雷"],
        scene_judgments=[sj],
    )
    assert bom.reasoning_chain == ["step1: 识别承诺词", "step2: 排雷"]
    assert len(bom.scene_judgments) == 1
    assert bom.scene_judgments[0].scene == "保底承诺"


def test_bom_field_ordering_smoke():
    """BOM 仍能正常构造，旧字段不丢。"""
    bom = BOM(clause="保底条款", block_code="B01", version=3)
    assert bom.clause == "保底条款"
    assert bom.block_code == "B01"
    assert bom.version == 3
    assert bom.created_at is not None
