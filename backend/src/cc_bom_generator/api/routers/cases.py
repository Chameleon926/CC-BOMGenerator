"""/api/cases 用例库路由（测试集列表/详情/用例行/删除）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..deps import get_db
from ...db.models import TestSetImport, TestCase

router = APIRouter()


@router.get("/cases")
def list_cases(db: Session = Depends(get_db)):
    """列测试集（文件级，每次导入一条）。"""
    rows = db.query(TestSetImport).order_by(TestSetImport.imported_at.desc()).all()
    return {"cases": [{
        "id": r.id,
        "file_name": r.file_name,
        "file_hash": (r.file_hash or "")[:12],
        "total_cases": r.total_cases or 0,
        "positive_cases": r.positive_cases or 0,
        "negative_cases": r.negative_cases or 0,
        "clauses_count": r.clauses_count or 0,
        "imported_at": r.imported_at,
    } for r in rows]}


@router.get("/cases/{test_set_id}")
def get_case(test_set_id: int, db: Session = Depends(get_db)):
    """测试集详情（元数据）。"""
    ts = db.get(TestSetImport, test_set_id)
    if not ts:
        raise HTTPException(status_code=404, detail=f"测试集 {test_set_id} 不存在")
    # 覆盖的条款列表（去重）
    block_codes = [r[0] for r in db.query(TestCase.block_code)
                   .filter_by(test_set_id=test_set_id)
                   .distinct().all() if r[0]]
    return {
        "id": ts.id,
        "file_name": ts.file_name,
        "total_cases": ts.total_cases or 0,
        "positive_cases": ts.positive_cases or 0,
        "negative_cases": ts.negative_cases or 0,
        "clauses_count": ts.clauses_count or 0,
        "imported_at": ts.imported_at,
        "block_codes": block_codes,
    }


@router.get("/cases/{test_set_id}/rows")
def get_case_rows(
    test_set_id: int,
    block_code: str = Query("", description="按条款筛选"),
    filter: str = Query("all", description="all|positive|negative"),
    limit: int = Query(500, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """用例行（分页 + 按条款/正负例筛选）。返回原始列 row_data + 提取字段。"""
    q = db.query(TestCase).filter_by(test_set_id=test_set_id)
    if block_code:
        q = q.filter(TestCase.block_code == block_code)
    if filter == "positive":
        q = q.filter(TestCase.has_expected == True)  # noqa: E712
    elif filter == "negative":
        q = q.filter(TestCase.has_expected == False)  # noqa: E712
    total = q.count()
    rows = q.order_by(TestCase.id).offset(offset).limit(limit).all()
    return {
        "total": total,
        "rows": [{
            "id": r.id,
            "block_code": r.block_code or "",
            "doc_id": r.doc_id or "",
            "expected_value": r.expected_value or "",
            "has_expected": bool(r.has_expected),
            "row_data": r.row_data or {},
        } for r in rows],
    }


@router.delete("/cases/{test_set_id}")
def delete_case(test_set_id: int, db: Session = Depends(get_db)):
    """删测试集 + 级联删 test_cases。"""
    ts = db.get(TestSetImport, test_set_id)
    if not ts:
        raise HTTPException(status_code=404, detail=f"测试集 {test_set_id} 不存在")
    db.query(TestCase).filter_by(test_set_id=test_set_id).delete(synchronize_session=False)
    db.delete(ts)
    db.commit()
    return {"status": "ok", "deleted": test_set_id}
