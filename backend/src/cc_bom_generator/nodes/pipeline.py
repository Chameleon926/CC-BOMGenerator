"""
生成场景编排入口：把 B1→B5 串起来。

外部调用 generate_bom() 一次，从 CleanedTestSet 跑到 FullPrompt。
"""

from __future__ import annotations

from typing import Optional

from ..contracts.bom import BOM, BomSource
from ..contracts.cleaned_test_set import CleanedTestSet, FullPrompt
from ..contracts.diagnosis import Verification

from .keyword_extract import extract_keywords
from .generate import generate_definition_and_rules
from .profile_build import build_profile
from .verify import verify_bom, has_blocking_issues
from .prompt_assemble import assemble_prompt


def generate_bom(
    cleaned: CleanedTestSet,
    nkw: int = 10,
    nsec: int = 6,
    nq: int = 3,
    skip_verify: bool = False,
) -> tuple[BOM, FullPrompt, Optional[Verification]]:
    """
    生成场景完整编排：CleanedTestSet → BOM + FullPrompt + Verification

    执行顺序：
      B1 keyword_extract（统计，不用大模型）
      B2 generate（大模型，定义+规则）
      B3 profile_build（统计+大模型融合，画像）
      B4 verify（大模型自检，可选）
      B5 prompt_assemble（模板拼装）

    Args:
        cleaned: A 模块交付的清洗后测试集
        nkw: 关键词数量
        nsec: 章节提示数量
        nq: 语义查询数量
        skip_verify: 跳过自检（省时间，但不建议）

    Returns:
        (BOM, FullPrompt, Verification)
        - BOM: 完整语义 BOM（定义+规则+画像）
        - FullPrompt: 旧平台可用的完整提示词
        - Verification: 自检结果（skip_verify 时为 None）
    """
    print(f"  [B1] 关键词抽取（统计，不用大模型）...")
    keywords, confusion_words, positive_examples = extract_keywords(cleaned, top_n=nkw)

    print(f"  [B2] 定义+规则生成（大模型，温度 0.2）...")
    bom = generate_definition_and_rules(cleaned, keywords=keywords)

    print(f"  [B3] 画像组装（统计+大模型融合）...")
    bom = build_profile(
        cleaned=cleaned,
        bom=bom,
        keywords=keywords,
        confusion_words=confusion_words,
        positive_examples=positive_examples,
        nkw=nkw,
        nsec=nsec,
        nq=nq,
    )

    verification = None
    if not skip_verify:
        print(f"  [B4] 规则自检（大模型，温度 0.0）...")
        verification = verify_bom(
            bom=bom,
            positive_examples=positive_examples or cleaned.positive_values[:5],
        )
        if has_blocking_issues(verification):
            print(f"  [B4] ⚠️ 自检发现 {len(verification.red_flags)} 个红旗，建议人工复核")
        else:
            print(f"  [B4] ✅ 自检通过")

    print(f"  [B5] 提示词组装（模板拼装）...")
    full_prompt = assemble_prompt(bom)

    print(f"  ✅ 生成完成：{bom.clause}")
    return bom, full_prompt, verification
