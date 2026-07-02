"""generate 升级 T2：_generate_logic 精细规则解析单元测试（mock LLM）。

覆盖：
- 精细规则解析（scene/logic/poison_words/reasoning_chain/scene_judgments）
- poison_words 无一票否决语义时为空（不强制造毒药词）
- coverage_check 不再挂 BOM（M7：原 bom._coverage_check 在 Pydantic v2 报错）
- call_json retry=2 + few_shot 注入（render_prompt 调用断言）
"""

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from src.cc_bom_generator.nodes.skills import _generate_logic
from src.cc_bom_generator.schemas.cleaned_test_set import CleanedTestSet


# ---- 公共 fixture ----

def _make_cleaned() -> CleanedTestSet:
    return CleanedTestSet(
        clause="押金条款",
        block_code="FSB00000721",
        domain="采购",
        positive_values=["甲方预付款", "履约保证金"],
    )


# ---- T2-1：精细规则解析 ----

def test_parse_fine_grained_rules():
    """mock LLM 返回含 scene/logic/poison_words/reasoning_chain/scene_judgments 的 JSON，
    断言 BOM 各字段解析对。"""
    fake_result = {
        "semantic_definition": "押金条款是指甲方为保证履约向供应商预付的资金。",
        "extraction_rules": {
            "absolute_interception_rules": [
                {
                    "rule": "命中'供应商主动向甲方付款'即放弃",
                    "scene": "供应商主动付款",
                    "logic": "资金方向反转，与押金本义相悖，命中即放弃。",
                }
            ],
            "core_match_rules": [
                {
                    "rule": "甲方在签约后向供应商支付预付款",
                    "scene": "正向支付",
                    "logic": "资金方向正确，属甲方履约担保，提取。",
                }
            ],
            "poison_words": ["无理由退款", "全额退还"],
        },
        "reasoning_chain": [
            "排雷1：找动作实体",
            "排雷2：判断资金方向",
            "排雷3：决策",
        ],
        "scene_judgments": [
            {
                "scene": "供应商主动付款",
                "negative_case": "某公司供应商向甲方付款",
                "positive_case": "甲方预付给某公司供应商",
                "analysis": "区分付款方向",
            }
        ],
        "coverage_check": "覆盖正例多样性，泛化无过拟合。",
    }

    with patch.object(_generate_logic, "call_json", return_value=fake_result) as mock_call, \
         patch.object(_generate_logic, "render_prompt", return_value="RENDERED") as mock_render:
        bom = _generate_logic.generate_definition_and_rules(_make_cleaned())

    # ---- call_json 被调用，且 retry=2 ----
    mock_call.assert_called_once()
    _, kwargs = mock_call.call_args
    assert kwargs.get("temperature") == 0.2
    assert kwargs.get("max_retries") == 2

    # ---- render_prompt 被调用（含 few-shot 注入）----
    # 至少调了 gen_stage1 / system / _fewshot_deposit_cap
    called_names = [c.args[0] for c in mock_render.call_args_list]
    assert "gen_stage1" in called_names
    assert "_fewshot_deposit_cap" in called_names
    assert "system" in called_names

    # ---- semantic_definition ----
    assert bom.semantic_definition.startswith("押金条款是指")

    # ---- 拦截规则：scene + logic 解析对 ----
    inter = bom.extraction_rules.absolute_interception_rules
    assert len(inter) == 1
    assert inter[0].rule.startswith("命中'供应商主动向甲方付款'")
    assert inter[0].scene == "供应商主动付款"
    assert inter[0].logic.startswith("资金方向反转")

    # ---- 匹配规则：scene + logic 解析对 ----
    match = bom.extraction_rules.core_match_rules
    assert len(match) == 1
    assert match[0].scene == "正向支付"
    assert match[0].logic.startswith("资金方向正确")

    # ---- poison_words ----
    assert bom.extraction_rules.poison_words == ["无理由退款", "全额退还"]

    # ---- reasoning_chain ----
    assert bom.reasoning_chain == [
        "排雷1：找动作实体",
        "排雷2：判断资金方向",
        "排雷3：决策",
    ]

    # ---- scene_judgments ----
    assert len(bom.scene_judgments) == 1
    sj = bom.scene_judgments[0]
    assert sj.scene == "供应商主动付款"
    assert sj.negative_case.startswith("某公司供应商")
    assert sj.positive_case.startswith("甲方预付")
    assert sj.analysis == "区分付款方向"


# ---- T2-2：无一票否决语义时 poison_words 为空 ----

def test_poison_words_empty_when_no_veto_semantics():
    """mock LLM 返回 poison_words=[] -> 断言空（不强制造毒药词）。"""
    fake_result = {
        "semantic_definition": "违约金条款是指违约方应支付的赔偿性款项。",
        "extraction_rules": {
            "absolute_interception_rules": [
                {
                    "rule": "命中'定金/赔偿金'即放弃",
                    "scene": "相邻概念混淆",
                    "logic": "定金/赔偿金非违约金，概念边界拦截。",
                }
            ],
            "core_match_rules": [
                {
                    "rule": "违约触发并按约定比例计算",
                    "scene": "违约触发",
                    "logic": "违约行为+计算方式齐备，提取。",
                }
            ],
            "poison_words": [],
        },
        "reasoning_chain": ["识别违约行为", "匹配责任条款"],
        "scene_judgments": [],
        "coverage_check": "违约金无方向/承诺陷阱，poison_words 留空。",
    }

    with patch.object(_generate_logic, "call_json", return_value=fake_result), \
         patch.object(_generate_logic, "render_prompt", return_value="RENDERED"):
        bom = _generate_logic.generate_definition_and_rules(_make_cleaned())

    assert bom.extraction_rules.poison_words == []
    assert bom.reasoning_chain == ["识别违约行为", "匹配责任条款"]
    assert bom.scene_judgments == []


# ---- T2-3：coverage_check 不再挂 BOM（M7 修复）----

def test_coverage_check_no_pydantic_error():
    """mock 返回含 coverage_check -> 不抛 AttributeError / ValidationError。"""
    fake_result = {
        "semantic_definition": "x",
        "extraction_rules": {
            "absolute_interception_rules": [],
            "core_match_rules": [],
            "poison_words": [],
        },
        "reasoning_chain": [],
        "scene_judgments": [],
        "coverage_check": "已覆盖正例多样性。",
    }

    with patch.object(_generate_logic, "call_json", return_value=fake_result), \
         patch.object(_generate_logic, "render_prompt", return_value="RENDERED"):
        # 不应抛任何异常（原 bom._coverage_check = ... 在 Pydantic v2 会抛 ValueError）
        bom = _generate_logic.generate_definition_and_rules(_make_cleaned())

    # BOM 上不存在 _coverage_check 私有属性（确认改用 log）
    assert not hasattr(bom, "_coverage_check")


# ---- T2-4：兜底健壮性（非 dict 元素 / 缺 scene 丢弃）----

def test_robust_parse_malformed_items():
    """LLM 返回畸形元素（规则为 str、scene_judgments 缺 scene）也能兜底解析。"""
    fake_result = {
        "semantic_definition": "x",
        "extraction_rules": {
            "absolute_interception_rules": ["纯字符串规则也能兜底"],
            "core_match_rules": [
                {"rule": "匹配条件", "logic": "为什么提取"}
            ],
            "poison_words": ["  保底  ", "", "保底", "  "],
        },
        "reasoning_chain": ["步骤1", "", None, "步骤2"],
        "scene_judgments": [
            {"scene": "有场景", "analysis": "ok"},
            {"negative_case": "缺 scene 应被丢弃"},
        ],
        "coverage_check": "ok",
    }

    with patch.object(_generate_logic, "call_json", return_value=fake_result), \
         patch.object(_generate_logic, "render_prompt", return_value="RENDERED"):
        bom = _generate_logic.generate_definition_and_rules(_make_cleaned())

    # 纯字符串规则兜底成 ExtractionRule（scene/logic 空）
    inter = bom.extraction_rules.absolute_interception_rules
    assert len(inter) == 1
    assert inter[0].rule == "纯字符串规则也能兜底"
    assert inter[0].scene == ""

    # 匹配规则缺 scene 仍保留（scene 是可选默认空）
    assert len(bom.extraction_rules.core_match_rules) == 1

    # poison_words：解析层 trim + 去空 + 去重（契约 validator 再兜一次）
    assert bom.extraction_rules.poison_words == ["保底"]

    # reasoning_chain 去 None/空
    assert bom.reasoning_chain == ["步骤1", "步骤2"]

    # scene_judgments：缺 scene 的被丢弃，只留 1 条
    assert len(bom.scene_judgments) == 1
    assert bom.scene_judgments[0].scene == "有场景"
