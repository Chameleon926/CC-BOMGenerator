"""SelfCheck 升级单元测试（generate 升级 T4c）。

新增三段：
1. verify_bom 把 reasoning_chain 传进 verify 提示词
2. LLM 返回 red_flags 含「资金方向反」→ Verification.red_flags 含
3. verify.txt 文本覆盖三类业务致命错（资金/方向/主体/毒药词）
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import patch

from src.cc_bom_generator.nodes.skills import _verify_logic
from src.cc_bom_generator.nodes.skills._verify_logic import verify_bom
from src.cc_bom_generator.schemas.bom import (
    BOM,
    BomSource,
    ExtractionRules,
    ExtractionRule,
    RecallProfile,
)


def _make_bom(reasoning_chain=None, poison_words=None):
    return BOM(
        clause="押金条款",
        block_code="FSB0001",
        source=BomSource.GENERATE,
        semantic_definition="押金条款是指...",
        extraction_rules=ExtractionRules(
            poison_words=poison_words or [],
            core_match_rules=[
                ExtractionRule(rule="出现'押金'→提取"),
            ],
        ),
        recall_profile=RecallProfile(
            positive_keywords=["押金"],
            positive_examples=["供应商缴纳履约押金 10 万元"],
        ),
        reasoning_chain=reasoning_chain or [],
    )


# ---- 1. reasoning_chain 透传 ----

def test_verify_passes_reasoning_chain():
    """verify_bom 应把 bom.reasoning_chain 渲染进 verify 提示词。"""
    bom = _make_bom(reasoning_chain=[
        "第1步：先确认谁交钱、谁收钱，方向不能反",
        "第2步：押金是供应商交，不是华为交",
    ])

    captured = {}

    def fake_call_json(messages, temperature=0.0):
        # 抓 user_prompt 快照
        captured["user_prompt"] = messages[-1]["content"]
        return {
            "checks": [{"item": "正例1", "verdict": "pass", "reason": "ok"}],
            "red_flags": [],
            "coverage_estimate": "1/1 = 100%",
            "summary": "可直接用",
        }

    with patch.object(_verify_logic, "call_json", side_effect=fake_call_json):
        verification = verify_bom(bom, ["供应商缴纳履约押金 10 万元"])

    user_prompt = captured["user_prompt"]
    # 占位已被替换（不再是 {{reasoning_chain}}），且含两条链步骤
    assert "{{reasoning_chain}}" not in user_prompt, (
        "reasoning_chain 占位必须被替换掉"
    )
    assert "谁交钱、谁收钱" in user_prompt, "reasoning_chain 第1步应进提示词"
    assert "押金是供应商交" in user_prompt, "reasoning_chain 第2步应进提示词"

    # 结构未变
    assert verification.checks[0]["verdict"] == "pass"
    assert verification.coverage_estimate == "1/1 = 100%"


def test_verify_empty_reasoning_chain_uses_placeholder():
    """reasoning_chain 为空 → 占位替换为占位句，不残留 {{reasoning_chain}}。"""
    bom = _make_bom(reasoning_chain=[])

    captured = {}

    def fake_call_json(messages, temperature=0.0):
        captured["user_prompt"] = messages[-1]["content"]
        return {"checks": [], "red_flags": [], "coverage_estimate": "", "summary": ""}

    with patch.object(_verify_logic, "call_json", side_effect=fake_call_json):
        verify_bom(bom, ["供应商缴纳履约押金 10 万元"])

    assert "{{reasoning_chain}}" not in captured["user_prompt"], (
        "空链也不应残留未替换占位"
    )


# ---- 2. red_flag 透传（资金方向反）----

def test_red_flag_on_direction_reversal():
    """LLM 判定资金方向反 → Verification.red_flags 应含该红旗。"""
    bom = _make_bom(reasoning_chain=["确认资金方向"])

    fake = {
        "checks": [{"item": "押金正例", "verdict": "fail", "reason": "方向反"}],
        "red_flags": ["资金方向反：供应商交钱被当成华为收押金"],
        "coverage_estimate": "0/1 = 0%",
        "summary": "需调整：方向反",
    }

    with patch.object(_verify_logic, "call_json", return_value=fake):
        verification = verify_bom(bom, ["供应商缴纳履约押金 10 万元"])

    assert verification.red_flags, "red_flags 不能为空"
    assert any("资金方向反" in f for f in verification.red_flags), (
        f"red_flags 应含'资金方向反': {verification.red_flags}"
    )


# ---- 3. verify.txt 三类业务致命错覆盖 ----

def test_verify_txt_has_three_checks():
    """verify.txt 文本应覆盖三类业务致命错：资金/方向/主体/毒药词。"""
    prompts_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "prompts")
    )
    verify_path = os.path.join(prompts_dir, "verify.txt")
    with open(verify_path, encoding="utf-8") as f:
        text = f.read()

    # {{reasoning_chain}} 占位 + 强制前置
    assert "{{reasoning_chain}}" in text, "verify.txt 必须含 {{reasoning_chain}} 占位"
    assert "reasoning_chain" in text, "应明确点名 reasoning_chain（强制前置段落）"

    # 三类业务致命错关键词
    assert "资金" in text, "必须查资金（致命错①）"
    assert "方向" in text, "必须查方向（致命错①）"
    assert "主体" in text, "必须查主体（致命错②）"
    assert "毒药词" in text, "必须查毒药词误伤正例（致命错③）"

    # 输出结构保留
    assert "checks" in text
    assert "red_flags" in text
    assert "coverage_estimate" in text
    assert "summary" in text


if __name__ == "__main__":
    test_verify_passes_reasoning_chain()
    test_verify_empty_reasoning_chain_uses_placeholder()
    test_red_flag_on_direction_reversal()
    test_verify_txt_has_three_checks()
    print("\n全部测试通过")
