"""/api 生成场景路由（异步：generate 返回 run_id，status 查节点进度，result 取结果）。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from threading import Thread
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db
from ...db import session_scope, PipelineRepository
from ...db.models import PipelineRun, NodeExecution
from ...logging_config import get_logger
from ...nodes.orchestrator import create_default_orchestrator
from ...schemas.generation_state import GenerationState
from ...services.ingest_service import parse_excel_to_cleaned

router = APIRouter()
log = get_logger("api.generate")


class GenerateResponse(BaseModel):
    """/runs/{run_id}/result 的返回值。"""
    bom: dict
    full_prompt: dict
    verification: Optional[dict] = None
    cleaned_test_set: dict = {}


@router.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "service": "cc-bom-generator"}


@router.post("/generate")
async def generate(
    file: UploadFile = File(..., description="测试集 Excel/CSV"),
    clause: str = Form("", description="条款名称（可选，默认从测试集 Block Name 列取）"),
    block_code: str = Form("", description="语义块编码（可选）"),
    domain: str = Form("", description="业务域（可选）"),
    nkw: int = Form(10, description="关键词数量"),
    nsec: int = Form(6, description="章节提示数量"),
    nq: int = Form(3, description="语义查询数量"),
    skip_verify: bool = Form(False, description="跳过自检"),
    db: Session = Depends(get_db),
):
    """上传测试集 → 异步启动生成 → 立即返回 run_id。

    前端用 run_id 轮询 `GET /api/runs/{run_id}/status` 看节点进度，
    `status == "success"` 后调 `GET /api/runs/{run_id}/result` 取 BOM + 提示词。
    """
    # ---- 保存上传文件到临时路径 ----
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        cleaned = parse_excel_to_cleaned(
            tmp_path, clause=clause, block_code=block_code, domain=domain
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    # ---- 同步：创建 pipeline_run，拿 run_id（持久化后前端立即可查）----
    state = GenerationState(
        cleaned=cleaned, nkw=nkw, nsec=nsec, nq=nq, skip_verify=skip_verify,
    )
    repo = PipelineRepository(db)
    run_id = repo.start_pipeline_run(
        block_code=cleaned.block_code,
        block_name=cleaned.clause,
        mode="generate",
        input_cleaned_json=cleaned.model_dump(mode="json"),
    )
    db.commit()

    # ---- 异步：起线程跑剩余节点（skills + finish + save_bom），独立 session/事务 ----
    Thread(target=_bg_generate, args=(run_id, state), daemon=True).start()

    return {
        "run_id": run_id,
        "status": "running",
        "block_code": cleaned.block_code,
        "clause": cleaned.clause,
    }


def _bg_generate(run_id: int, state: GenerationState) -> None:
    """后台线程：复用 run_id 跑 orchestrator 剩余节点。独立 session_scope 事务。"""
    try:
        with session_scope() as session:
            repo = PipelineRepository(session)
            orchestrator = create_default_orchestrator()
            orchestrator.run(state, repo, run_id=run_id, commit_after_each=True)
    except Exception as e:
        log.error(f"后台 generate run_id={run_id} 失败: {e}")


# ==================== 进度查询 ====================

@router.get("/runs/{run_id}/status")
def run_status(run_id: int, db: Session = Depends(get_db)):
    """查 run 进度：run 状态 + 已完成节点列表（序号/技能名/是否成功/是否回修/耗时）。"""
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run {run_id} 不存在")
    nodes = (
        db.query(NodeExecution)
        .filter(NodeExecution.pipeline_run_id == run_id)
        .order_by(NodeExecution.seq)
        .all()
    )
    return {
        "run_id": run_id,
        "status": run.run_status,          # running / success / fail
        "block_code": run.block_code,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_ms": run.duration_ms,
        "error_message": run.error_message,
        "nodes": [
            {
                "seq": n.seq,
                "skill": n.skill_name,
                "success": n.success,
                "is_retry": bool(n.is_retry),
                "retry_round": n.retry_round,
                "duration_ms": n.duration_ms,
            }
            for n in nodes
        ],
    }


@router.get("/runs/{run_id}/result")
def run_result(run_id: int, db: Session = Depends(get_db)):
    """run 成功后取完整结果（BOM + 提示词，粘新平台跑分用）。"""
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run {run_id} 不存在")
    if run.run_status != "success":
        raise HTTPException(
            status_code=409,
            detail=f"run status={run.run_status}，未完成或失败，无法取结果",
        )
    return GenerateResponse(
        bom=run.output_bom_json or {},
        full_prompt={"prompt_text": run.output_prompt_text or ""},
    )
