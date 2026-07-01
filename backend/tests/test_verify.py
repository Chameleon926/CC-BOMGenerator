"""verify.py 单元测试。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cc_bom_generator.schemas.bom import (
    BOM, ExtractionRules, ExtractionRule, RecallProfile, BomSource,
)
from src.cc_bom_generator.nodes.skills._verify_logic import verify_bom, has_blocking_issues


def test_verify_basic():
    """基本测试：自检通过的 BOM。"""
    bom = BOM(
        clause="付款支持文档",
        block_code="FSB0000004",
        source=BomSource.GENERATE,
        semantic_definition=(
            "付款支持文档条款是指合同中约定供应商需提供特定文件"
            "（如发票、验收报告、保函、对账单等）作为付款申请、结算"
            "或里程碑付款依据的条款。注意：仅约定付款金额/时间但不提及"
            "具体支持文件的条款不属于本条款。"
        ),
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[
                ExtractionRule(
                    rule="仅提及'付款'未列出具体文件名（如发票/验收报告/保函等）→ 拦截",
                    fixes="针对纯付款条件无文件支撑的误抽",
                ),
            ],
            core_match_rules=[
                ExtractionRule(
                    rule="出现'付款'相关词 + 至少一种具体文件名（发票/验收报告/保函/对账单等），且上下文指向付款依据 → 提取",
                    fixes="覆盖所有含具体文件的付款支持条款",
                ),
            ],
        ),
        recall_profile=RecallProfile(
            positive_keywords=["付款", "供应商", "增值税", "专用发票", "验收报告"],
            confusion_words=["付款金额", "付款时间"],
            section_hints=["付款条款", "结算与付款"],
            semantic_queries=["供应商需提供哪些文件作为付款申请依据"],
            positive_examples=[
                "供应商应提供增值税专用发票作为付款支持文档",
                "验收报告和发票扫描件作为付款依据",
            ],
        ),
    )

    positives = [
        "供应商应提供增值税专用发票作为付款支持文档",
        "验收报告和发票扫描件作为付款依据",
        "付款里程碑：验收后付款，凭发票和验收报告",
        "预付款保函及履约保函作为申付材料",
        "对账单和结算明细作为结算凭证",
    ]

    print("调用大模型做规则自检...\n")
    verification = verify_bom(bom, positives)

    # 打印结果
    print(f"覆盖估计: {verification.coverage_estimate}")
    print(f"结论: {verification.summary}")
    print(f"\n逐条检查({len(verification.checks)}):")
    for check in verification.checks:
        verdict = check.get("verdict", "?")
        item = check.get("item", "?")
        reason = check.get("reason", "")[:60]
        emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(verdict, "❓")
        print(f"  {emoji} [{verdict}] {item}: {reason}")

    if verification.red_flags:
        print(f"\n🚩 红旗({len(verification.red_flags)}):")
        for flag in verification.red_flags:
            print(f"  - {flag}")
    else:
        print("\n✓ 无红旗")

    # ====== 断言 ======
    assert verification.coverage_estimate, "覆盖估计不能为空"
    assert verification.summary, "结论不能为空"
    assert len(verification.checks) > 0, "检查项不能为空"

    # 每个正例都应该有对应的检查
    assert len(verification.checks) >= len(positives) - 1, \
        "检查项数量应接近正例数"

    print("\n✓ test_verify_basic passed")


def test_has_blocking_issues():
    """测试 has_blocking_issues 函数。"""
    from src.cc_bom_generator.schemas.diagnosis import Verification

    # 无红旗、无 fail
    v1 = Verification(checks=[{"verdict": "pass"}], red_flags=[])
    assert has_blocking_issues(v1) == False, "无红旗无fail应返回False"

    # 有红旗
    v2 = Verification(checks=[{"verdict": "pass"}], red_flags=["拦截规则过严"])
    assert has_blocking_issues(v2) == True, "有红旗应返回True"

    # 有 fail
    v3 = Verification(checks=[{"verdict": "fail", "reason": "正例被误杀"}], red_flags=[])
    assert has_blocking_issues(v3) == True, "有fail应返回True"

    print("✓ test_has_blocking_issues passed")


if __name__ == "__main__":
    test_verify_basic()
    test_has_blocking_issues()
    print("\n全部测试通过")
