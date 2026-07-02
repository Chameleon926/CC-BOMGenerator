"""assemble 升级单元测试（generate 升级 T3）。

验证：
1. BOM 含 poison_words + rule.logic → prompt_text 含「毒药词」段 + logic 内容
2. 含 scene_judgments + reasoning_chain → prompt_text 含判例分析 + 思维链
3. positive_examples + negative_examples 都不进 prompt_text
4. 空规则/毒药词 → 输出「（无）」不崩
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.nodes.skills._prompt_logic import assemble_prompt
from src.cc_bom_generator.schemas.bom import (
    BOM,
    BomSource,
    ExtractionRule,
    ExtractionRules,
    RecallProfile,
    SceneJudgment,
)


def _full_bom():
    """构造一个含全精细字段的 BOM。"""
    return BOM(
        clause="押金条款",
        block_code="FSB0001",
        source=BomSource.GENERATE,
        semantic_definition="押金条款是指合同中约定一方交纳一定金额作为履行担保的条款。",
        extraction_rules=ExtractionRules(
            absolute_interception_rules=[
                ExtractionRule(
                    rule="仅出现'押金'二字无具体金额或场景→拦截",
                    scene="供应商主动付款",
                    logic="字面命中无实质，防误抽",
                ),
            ],
            core_match_rules=[
                ExtractionRule(
                    rule="出现'押金/保证金'+具体金额+交纳动作→提取",
                    scene="标准押金约定",
                    logic="三要素齐备才是真押金条款",
                ),
            ],
            poison_words=["员工差旅押金", "个人保证金"],
        ),
        recall_profile=RecallProfile(
            positive_keywords=["押金", "保证金", "交纳"],
            confusion_words=["付款金额", "结算周期"],
            section_hints=["履约担保", "付款条款"],
            semantic_queries=["谁向谁交纳押金及金额"],
            positive_examples=["供应商缴纳履约押金 10 万元"],
            negative_examples=["员工差旅押金凭票报销"],
        ),
        reasoning_chain=[
            "第1步：先确认谁交钱、谁收钱，方向不能反",
            "第2步：排除员工差旅等自然人行为",
        ],
        scene_judgments=[
            SceneJudgment(
                scene="退款推演陷阱",
                negative_case="押金在验收后转为货款",
                positive_case="供应商交纳履约押金 10 万元",
                analysis="资金方向决定归属，必须看交纳主体",
            ),
        ],
    )


# ---- 1. 毒药词 + rule.logic 进提示词 ----

def test_prompt_has_poison_words_and_logic():
    """poison_words + rule.logic → prompt_text 含「毒药词」段 + logic 内容。"""
    bom = _full_bom()
    full_prompt = assemble_prompt(bom)
    text = full_prompt.prompt_text

    # 毒药词段标题 + 内容
    assert "毒药词" in text, "提示词必须含毒药词段标题"
    assert "员工差旅押金" in text, "毒药词内容应进提示词"
    assert "个人保证金" in text, "第二个毒药词内容应进提示词"

    # rule.logic 进提示词（拦截 + 匹配各一条 logic）
    assert "字面命中无实质，防误抽" in text, "拦截规则的 logic 应进提示词"
    assert "三要素齐备才是真押金条款" in text, "匹配规则的 logic 应进提示词"

    # logic 应以「逻辑：」前缀呈现
    assert "（逻辑：" in text, "logic 应以「（逻辑：...）」格式呈现"


# ---- 2. 判例分析 + 思维链进提示词 ----

def test_prompt_has_scene_judgments_and_reasoning_chain():
    """scene_judgments + reasoning_chain → prompt_text 含判例分析 + 思维链。"""
    bom = _full_bom()
    text = assemble_prompt(bom).prompt_text

    # 判例分析
    assert "判例分析" in text, "提示词必须含判例分析段标题"
    assert "退款推演陷阱" in text, "判例场景应进提示词"
    assert "资金方向决定归属" in text, "判例分析逻辑应进提示词"
    assert "供应商交纳履约押金 10 万元" in text, (
        "判例正例（positive_case，已脱敏）应进提示词"
    )

    # 思维链
    assert "思维链" in text, "提示词必须含思维链段标题"
    assert "谁交钱、谁收钱" in text, "思维链第1步应进提示词"
    assert "排除员工差旅" in text, "思维链第2步应进提示词"


# ---- 3. examples 不进提示词 ----

def test_examples_not_in_prompt():
    """positive_examples + negative_examples 都不进 prompt_text。"""
    bom = _full_bom()
    text = assemble_prompt(bom).prompt_text

    # positive_examples（召回锚点）不应作为独立 examples 段落出现
    assert "供应商缴纳履约押金 10 万元" not in text, (
        "recall_profile.positive_examples 不应进提示词"
    )
    # negative_examples 不应进提示词
    assert "员工差旅押金凭票报销" not in text, (
        "recall_profile.negative_examples 不应进提示词"
    )

    # 注意：scene_judgments.positive_case 里也有「供应商交纳履约押金 10 万元」，
    # 但那是"交纳"（判例正例，已脱敏），与 recall_profile.positive_examples 的"缴纳"不同字。
    # 上面断言用的是"缴纳"，专测 recall_profile.positive_examples 不泄漏。


# ---- 4. 空列表优雅（（无）） ----

def test_empty_lists_render_placeholder():
    """空规则/毒药词/思维链/判例 → 输出「（无）」不崩。"""
    bom = BOM(
        clause="空条款",
        block_code="FSB0000",
        source=BomSource.GENERATE,
        semantic_definition="一个全空的 BOM。",
        extraction_rules=ExtractionRules(),  # 全空
        recall_profile=RecallProfile(),  # 全空
        reasoning_chain=[],
        scene_judgments=[],
    )

    # 不应抛异常
    full_prompt = assemble_prompt(bom)
    text = full_prompt.prompt_text

    # 各精细段空时输出占位「（无）」
    assert "（无）" in text, "空列表应渲染为「（无）」占位"

    # 占位应覆盖各段（拦截 / 毒药词 / 匹配 / 判例 / 思维链 / 关键词 / 易混淆词 / 章节 / 语义查询）
    placeholder_count = text.count("（无）")
    assert placeholder_count >= 9, (
        f"全空 BOM 至少应有 9 处「（无）」占位，实际 {placeholder_count}"
    )

    # 不应残留未替换的 {{var}} 占位符（render_prompt 的约定）
    import re as _re
    leftover = _re.findall(r"\{\{\s*\w+\s*\}\}", text)
    assert not leftover, f"空 BOM 不应残留未替换的 {{var}} 占位符: {leftover}"

    # 核心结构仍在（定义/边界原则/输出 schema）
    assert "空条款" in text
    assert "精准截取" in text
    assert "blockExtractions" in text


# ---- 5. 回归：基础结构保留 ----

def test_prompt_keeps_core_structure():
    """升级后核心结构（条款名/编码/定义/边界原则/JSON Schema）仍保留。"""
    bom = _full_bom()
    text = assemble_prompt(bom).prompt_text

    assert "押金条款" in text
    assert "FSB0001" in text
    assert "交纳一定金额" in text  # 定义片段
    assert "精准截取" in text
    assert "剔除无关信息" in text
    assert "blockExtractions" in text
    import re as _re2
    assert not _re2.findall(r"\{\{\s*\w+\s*\}\}", text), "不应残留未替换的 {{var}} 占位符"

    # bom_snapshot 可追溯
    full_prompt = assemble_prompt(bom)
    assert full_prompt.bom_snapshot.clause == "押金条款"


if __name__ == "__main__":
    test_prompt_has_poison_words_and_logic()
    test_prompt_has_scene_judgments_and_reasoning_chain()
    test_examples_not_in_prompt()
    test_empty_lists_render_placeholder()
    test_prompt_keeps_core_structure()
    print("\n全部测试通过")
