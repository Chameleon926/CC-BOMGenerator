"""keyword_extract 单元测试。"""

import sys
import os

# 把 backend/ 加到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cc_bom_generator.contracts.cleaned_test_set import CleanedTestSet
from src.cc_bom_generator.nodes.keyword_extract import extract_keywords


def test_basic_extraction():
    """基本测试：能从期望值列表中抽出关键词。"""
    cleaned = CleanedTestSet(
        clause="付款支持文档",
        block_code="FSB0000004",
        positive_values=[
            "供应商应提供增值税专用发票作为付款支持文档",
            "验收报告和发票扫描件作为付款依据",
            "付款里程碑：验收后付款，凭发票和验收报告",
            "供应商应提供增值税专用发票作为付款支持文档",  # 重复
            "预付款保函及履约保函作为申付材料",
            "对账单和结算明细作为结算凭证",
        ],
    )

    keywords, confusion, examples = extract_keywords(cleaned)

    print(f"关键词: {keywords}")
    print(f"混淆词: {confusion}")
    print(f"正例({len(examples)}): {examples}")

    # 基本断言
    assert len(keywords) > 0, "关键词不能为空"
    assert len(keywords) <= 10, "关键词不超过 10 个"
    assert all(len(kw) >= 2 for kw in keywords), "关键词至少 2 字"
    assert all(len(kw) <= 8 for kw in keywords), "关键词不超过 8 字"
    assert all(not any(c.isdigit() for c in kw) for kw in keywords), "关键词不含数字"

    assert len(examples) > 0, "正例不能为空"
    assert len(examples) <= 5, "正例不超过 5 个"


def test_empty_values():
    """空列表不报错。"""
    cleaned = CleanedTestSet(
        clause="空条款",
        block_code="FSB0001",
        positive_values=[],
    )
    keywords, confusion, examples = extract_keywords(cleaned)
    assert keywords == []
    assert confusion == []
    assert examples == []


def test_few_values():
    """值少于 5 个时直接返回全部正例。"""
    cleaned = CleanedTestSet(
        clause="测试",
        block_code="FSB0002",
        positive_values=[
            "发票和验收报告",
            "付款保函",
        ],
    )
    keywords, confusion, examples = extract_keywords(cleaned)
    assert len(examples) == 2, "少于5个时正例应返回全部"


def test_no_digits_in_keywords():
    """关键词不含数字、金额符号。"""
    cleaned = CleanedTestSet(
        clause="合同金额",
        block_code="FSB0003",
        positive_values=[
            "合同总价100万元",
            "金额为347942.39元",
            "含税金额5%的增值税",
        ],
    )
    keywords, _, _ = extract_keywords(cleaned)
    for kw in keywords:
        assert not any(c.isdigit() for c in kw), f"关键词含数字: {kw}"
        assert "%" not in kw, f"关键词含%: {kw}"
        assert "万" not in kw, f"关键词含万元: {kw}"


if __name__ == "__main__":
    test_basic_extraction()
    print("✓ test_basic_extraction passed")

    test_empty_values()
    print("✓ test_empty_values passed")

    test_few_values()
    print("✓ test_few_values passed")

    test_no_digits_in_keywords()
    print("✓ test_no_digits_in_keywords passed")

    print("\n全部测试通过")
