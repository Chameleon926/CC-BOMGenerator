"""/api 条款：导入测试集扫描 + 条款 CRUD。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db
from ...db.models import (
    Clause, BomVersion, PipelineRun, NodeExecution, LlmCall, RuleModification,
    TestSetImport, TestCase,
)
from ...nodes.skills._prompt_logic import assemble_prompt
from ...schemas.bom import BOM
from ...services.ingest_service import scan_clauses

router = APIRouter()


@router.post("/testset/scan")
async def testset_scan(file: UploadFile = File(..., description="测试集 Excel（多 sheet/多条款）"), db: Session = Depends(get_db)):
    """上传测试集 → 存 latest.xlsx + 扫条款 + upsert clauses 表（含用例数/来源/时间）。"""
    upload_dir = Path("data/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = upload_dir / "latest.xlsx"
    xlsx_path.write_bytes(await file.read())
    try:
        clauses_list = scan_clauses(xlsx_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"扫描失败: {e}")
    now = datetime.now()
    # 解析每条款的正例数据（存 DB，防重部署丢 latest.xlsx）
    import pandas as pd
    from ...services.ingest_service import find_col
    df = pd.read_excel(xlsx_path).fillna("")
    expected_col = find_col(df, ["expected_value", "期望值", "期望结果"])
    block_code_col = find_col(df, ["block_code", "语义块编码", "块/项编码", "条款编码"])
    doc_id_col = find_col(df, ["doc_id", "文档id", "文档编号"])
    item_code_col = find_col(df, ["item_code", "子项编码", "项编码"])
    item_name_col = find_col(df, ["item_name", "子项名称", "项名称"])

    for c in clauses_list:
        bc = c["block_code"]
        # 筛选该条款的行
        clause_df = df[df[block_code_col].astype(str).str.strip() == bc] if block_code_col else df
        total_for_clause = len(clause_df)  # 总用例数（含空期望值的负例）
        values = [str(v).strip() for v in clause_df[expected_col] if str(v).strip()] if expected_col else []
        seen_v = set(); unique_values = []
        for v in values:
            if v not in seen_v: seen_v.add(v); unique_values.append(v)
        # 正例行（含 doc_id，精确去重）
        pos_examples = []; seen_r = set()
        for _, row in clause_df.iterrows():
            ev = str(row[expected_col]).strip() if expected_col else ""
            if not ev: continue
            did = str(row[doc_id_col]).strip() if doc_id_col else ""
            ic = str(row[item_code_col]).strip() if item_code_col else ""
            inm = str(row[item_name_col]).strip() if item_name_col else ""
            rk = (did, ev, ic, inm)
            if rk in seen_r: continue
            seen_r.add(rk)
            pos_examples.append({"doc_id": did, "expected_value": ev, "item_code": ic, "item_name": inm})

        existing = db.query(Clause).filter_by(block_code=bc).first()
        if existing:
            existing.positive_count = c["positive_count"]
            existing.total_count = total_for_clause
            existing.source_file = file.filename
            existing.imported_at = now
            existing.positive_values_json = unique_values
            existing.positive_examples_json = pos_examples
            if not existing.block_name:
                existing.block_name = c["block_name"] or c["block_code"]
        else:
            db.add(Clause(
                block_code=bc, block_name=c["block_name"] or c["block_code"],
                positive_count=c["positive_count"], total_count=total_for_clause,
                source_file=file.filename, imported_at=now,
                positive_values_json=unique_values, positive_examples_json=pos_examples,
            ))
    # ---- 用例库：创建 TestSetImport + TestCase（全部行存 DB，含负例）----
    import hashlib
    file_hash = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()[:16]
    existing_ts = db.query(TestSetImport).filter_by(file_hash=file_hash).first()
    if existing_ts:
        existing_ts.imported_at = now
        ts_id = existing_ts.id
    else:
        ts = TestSetImport(file_name=file.filename, file_hash=file_hash)
        db.add(ts)
        db.flush()
        ts_id = ts.id
        total = 0; positive = 0; negative = 0; seen_blocks = set()
        for _, row in df.iterrows():
            total += 1
            bc = str(row[block_code_col]).strip() if block_code_col else ""
            if bc:
                seen_blocks.add(bc)
            ev = str(row[expected_col]).strip() if expected_col else ""
            has_ev = bool(ev)
            if has_ev:
                positive += 1
            else:
                negative += 1
            did = str(row[doc_id_col]).strip() if doc_id_col else ""
            row_data = {str(col): str(row[col]) for col in df.columns if str(row[col]).strip()}
            db.add(TestCase(
                test_set_id=ts_id, block_code=bc, doc_id=did,
                expected_value=ev if has_ev else "",
                has_expected=has_ev, row_data=row_data,
            ))
        ts.total_cases = total
        ts.positive_cases = positive
        ts.negative_cases = negative
        ts.clauses_count = len(seen_blocks)

    db.commit()
    return {"file_name": file.filename, "clause_count": len(clauses_list), "clauses": clauses_list}


@router.get("/clauses")
def list_clauses(db: Session = Depends(get_db)):
    """取条款列表（查 clauses 表，含用例数/版本/来源，持久化，刷新不丢）。"""
    rows = db.query(Clause).order_by(Clause.imported_at.desc()).all()
    return {"clauses": [
        {"block_code": r.block_code, "block_name": r.block_name,
         "positive_count": r.positive_count or 0, "current_version": r.current_version,
         "source_file": r.source_file}
        for r in rows
    ]}


@router.get("/clauses/{block_code}/examples")
def get_examples(block_code: str, db: Session = Depends(get_db)):
    """预览条款的正例数据（DB 存的，重部署不丢）。"""
    clause = db.query(Clause).filter_by(block_code=block_code).first()
    if not clause:
        raise HTTPException(status_code=404, detail=f"条款 {block_code} 不存在")
    return {
        "block_code": block_code,
        "block_name": clause.block_name,
        "positive_values": clause.positive_values_json or [],
        "positive_examples": clause.positive_examples_json or [],
        "total_count": clause.total_count or 0,
        "positive_count": clause.positive_count or 0,
        "count": len(clause.positive_values_json or []),
    }


class ClauseCreate(BaseModel):
    block_code: str
    block_name: str
    domain: str = ""


@router.post("/clauses")
def create_clause(body: ClauseCreate, db: Session = Depends(get_db)):
    """手动新增条款。"""
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


# ==================== 典型正例编辑（TE-4）====================

class TypicalExampleItem(BaseModel):
    value: str
    reason: str = ""


class TypicalExamplesUpdate(BaseModel):
    typical_examples: List[TypicalExampleItem]


@router.put("/clauses/{block_code}/typical-examples")
def update_typical_examples(block_code: str, body: TypicalExamplesUpdate, db: Session = Depends(get_db)):
    """编辑最新 bom_version 的典型正例（value/reason）+ 重 assemble 提示词。原地更新（不版本递增）。

    同步更新关联 run（bom_version.pipeline_run_id）的输出快照，
    让任务详情（读 run.output_bom_json/prompt）立刻反映编辑。
    """
    clause = db.query(Clause).filter_by(block_code=block_code).first()
    if not clause:
        raise HTTPException(status_code=404, detail=f"条款 {block_code} 不存在")
    bom_ver = (
        db.query(BomVersion)
        .filter_by(block_code=block_code, version=clause.current_version)
        .first()
    )
    if not bom_ver:
        raise HTTPException(status_code=404, detail=f"条款 {block_code} 尚无 BOM，请先生成")

    bom_dict = dict(bom_ver.full_bom_json or {})
    bom_dict["typical_examples"] = [te.model_dump() for te in body.typical_examples]
    bom = BOM.model_validate(bom_dict)
    new_prompt = assemble_prompt(bom)
    bom_ver.full_bom_json = bom.model_dump(mode="json")
    bom_ver.prompt_text = new_prompt.prompt_text

    # 同步关联 run 的输出快照（任务详情读 run.output_bom_json/prompt）
    if bom_ver.pipeline_run_id:
        run = db.get(PipelineRun, bom_ver.pipeline_run_id)
        if run:
            run.output_bom_json = bom_ver.full_bom_json
            run.output_prompt_text = bom_ver.prompt_text

    db.commit()
    return {"status": "ok", "block_code": block_code, "version": clause.current_version, "count": len(body.typical_examples)}
