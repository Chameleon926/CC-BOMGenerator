"""
生成场景编排入口（非 HTTP 同步入口）。

保持 generate_bom() 入口签名不变（向后兼容），内部改为：
Orchestrator + Repository + session_scope（run 级 Unit-of-Work 事务）。
"""

from __future__ import annotations

from typing import Optional

from ..db import session_scope, PipelineRepository
from ..schemas.bom import BOM
from ..schemas.cleaned_test_set import CleanedTestSet, FullPrompt
from ..schemas.diagnosis import Verification
from ..schemas.generation_state import GenerationState
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

    内部使用 Orchestrator + Skill 流水线 + Repository 写库。
    一次调用包在 session_scope 里 = 一个事务（run 级 UoW，全成或全回滚）。
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

    # 创建编排器，在 session_scope 事务内执行（出块统一 commit / 异常 rollback）
    orchestrator = create_default_orchestrator()
    with session_scope() as session:
        repo = PipelineRepository(session)
        state = orchestrator.run(state, repo)

    # session 已 commit+close；bom/full_prompt/verification 是 pydantic 对象，可安全读取
    bom = state.bom
    full_prompt = state.full_prompt
    verification = state.verification

    print(f"\n  ✅ 生成完成：{bom.clause}")
    if verification:
        print(f"  自检结论: {verification.summary[:80]}")
    print(f"  提示词长度: {len(full_prompt.prompt_text)} 字")

    return bom, full_prompt, verification
