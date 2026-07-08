"""/api 生成场景路由（异步：generate 返回 run_id，status 查节点进度，result 取结果）。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from threading import Thread
from typing import List, Optional

from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import get_db
from ...db import session_scope, PipelineRepository
from ...db.models import PipelineRun, NodeExecution
from ...logging_config import get_logger
from ...nodes.orchestrator import create_default_orchestrator
from ...schemas.generation_state import GenerationState
from ...services.ingest_service import parse_excel_to_cleaned, scan_clauses
import yaml
from ...llm.client import _CONFIG_PATH

router = APIRouter()
log = get_logger("api.generate")


class GenerateResponse(BaseModel):
    """/runs/{run_id}/result 的返回值。"""
    bom: dict
    full_prompt: dict
    verification: Optional[dict] = None
    cleaned_test_set: dict = {}
    selected_examples: List[dict] = Field(
        default_factory=list,
        description="Skill2(ExampleRetrieve) 聚类选取的代表正例（含 doc_id 等行级字段，追溯用）",
    )


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
    db: Session = Depends(get_db),
):
    """上传测试集 → 异步启动生成 → 立即返回 run_id。

    前端用 run_id 轮询 `GET /api/runs/{run_id}/status` 看节点进度，
    `status == "success"` 后调 `GET /api/runs/{run_id}/result` 取 BOM + 提示词。
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


# ==================== 任务列表 + 停止 ====================

@router.get("/runs")
def list_runs(block_code: str = "", db: Session = Depends(get_db)):
    """查生成任务列表（可按 block_code 筛选，含进度%）。"""
    TOTAL_STEPS = 7
    q = db.query(PipelineRun)
    if block_code:
        q = q.filter(PipelineRun.block_code == block_code)
    runs = q.order_by(PipelineRun.id.desc()).all()
    result = []
    for r in runs:
        done = db.query(NodeExecution).filter_by(pipeline_run_id=r.id, is_retry=False).count()
        result.append({
            "run_id": r.id,
            "block_code": r.block_code,
            "status": r.run_status,
            "progress": min(100, round(done / TOTAL_STEPS * 100)) if TOTAL_STEPS else 0,
            "done_nodes": done,
            "total_steps": TOTAL_STEPS,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "duration_ms": r.duration_ms,
            "error_message": r.error_message,
        })
    return {"runs": result}


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: int, db: Session = Depends(get_db)):
    """停止生成任务（标记 cancelled，后台 Thread 自然结束）。"""
    from datetime import datetime
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run {run_id} 不存在")
    if run.run_status != "running":
        raise HTTPException(status_code=400, detail=f"run {run_id} 状态 {run.run_status}，无法停止")
    run.run_status = "cancelled"
    run.finished_at = datetime.now()
    db.commit()
    return {"status": "ok", "run_id": run_id}


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
    """取 run 结果（BOM + 提示词 + 选取正例）。不限 success：失败/取消也返回已产出部分。

    selected_examples 在 Skill2(ExampleRetrieve) 落库，即使后续 Skill3 失败，任务详情也能
    展示「已选取的正例」（对齐原型）。bom/prompt 未完成则为空，前端按存在性渲染。
    """
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run {run_id} 不存在")
    # 取 Skill2(ExampleRetrieve) 选出的代表正例（带 doc_id），从节点 output_json 读
    ex_node = (
        db.query(NodeExecution)
        .filter_by(pipeline_run_id=run_id, skill_name="ExampleRetrieveSkill", is_retry=False)
        .order_by(NodeExecution.seq)
        .first()
    )
    selected: List[dict] = []
    if ex_node and ex_node.output_json:
        selected = ex_node.output_json.get("selected_examples") or []
    return GenerateResponse(
        bom=run.output_bom_json or {},
        full_prompt={"prompt_text": run.output_prompt_text or ""},
        selected_examples=selected,
    )


# ==================== 条款 CRUD ====================

@router.post("/testset/scan")
async def testset_scan(file: UploadFile = File(..., description="测试集 Excel（多 sheet/多条款）"), db: Session = Depends(get_db)):
    """上传测试集 → 存 latest.xlsx + 扫条款 + upsert clauses 表（含用例数/来源/时间）。"""
    from datetime import datetime
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = upload_dir / "latest.xlsx"
    xlsx_path.write_bytes(await file.read())
    try:
        clauses_list = scan_clauses(xlsx_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"扫描失败: {e}")
    from ...db.models import Clause
    now = datetime.now()
    for c in clauses_list:
        existing = db.query(Clause).filter_by(block_code=c["block_code"]).first()
        if existing:
            existing.positive_count = c["positive_count"]
            existing.source_file = file.filename
            existing.imported_at = now
            if not existing.block_name:
                existing.block_name = c["block_name"] or c["block_code"]
        else:
            db.add(Clause(
                block_code=c["block_code"],
                block_name=c["block_name"] or c["block_code"],
                positive_count=c["positive_count"],
                source_file=file.filename,
                imported_at=now,
            ))
    db.commit()
    return {"file_name": file.filename, "clause_count": len(clauses_list), "clauses": clauses_list}


@router.get("/clauses")
def list_clauses(db: Session = Depends(get_db)):
    """取条款列表（查 clauses 表，含用例数/版本/来源，持久化，刷新不丢）。"""
    from ...db.models import Clause
    rows = db.query(Clause).order_by(Clause.imported_at.desc()).all()
    return {"clauses": [
        {"block_code": r.block_code, "block_name": r.block_name,
         "positive_count": r.positive_count or 0, "current_version": r.current_version,
         "source_file": r.source_file}
        for r in rows
    ]}


class ClauseCreate(BaseModel):
    block_code: str
    block_name: str
    domain: str = ""


@router.post("/clauses")
def create_clause(body: ClauseCreate, db: Session = Depends(get_db)):
    """手动新增条款。"""
    from ...db.models import Clause
    if db.query(Clause).filter_by(block_code=body.block_code).first():
        raise HTTPException(status_code=409, detail=f"条款 {body.block_code} 已存在")
    db.add(Clause(block_code=body.block_code, block_name=body.block_name, domain=body.domain))
    db.commit()
    return {"status": "ok", "block_code": body.block_code}


class ClauseUpdate(BaseModel):
    block_name: Optional[str] = None
    domain: Optional[str] = None


@router.put("/clauses/{block_code}")
def update_clause(block_code: str, body: ClauseUpdate, db: Session = Depends(get_db)):
    """改条款信息（名称/域）。"""
    from ...db.models import Clause
    clause = db.query(Clause).filter_by(block_code=block_code).first()
    if not clause:
        raise HTTPException(status_code=404, detail=f"条款 {block_code} 不存在")
    if body.block_name is not None: clause.block_name = body.block_name
    if body.domain is not None: clause.domain = body.domain
    db.commit()
    return {"status": "ok", "block_code": block_code}


@router.delete("/clauses/{block_code}")
def delete_clause(block_code: str, db: Session = Depends(get_db)):
    """删条款 + 级联清理关联数据（BOM/运行/节点/LLM调用/规则修改）。"""
    from ...db.models import Clause, BomVersion, PipelineRun, NodeExecution, LlmCall, RuleModification
    clause = db.query(Clause).filter_by(block_code=block_code).first()
    if not clause:
        raise HTTPException(status_code=404, detail=f"条款 {block_code} 不存在")
    # 按依赖顺序删关联（子→父）
    bom_ids = [b.id for b in db.query(BomVersion).filter_by(block_code=block_code).all()]
    if bom_ids:
        db.query(RuleModification).filter(RuleModification.bom_version_id.in_(bom_ids)).delete(synchronize_session=False)
        db.query(BomVersion).filter(BomVersion.id.in_(bom_ids)).delete(synchronize_session=False)
    run_ids = [r.id for r in db.query(PipelineRun).filter_by(block_code=block_code).all()]
    if run_ids:
        node_ids = [n.id for n in db.query(NodeExecution).filter(NodeExecution.pipeline_run_id.in_(run_ids)).all()]
        if node_ids:
            db.query(LlmCall).filter(LlmCall.node_execution_id.in_(node_ids)).delete(synchronize_session=False)
        db.query(NodeExecution).filter(NodeExecution.pipeline_run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(PipelineRun).filter(PipelineRun.id.in_(run_ids)).delete(synchronize_session=False)
    db.delete(clause)
    db.commit()
    return {"status": "ok", "deleted": block_code}


# ==================== 模型配置（读/写 config/llm.yaml）====================

class ConfigModel(BaseModel):
    """模型配置。POST 时字段留空 = 不改。"""
    api_format: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None  # 留空=不改；填了=覆盖
    temperature_stage1: Optional[float] = None
    temperature_stage2: Optional[float] = None
    temperature_stage3: Optional[float] = None


def _mask_key(k: str) -> str:
    return (k[:4] + "..." + k[-4:]) if len(k) > 8 else "***"


def _clear_llm_cache() -> None:
    """清 llm.client 配置缓存，让后续 LLM 调用读到新配置。"""
    from ...llm import client as _c
    _c._config_cache = None


@router.get("/config")
def get_config():
    """读当前模型配置（api_key 脱敏返回）。"""
    if not _CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="config/llm.yaml 不存在")
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    api_key = cfg.get("api_key", "")
    return {
        "api_format": cfg.get("api_format", "openai"),
        "base_url": cfg.get("base_url", ""),
        "model": cfg.get("model", ""),
        "api_key_masked": _mask_key(api_key),
        "has_api_key": bool(api_key),
        "temperature_stage1": cfg.get("temperature_stage1", 0.2),
        "temperature_stage2": cfg.get("temperature_stage2", 0.5),
        "temperature_stage3": cfg.get("temperature_stage3", 0.0),
    }


@router.post("/config")
def update_config(body: ConfigModel):
    """更新模型配置（写回 config/llm.yaml）。api_key 留空=保持原值（防误清）。"""
    if not _CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="config/llm.yaml 不存在")
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    data = body.model_dump(exclude_none=True)
    if "api_key" in data and not data["api_key"]:
        data.pop("api_key")  # 空值=不改
    cfg.update(data)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    _clear_llm_cache()
    return {"status": "ok", "updated_fields": list(data.keys())}
