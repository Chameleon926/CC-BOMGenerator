"""
生成场景业务编排层 —— HTTP 事务边界落地点。

run_generate 在注入的 session 上跑管线，service 管 commit/rollback。
与 nodes.pipeline.generate_bom（非 HTTP，用 session_scope）是两条独立事务路径，
不互相委托（避免双 commit）。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..db import PipelineRepository
from ..nodes.orchestrator import create_default_orchestrator
from ..schemas.bom import BOM
from ..schemas.cleaned_test_set import CleanedTestSet, FullPrompt
from ..schemas.diagnosis import Verification
from ..schemas.generation_state import GenerationState


def run_generate(
    session: Session,
    cleaned: CleanedTestSet,
    nkw: int = 10,
    nsec: int = 6,
    nq: int = 3,
    skip_verify: bool = False,
) -> tuple[BOM, FullPrompt, Optional[Verification]]:
    """HTTP 路径业务编排：注入 session 上跑管线，service 管事务。"""
    state = GenerationState(
        cleaned=cleaned,
        nkw=nkw,
        nsec=nsec,
        nq=nq,
        skip_verify=skip_verify,
    )
    orchestrator = create_default_orchestrator()
    repo = PipelineRepository(session)
    try:
        state = orchestrator.run(state, repo)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return state.bom, state.full_prompt, state.verification
