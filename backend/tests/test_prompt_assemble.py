"""prompt_assemble.py 单元测试。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.cc_bom_generator.contracts.bom import (
    BOM, ExtractionRules, ExtractionRule, RecallProfile, BomSource,
)
from src.cc_bom_generator.nodes.prompt_assemble import assemble_prompt


def test_assemble_basic():
    """基本测试：组装提示词。"""
    bom = BOM(
        clause="付款支持文档",
        block_code="FSB0000004",
        source=BomSource.GENERATE,
        semantic_definition=(
            "付款支持文档条款是指合同中约定供应商需提供特定文件"
            "（如发票、验收报告、保函、对账单等）作为付款申请依据的条款。"
        ),
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[
                ExtractionRule(rule="仅提及付款未列出具体文件名→拦截"),
                ExtractionRule(rule="文件属交付物非付款支持→拦截"),
            ],
            core_match_rules=[
                ExtractionRule(rule="出现付款+至少一种具体文件名→提取"),
                ExtractionRule(rule="凭/依据/提供+文件名+指向付款→提取"),
            ],
        ),
        recall_profile=RecallProfile(
            positive_keywords=["付款", "供应商", "增值税", "专用发票", "验收报告"],
            confusion_words=["付款金额", "付款时间"],
            section_hints=["付款条款", "结算与付款", "付款条件"],
            semantic_queries=["供应商需提供哪些文件作为付款申请依据"],
            positive_examples=["增值税专用发票作为付款支持文档"],
        ),
    )

    full_prompt = assemble_prompt(bom)

    print(f"条款: {full_prompt.clause}")
    print(f"组装来源: {full_prompt.assembled_from}")
    print(f"\n{'='*60}")
    print(full_prompt.prompt_text)
    print(f"{'='*60}")

    # ====== 断言 ======

    # 1. 提示词不为空
    assert len(full_prompt.prompt_text) > 100, "提示词太短"

    # 2. 包含条款名
    assert "付款支持文档" in full_prompt.prompt_text

    # 3. 包含编码
    assert "FSB0000004" in full_prompt.prompt_text

    # 4. 包含定义
    assert "供应商需提供特定文件" in full_prompt.prompt_text

    # 5. 包含匹配规则
    assert "具体文件名" in full_prompt.prompt_text

    # 6. 包含拦截规则
    assert "拦截" in full_prompt.prompt_text

    # 7. 包含关键词
    assert "增值税" in full_prompt.prompt_text

    # 8. 包含易混淆词
    assert "付款金额" in full_prompt.prompt_text

    # 9. 包含章节提示
    assert "付款条款" in full_prompt.prompt_text

    # 10. 包含语义查询
    assert "供应商需提供" in full_prompt.prompt_text

    # 11. 包含输出格式（JSON Schema）
    assert "blockExtractions" in full_prompt.prompt_text

    # 12. 包含边界原则
    assert "精准截取" in full_prompt.prompt_text
    assert "剔除无关信息" in full_prompt.prompt_text

    # 13. BOM 快照可追溯
    assert full_prompt.bom_snapshot.clause == "付款支持文档"

    print("\n✓ test_assemble_basic passed — 13 项断言全部通过")


if __name__ == "__main__":
    test_assemble_basic()
    print("\n全部测试通过")
