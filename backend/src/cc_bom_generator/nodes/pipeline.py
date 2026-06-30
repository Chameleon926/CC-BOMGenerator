"""
生成场景编排入口。

保持 generate_bom() 入口不变（向后兼容），内部改为调 Orchestrator。
"""

from __future__ import annotations

from typing import Optional

from ..contracts.bom import BOM
from ..contracts.cleaned_test_set import CleanedTestSet, FullPrompt
from ..contracts.diagnosis import Verification
from ..contracts.generation_state import GenerationState
from .orchestrator import create_default_orchestrator


def generate_bom(
    cleaned: CleanedTestSet,
    nkw: int = 10,
    nsec: int = 6,
    nq: int = 3,
    skip_verify: bool = False,
) -> tuple[BOM, FullPrompt, Optional[Verification]]:
    """
    生成场景完整编排：CleanedTestSet → BOM + FullPrompt + Verification

    内部使用 Orchestrator + Skill 流水线架构。
    对外接口保持不变，向后兼容。
    """
    # 初始化状态
    state = GenerationState(
        cleaned=cleaned,
        nkw=nkw,
        nsec=nsec,
        nq=nq,
        skip_verify=skip_verify,
    )

    # 创建并运行编排器
    orchestrator = create_default_orchestrator()
    state = orchestrator.run(state)

    # 提取结果
    bom = state.bom
    full_prompt = state.full_prompt
    verification = state.verification

    print(f"\n  ✅ 生成完成：{bom.clause}")
    if verification:
        print(f"  自检结论: {verification.summary[:80]}")
    print(f"  提示词长度: {len(full_prompt.prompt_text)} 字")

    return bom, full_prompt, verification
