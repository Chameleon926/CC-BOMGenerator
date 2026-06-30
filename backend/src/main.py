"""
FastAPI 主入口

提供生成场景的 REST API 接口。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.cc_bom_generator.contracts.cleaned_test_set import CleanedTestSet, FullPrompt
from src.cc_bom_generator.contracts.bom import BOM
from src.cc_bom_generator.contracts.diagnosis import Verification
from src.cc_bom_generator.nodes.pipeline import generate_bom

app = FastAPI(
    title="CC-BOMGenerator API",
    description="语义 BOM 规则编译器 — 生成场景后端接口",
    version="0.1.0",
)

# 允许前端跨域（开发期）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 响应模型 ====================

class GenerateResponse(BaseModel):
    """生成接口的返回值。"""
    bom: dict
    full_prompt: dict
    verification: Optional[dict] = None
    cleaned_test_set: dict


# ==================== 接口 ====================

@app.get("/api/health")
def health():
    """健康检查"""
    return {"status": "ok", "service": "cc-bom-generator"}


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(
    file: UploadFile = File(..., description="测试集 Excel/CSV"),
    clause: str = Form(..., description="条款名称（如果 Excel 里有多条款，用这个指定）"),
    block_code: str = Form("", description="语义块编码（可选）"),
    domain: str = Form("", description="业务域（可选）"),
    nkw: int = Form(10, description="关键词数量"),
    nsec: int = Form(6, description="章节提示数量"),
    nq: int = Form(3, description="语义查询数量"),
    skip_verify: bool = Form(False, description="跳过自检"),
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
        # ---- 解析 Excel（简版，后续 A 模块接管）----
        cleaned = _parse_excel_to_cleaned(
            tmp_path, clause=clause, block_code=block_code, domain=domain
        )

        # ---- 跑生成管线 ----
        bom, full_prompt, verification = generate_bom(
            cleaned=cleaned,
            nkw=nkw,
            nsec=nsec,
            nq=nq,
            skip_verify=skip_verify,
        )

        # ---- 序列化返回 ----
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


# ==================== 内部函数（简版解析，A 模块接管后替换）====

def _parse_excel_to_cleaned(
    path: Path,
    clause: str,
    block_code: str = "",
    domain: str = "",
) -> CleanedTestSet:
    """
    简版 Excel 解析：读期望值列，去重，返回 CleanedTestSet。
    A 模块（杨力）写完后替换这个。
    """
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    df = df.fillna("")

    # 自适应列名
    expected_col = _find_col(df, ["expected_value", "期望值", "期望结果", "期望"])
    if not expected_col:
        raise ValueError("找不到期望值列（expected_value / 期望值 / 期望结果）")

    block_name_col = _find_col(df, ["block_name", "语义块名称", "块/项名称", "条款名称"])
    block_code_col = _find_col(df, ["block_code", "语义块编码", "块/项编码", "条款编码"])

    # 如果有 block_code 列，按条款分组取指定条款
    if block_code_col and block_code:
        df = df[df[block_code_col].astype(str).str.strip() == block_code]

    # 提取期望值并去重
    values = [
        str(v).strip()
        for v in df[expected_col]
        if str(v).strip()
    ]
    # 精确去重保序
    seen = set()
    unique_values = []
    for v in values:
        if v not in seen:
            seen.add(v)
            unique_values.append(v)

    # 从数据中取 block_code / clause
    if not block_code and block_code_col:
        block_code = str(df[block_code_col].iloc[0]).strip() if len(df) > 0 else ""

    if not clause and block_name_col:
        clause = str(df[block_name_col].iloc[0]).strip() if len(df) > 0 else clause

    return CleanedTestSet(
        clause=clause,
        block_code=block_code,
        domain=domain,
        positive_values=unique_values,
        original_count=len(values),
        after_dedup=len(unique_values),
    )


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """自适应列名查找（去空格、大小写无关）。"""
    col_map = {str(c).replace(" ", "").lower(): c for c in df.columns}
    for name in candidates:
        key = name.replace(" ", "").lower()
        if key in col_map:
            return col_map[key]
    return None


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
