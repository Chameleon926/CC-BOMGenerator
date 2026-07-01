"""
数据摄入服务（简版）。

TODO(杨力 / A 模块)：A 模块数据预处理（Excel 解析 → 去重 → 清洗 → 脱敏）接管后，
替换此简版实现，输出对齐 schemas.cleaned_test_set.CleanedTestSet。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from ..schemas.cleaned_test_set import CleanedTestSet


def parse_excel_to_cleaned(
    path: Path,
    clause: str,
    block_code: str = "",
    domain: str = "",
) -> CleanedTestSet:
    """简版 Excel 解析：读期望值列，去重，返回 CleanedTestSet。"""
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    df = df.fillna("")

    # 自适应列名
    expected_col = find_col(df, ["expected_value", "期望值", "期望结果", "期望"])
    if not expected_col:
        raise ValueError("找不到期望值列（expected_value / 期望值 / 期望结果）")

    block_name_col = find_col(df, ["block_name", "语义块名称", "块/项名称", "条款名称"])
    block_code_col = find_col(df, ["block_code", "语义块编码", "块/项编码", "条款编码"])

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


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """自适应列名查找（去空格、大小写无关）。"""
    col_map = {str(c).replace(" ", "").lower(): c for c in df.columns}
    for name in candidates:
        key = name.replace(" ", "").lower()
        if key in col_map:
            return col_map[key]
    return None
