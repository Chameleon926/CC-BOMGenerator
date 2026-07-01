"""/api 生成场景路由。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_db
from ...services.generate_service import run_generate
from ...services.ingest_service import parse_excel_to_cleaned

router = APIRouter()


# ==================== 响应模型 ====================

class GenerateResponse(BaseModel):
    """生成接口的返回值。"""
    bom: dict
    full_prompt: dict
    verification: Optional[dict] = None
    cleaned_test_set: dict


# ==================== 接口 ====================

@router.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "service": "cc-bom-generator"}


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    file: UploadFile = File(..., description="测试集 Excel/CSV"),
    clause: str = Form(..., description="条款名称（如果 Excel 里有多条款，用这个指定）"),
    block_code: str = Form("", description="语义块编码（可选）"),
    domain: str = Form("", description="业务域（可选）"),
    nkw: int = Form(10, description="关键词数量"),
    nsec: int = Form(6, description="章节提示数量"),
    nq: int = Form(3, description="语义查询数量"),
    skip_verify: bool = Form(False, description="跳过自检"),
    db: Session = Depends(get_db),
):
    """
    上传测试集 → 自动生成 BOM + 完整提示词

    流程：解析 Excel → 按条款分组 → 去重 → B1~B5 → 返回结果
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
        bom, full_prompt, verification = run_generate(
            db, cleaned, nkw=nkw, nsec=nsec, nq=nq, skip_verify=skip_verify
        )
        return GenerateResponse(
            bom=bom.model_dump(mode="json"),
            full_prompt=full_prompt.model_dump(mode="json"),
            verification=verification.model_dump(mode="json") if verification else None,
            cleaned_test_set=cleaned.model_dump(mode="json"),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)
