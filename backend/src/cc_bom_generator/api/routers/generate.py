"""/api 生成场景：POST /generate（异步，返 run_id）+ 健康检查。

任务列表/停止/进度/结果见 runs.py；条款 CRUD 见 clauses.py；模型配置见 config.py。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from threading import Thread

from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db
from ...db import session_scope, PipelineRepository
from ...enums import RunStatus
from ...logging_config import get_logger
from ...nodes.orchestrator import create_default_orchestrator
from ...schemas.generation_state import GenerationState
from ...services.ingest_service import parse_excel_to_cleaned

router = APIRouter()
log = get_logger("api.generate")


@router.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "service": "cc-bom-generator"}


@router.post("/generate")
async def generate(
    file: UploadFile = File(None, description="测试集 Excel（可选，不传则用后端存的 latest.xlsx）"),
    clause: str = Form("", description="条款名称（可选，默认从测试集 Block Name 列取）"),
    block_code: str = Form("", description="语义块编码（可选）"),
    domain: str = Form("", description="业务域（可选）"),
    nkw: int = Form(10, description="关键词数量"),
    nsec: int = Form(6, description="章节提示数量"),
    nq: int = Form(3, description="语义查询数量"),
    skip_verify: bool = Form(False, description="跳过自检"),
    num_examples: int = Form(5, description="正例选取数量（典型正例数）"),
    db: Session = Depends(get_db),
):
    """上传测试集 → 异步启动生成 → 立即返回 run_id。

    前端用 run_id 轮询 `GET /api/runs/{run_id}/status` 看节点进度，
    成功后调 `GET /api/runs/{run_id}/result` 取 BOM + 提示词。
    file 可选：不传则用后端 data/uploads/latest.xlsx（scan 时存，刷新页面也能 generate）。
    """
    # ---- 文件来源：新上传 or 后端存的 latest.xlsx ----
    use_temp = False
    if file and file.filename:
        suffix = Path(file.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
        tmp_path = Path(tmp.name)
        use_temp = True
    else:
        tmp_path = Path("data/uploads/latest.xlsx")
        if not tmp_path.exists():
            raise HTTPException(status_code=400, detail="未上传测试集，请先上传扫描")

    try:
        cleaned = parse_excel_to_cleaned(
            tmp_path, clause=clause, block_code=block_code, domain=domain
        )
    finally:
        if use_temp:
            tmp_path.unlink(missing_ok=True)

    # ---- 同步：创建 pipeline_run，拿 run_id（持久化后前端立即可查）----
    # 上限 20（每个正例要 LLM 写理由，太多超 token + 召回慢）
    num_examples = min(num_examples, 20)
    # 校验：正例数量不能超过测试集可用正例数
    num_available = len(cleaned.positive_values)
    if num_examples > num_available and num_available > 0:
        raise HTTPException(
            status_code=400,
            detail=f"测试集只有 {num_available} 个正例（去重后），无法生成 {num_examples} 个典型正例。请将数量调整为 ≤ {num_available}。",
        )

    state = GenerationState(
        cleaned=cleaned, nkw=nkw, nsec=nsec, nq=nq, skip_verify=skip_verify,
        num_examples=num_examples,
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
        "status": RunStatus.RUNNING.value,
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
