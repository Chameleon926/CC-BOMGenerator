"""
数据摄入服务（简版）。

TODO(杨力 / A 模块)：A 模块数据预处理（Excel 解析 → 去重 → 清洗 → 脱敏）接管后，
替换此简版实现，输出对齐 schemas.cleaned_test_set.CleanedTestSet。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from ..schemas.cleaned_test_set import CleanedTestSet, PositiveExample


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

    # 行级字段（保留 doc_id 等，供 Skill2 选取代表正例时带回 doc_id / 追溯）
    doc_id_col = find_col(df, ["doc_id", "文档id", "文档编号"])
    item_code_col = find_col(df, ["item_code", "子项编码", "项编码"])
    item_name_col = find_col(df, ["item_name", "子项名称", "项名称"])
    doc_name_col = find_col(df, ["doc_name", "文档名称"])

    # 如果有 block_code 列，按条款分组取指定条款
    if block_code_col and block_code:
        df = df[df[block_code_col].astype(str).str.strip() == block_code]

    # 提取期望值并去重（字符串，关键词抽取用）
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

    # 全行正例（保留 doc_id 等行级字段，精确去重；供选取/追溯）
    positive_examples: list[PositiveExample] = []
    seen_rows: set[tuple] = set()
    for _, row in df.iterrows():
        ev = str(row[expected_col]).strip()
        if not ev:
            continue
        doc_id = str(row[doc_id_col]).strip() if doc_id_col else ""
        item_code = str(row[item_code_col]).strip() if item_code_col else ""
        item_name = str(row[item_name_col]).strip() if item_name_col else ""
        doc_name = str(row[doc_name_col]).strip() if doc_name_col else ""
        row_key = (doc_id, ev, item_code, item_name, doc_name)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        positive_examples.append(PositiveExample(
            doc_id=doc_id, expected_value=ev,
            item_code=item_code, item_name=item_name, doc_name=doc_name,
        ))

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
        positive_examples=positive_examples,
        original_count=len(values),
        after_dedup=len(unique_values),
    )


def find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """自适应列名查找（去空格+去下划线+大小写无关：'Block Code' / 'block_code' / 'blockcode' 都匹配）。"""
    def _norm(s) -> str:
        return str(s).replace(" ", "").replace("_", "").replace("-", "").lower()
    col_map = {_norm(c): c for c in df.columns}
    for name in candidates:
        key = _norm(name)
        if key in col_map:
            return col_map[key]
    return None


def scan_clauses(path: Path) -> list[dict]:
    """扫描测试集所有 sheet，提取条款列表（按 block_code 去重）。

    支持 1 个或多个 sheet，每 sheet 1 个或多个条款。
    返回 [{block_code, block_name, positive_count, sheets: [sheet名]}]，供前端渲染左侧条款列表。
    """
    if path.suffix.lower() not in (".xlsx", ".xls"):
        sheets = {"(csv)": pd.read_csv(path).fillna("")}
    else:
        xls = pd.ExcelFile(path)
        sheets = {s: pd.read_excel(xls, sheet_name=s).fillna("") for s in xls.sheet_names}

    clauses: dict[str, dict] = {}
    for sheet_name, df in sheets.items():
        bc_col = find_col(df, ["block_code", "语义块编码", "块/项编码", "条款编码"])
        bn_col = find_col(df, ["block_name", "语义块名称", "块/项名称", "条款名称"])
        expected_col = find_col(df, ["expected_value", "期望值", "期望结果", "期望"])
        if not bc_col:
            continue  # 该 sheet 无 block_code 列，跳过
        for _, row in df.iterrows():
            bc = str(row[bc_col]).strip()
            if not bc:
                continue
            bn = str(row[bn_col]).strip() if bn_col else ""
            has_value = bool(expected_col and str(row[expected_col]).strip())
            if bc not in clauses:
                clauses[bc] = {
                    "block_code": bc, "block_name": bn,
                    "positive_count": 0, "sheets": set(),
                }
            if has_value:
                clauses[bc]["positive_count"] += 1
            clauses[bc]["sheets"].add(sheet_name)
            if not clauses[bc]["block_name"] and bn:
                clauses[bc]["block_name"] = bn
    # set → sorted list（JSON 可序列化）
    return [{**c, "sheets": sorted(c["sheets"])} for c in clauses.values()]
