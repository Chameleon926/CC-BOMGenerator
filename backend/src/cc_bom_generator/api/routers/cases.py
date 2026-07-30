"""/api/cases 用例库路由（条款视角：每行=一个条款的用例统计）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import get_db
from ...db.models import Clause, TestCase

router = APIRouter()


@router.get("/cases")
def list_cases(
    search: str = Query("", description="按条款名称/编码模糊搜索"),
    db: Session = Depends(get_db),
):
    """用例库列表（条款视角）：每行=一个条款，含正例/负例统计。"""
    # 从 test_cases 聚合统计
    stats_subq = (
        db.query(
            TestCase.block_code.label("bc"),
            func.count(TestCase.id).label("total"),
            func.sum(func.IF(TestCase.has_expected == True, 1, 0)).label("positive"),  # noqa: E712
            func.sum(func.IF(TestCase.has_expected == False, 1, 0)).label("negative"),  # noqa: E712
        )
        .filter(TestCase.block_code != "")
        .group_by(TestCase.block_code)
        .subquery()
    )

    q = (
        db.query(
            Clause.block_code,
            Clause.block_name,
            Clause.positive_count,
            Clause.total_count,
            func.coalesce(stats_subq.c.total, 0).label("case_total"),
            func.coalesce(stats_subq.c.positive, 0).label("case_positive"),
            func.coalesce(stats_subq.c.negative, 0).label("case_negative"),
        )
        .outerjoin(stats_subq, stats_subq.c.bc == Clause.block_code)
    )

    # 模糊搜索（条款名称 + 编码）
    if search.strip():
        kw = f"%{search.strip()}%"
        q = q.filter(Clause.block_name.like(kw) | Clause.block_code.like(kw))

    rows = q.order_by(Clause.block_code).all()
    return {"cases": [{
        "block_code": r.block_code,
        "block_name": r.block_name or r.block_code,
        "total": int(r.case_total or 0),
        "positive": int(r.case_positive or 0),
        "negative": int(r.case_negative or 0),
        "clause_positive_count": r.positive_count or 0,
        "clause_total_count": r.total_count or 0,
    } for r in rows]}


@router.get("/cases/{block_code}/rows")
def get_case_rows(
    block_code: str,
    filter: str = Query("all", description="all|positive|negative"),
    limit: int = Query(500, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """某条款的用例行（分页 + 正负例筛选）。"""
    q = db.query(TestCase).filter_by(block_code=block_code)
    if filter == "positive":
        q = q.filter(TestCase.has_expected == True)  # noqa: E712
    elif filter == "negative":
        q = q.filter(TestCase.has_expected == False)  # noqa: E712
    total = q.count()
    rows = q.order_by(TestCase.id).offset(offset).limit(limit).all()
    # 条款名
    clause = db.query(Clause).filter_by(block_code=block_code).first()
    return {
        "block_code": block_code,
        "block_name": clause.block_name if clause else block_code,
        "total": total,
        "rows": [{
            "id": r.id,
            "doc_id": r.doc_id or "",
            "expected_value": r.expected_value or "",
            "has_expected": bool(r.has_expected),
            "row_data": r.row_data or {},
        } for r in rows],
    }
