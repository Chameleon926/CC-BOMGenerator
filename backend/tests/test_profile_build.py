"""profile_build.py 单元测试。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cc_bom_generator.contracts.cleaned_test_set import CleanedTestSet
from src.cc_bom_generator.contracts.bom import BOM, ExtractionRules, ExtractionRule, BomSource
from src.cc_bom_generator.nodes.profile_build import build_profile


def test_profile_build_basic():
    """基本测试：组装召回画像。"""
    # 准备输入
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

    # B1 统计结果（模拟）
    keywords = ["付款", "供应商", "增值税", "专用发票", "验收报告", "结算"]
    confusion_words = ["扫描", "预付款", "保函"]
    positive_examples = [
        "供应商应提供增值税专用发票作为付款支持文档",
        "对账单和结算明细作为结算凭证",
    ]

    # B2 生成的 BOM（模拟，已有定义+规则）
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
                ExtractionRule(rule="仅提及'付款'未列出具体文件名→拦截"),
            ],
            core_match_rules=[
                ExtractionRule(rule="出现'付款'+至少一种具体文件名→提取"),
            ],
        ),
    )

    print("调用大模型组装召回画像...\n")
    bom = build_profile(
        cleaned=cleaned,
        bom=bom,
        keywords=keywords,
        confusion_words=confusion_words,
        positive_examples=positive_examples,
    )

    rp = bom.recall_profile

    # 打印结果
    print(f"正向关键词({len(rp.positive_keywords)}): {rp.positive_keywords}")
    print(f"易混淆词({len(rp.confusion_words)}): {rp.confusion_words}")
    print(f"章节提示({len(rp.section_hints)}): {rp.section_hints}")
    print(f"语义查询({len(rp.semantic_queries)}):")
    for q in rp.semantic_queries:
        print(f"  · {q}")
    print(f"正例({len(rp.positive_examples)}):")
    for ex in rp.positive_examples:
        print(f"  · {ex[:40]}...")

    # ====== 断言：准确率保障 ======

    # 1. 关键词不能为空
    assert len(rp.positive_keywords) > 0, "关键词不能为空"

    # 2. 关键词必须是短词（≤8字）
    for kw in rp.positive_keywords:
        assert len(kw) <= 8, f"关键词过长(>{8}字): {kw}"

    # 3. 关键词不含数字（精确匹配用，原文不会有数字词）
    for kw in rp.positive_keywords:
        assert not any(c.isdigit() for c in kw), f"关键词含数字: {kw}"

    # 4. 关键词不含整句标点
    for kw in rp.positive_keywords:
        assert not any(c in kw for c in "，,；;。.!！"), f"关键词含标点: {kw}"

    # 5. 语义查询不能为空（向量召回靠它）
    assert len(rp.semantic_queries) > 0, "语义查询不能为空"

    # 6. 语义查询应该是完整句子（不是单词）
    for q in rp.semantic_queries:
        assert len(q) > 8, f"语义查询太短(不是句子): {q}"

    # 7. 正例不能为空（召回锚点）
    assert len(rp.positive_examples) > 0, "正例不能为空"

    # 8. 拦截规则和匹配规则不丢失
    assert len(bom.extraction_rules.core_match_rules) > 0, "匹配规则不能丢失"

    # 9. 定义不丢失
    assert len(bom.semantic_definition) > 20, "定义不能丢失"

    print("\n✓ test_profile_build passed")


if __name__ == "__main__":
    test_profile_build_basic()
    print("\n全部测试通过")
