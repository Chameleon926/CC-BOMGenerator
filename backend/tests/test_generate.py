"""generate.py 单元测试。

测试 LLM 调用是否正常、返回的 BOM 结构是否正确。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cc_bom_generator.schemas.cleaned_test_set import CleanedTestSet
from src.cc_bom_generator.schemas.bom import BomSource
from src.cc_bom_generator.nodes.skills._generate_logic import generate_definition_and_rules


def test_generate_basic():
    """基本测试：调大模型生成定义+规则。"""
    cleaned = CleanedTestSet(
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

    keywords = ["付款", "供应商", "增值税", "专用发票", "验收报告"]

    print("调用大模型生成定义+规则...\n")
    bom = generate_definition_and_rules(cleaned, keywords=keywords)

    # 打印结果
    print(f"条款: {bom.clause}")
    print(f"来源: {bom.source.value}")
    print(f"\n定义:\n{bom.semantic_definition}")
    print(f"\n拦截规则({len(bom.extraction_rules.absolute_interception_rules)}):")
    for r in bom.extraction_rules.absolute_interception_rules:
        print(f"  - {r.rule}")
    print(f"\n匹配规则({len(bom.extraction_rules.core_match_rules)}):")
    for r in bom.extraction_rules.core_match_rules:
        print(f"  - {r.rule}")
    print(f"\n覆盖检查: {getattr(bom, '_coverage_check', '(无)')}")

    # 断言
    assert bom.clause == "付款支持文档"
    assert bom.block_code == "FSB0000004"
    assert bom.source == BomSource.GENERATE
    assert len(bom.semantic_definition) > 20, "定义不能太短"
    assert len(bom.extraction_rules.core_match_rules) > 0, "至少要有1条匹配规则"

    # 泛化检查：定义里不应出现具体金额/公司名
    definition = bom.semantic_definition
    assert "华为" not in definition, "定义不应包含具体公司名"
    assert not any(c.isdigit() for c in definition.replace("（", "").replace("）", "")), \
        "定义里最好不要出现数字（泛化要求）"

    print("\n✓ test_generate_basic passed")


if __name__ == "__main__":
    test_generate_basic()
    print("\n全部测试通过")
