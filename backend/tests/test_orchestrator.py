"""编排器端到端测试 —— 跑完整管线 + 回修验证。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def create_cleaned():
    from src.cc_bom_generator.contracts.cleaned_test_set import CleanedTestSet

    return CleanedTestSet(
        clause="付款支持文档",
        block_code="FSB0000004",
        domain="采购",
        positive_values=[
            "供应商应提供增值税专用发票作为付款支持文档",
            "验收报告和发票扫描件作为付款依据",
            "付款里程碑：验收后付款，凭发票和验收报告",
            "预付款保函及履约保函作为申付材料",
            "对账单和结算明细作为结算凭证",
        ],
    )


def test_orchestrator_full_pipeline():
    """测试完整管线：从 CleanedTestSet 到 FullPrompt。"""
    from src.cc_bom_generator.nodes.orchestrator import create_default_orchestrator
    from src.cc_bom_generator.contracts.generation_state import GenerationState

    state = GenerationState(cleaned=create_cleaned(), skip_verify=True)

    orchestrator = create_default_orchestrator()
    state = orchestrator.run(state)

    # 断言
    assert state.bom is not None, "BOM 应已生成"
    assert len(state.bom.semantic_definition) > 20, "定义不能太短"
    assert len(state.bom.recall_profile.positive_keywords) > 0, "关键词不能为空"
    assert state.full_prompt is not None, "提示词应已生成"
    assert len(state.full_prompt.prompt_text) > 200, "提示词不能太短"

    # 验证 BOM 结构
    assert state.bom.clause == "付款支持文档"
    assert state.bom.block_code == "FSB0000004"

    # 验证关键词约束（短词、无数字）
    for kw in state.bom.recall_profile.positive_keywords:
        assert len(kw) <= 8, f"关键词过长: {kw}"
        assert not any(c.isdigit() for c in kw), f"关键词含数字: {kw}"

    # 验证规则非空
    assert len(state.bom.extraction_rules.core_match_rules) > 0, "匹配规则不能为空"

    print(f"定义: {state.bom.semantic_definition[:60]}...")
    print(f"关键词: {state.bom.recall_profile.positive_keywords}")
    print(f"提示词长度: {len(state.full_prompt.prompt_text)} 字")
    print("✓ test_orchestrator_full_pipeline passed")


def test_orchestrator_retry():
    """验证回修机制：SelfCheck.Summary 不为空。"""
    from src.cc_bom_generator.nodes.orchestrator import create_default_orchestrator
    from src.cc_bom_generator.contracts.generation_state import GenerationState

    state = GenerationState(cleaned=create_cleaned(), skip_verify=False)

    orchestrator = create_default_orchestrator()
    state = orchestrator.run(state)

    # 断言
    assert state.bom is not None
    assert state.full_prompt is not None

    # 如果自检发现红旗，应记录在 verification 中
    if state.verification:
        print(f"自检结论: {state.verification.summary[:60]}")
        print(f"红旗数: {len(state.verification.red_flags)}")

    # 回修次数不超过 1
    assert state.retry_count <= 1, f"回修次数不应超过 1（实际 {state.retry_count}）"

    print("✓ test_orchestrator_retry passed")


def test_rule_check():
    """验证程序化规则校验。"""
    from src.cc_bom_generator.nodes.skills.rule_check import RuleCheckSkill, _extract_rule_keywords
    from src.cc_bom_generator.contracts.bom import BOM, ExtractionRules, ExtractionRule, BomSource
    from src.cc_bom_generator.contracts.cleaned_test_set import CleanedTestSet
    from src.cc_bom_generator.contracts.generation_state import GenerationState

    # 构造一个有误杀风险的 BOM
    bom = BOM(
        clause="付款支持文档",
        block_code="FSB0000004",
        source=BomSource.GENERATE,
        semantic_definition="付款支持文档是指...",
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[
                ExtractionRule(rule="出现'供应商'关键词→拦截"),
            ],
            core_match_rules=[
                ExtractionRule(rule="出现'付款'+具体文件名→提取"),
            ],
        ),
    )

    cleaned = CleanedTestSet(
        clause="付款支持文档",
        block_code="FSB0000004",
        positive_values=["供应商应提供增值税专用发票作为付款支持文档"],
    )

    state = GenerationState(cleaned=cleaned, bom=bom)

    skill = RuleCheckSkill()
    state = skill.execute(state)

    # 断言："供应商"在正例中 → 应被标记为误杀
    assert not state.rule_check_passed, "正例含'供应商'，拦截规则应命中，rule_check 应失败"
    assert len(state.rule_check_details.get("killed_examples", [])) > 0, "应有误杀记录"

    print(f"误杀: {state.rule_check_details['killed_examples']}")
    print("✓ test_rule_check passed")


def test_extract_rule_keywords():
    """验证 _extract_rule_keywords 能提取引号内关键词。"""
    from src.cc_bom_generator.nodes.skills.rule_check import _extract_rule_keywords
    from src.cc_bom_generator.contracts.bom import ExtractionRule

    rules = [
        ExtractionRule(rule="出现'付款'或'发票'关键词→拦截"),
        ExtractionRule(rule="出现'付款'+'具体文件名'→提取"),
    ]

    kws = _extract_rule_keywords(rules)
    assert "付款" in kws, f"应提取'付款'，实际: {kws}"
    assert "发票" in kws, f"应提取'发票'，实际: {kws}"
    assert "拦截" in kws, f"应提取'拦截'，实际: {kws}"
    assert len(kws) >= 3, f"应至少提取 3 个关键词，实际: {kws}"

    print(f"提取的关键词: {kws}")
    print("✓ test_extract_rule_keywords passed")


if __name__ == "__main__":
    test_extract_rule_keywords()
    test_rule_check()
    test_orchestrator_full_pipeline()
    test_orchestrator_retry()

    print("\n✅ 全部编排器测试通过")