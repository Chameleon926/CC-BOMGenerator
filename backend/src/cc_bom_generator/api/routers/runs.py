"""/api 生成任务：列表（每条款最新一条）/ 停止 / 进度 / 结果。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import get_db
from ...db.models import PipelineRun, NodeExecution
from ...enums import RunStatus

router = APIRouter()


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
    keywords: List[str] = Field(
        default_factory=list,
        description="Skill1(FeatureExtract) 统计抽取的正向关键词（后续节点失败时也能展示部分结果）",
    )
    confusion_words: List[str] = Field(
        default_factory=list,
        description="Skill1(FeatureExtract) 统计抽取的易混淆词",
    )


@router.get("/runs")
def list_runs(block_code: str = "", db: Session = Depends(get_db)):
    """查生成任务列表：每个条款只返回**最新一条 run**（GROUP BY max(id) 取最新创建/更新的）。

    历史 run 留在 pipeline_runs 表（详情页 /runs/:id 仍可访问任意历史 run）。
    block_code 可选筛选（筛选后仍只返该条款最新一条）。
    """
    TOTAL_STEPS = 7
    # 每个条款取最新 run：max(id) 分组（id 自增 = 最新创建/更新）
    latest_ids = db.query(func.max(PipelineRun.id)).group_by(PipelineRun.block_code)
    if block_code:
        latest_ids = latest_ids.filter(PipelineRun.block_code == block_code)
    runs = (
        db.query(PipelineRun)
        .filter(PipelineRun.id.in_(latest_ids))
        .order_by(PipelineRun.id.desc())
        .all()
    )
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
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"run {run_id} 不存在")
    if run.run_status != RunStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail=f"run {run_id} 状态 {run.run_status}，无法停止")
    run.run_status = RunStatus.CANCELLED.value
    run.finished_at = datetime.now()
    db.commit()
    return {"status": "ok", "run_id": run_id}


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
        "status": run.run_status,
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
    # Skill1(FeatureExtract) 关键词/混淆词（失败时也能展示部分结果）
    kw_node = (
        db.query(NodeExecution)
        .filter_by(pipeline_run_id=run_id, skill_name="FeatureExtractSkill", is_retry=False)
        .order_by(NodeExecution.seq)
        .first()
    )
    keywords: List[str] = []
    confusion_words: List[str] = []
    if kw_node and kw_node.output_json:
        keywords = kw_node.output_json.get("keywords") or []
        confusion_words = kw_node.output_json.get("confusion_words") or []
    return GenerateResponse(
        bom=run.output_bom_json or {},
        full_prompt={"prompt_text": run.output_prompt_text or ""},
        selected_examples=selected,
        keywords=keywords,
        confusion_words=confusion_words,
    )
