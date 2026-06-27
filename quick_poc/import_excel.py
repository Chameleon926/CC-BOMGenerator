#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_poc · Excel/CSV → yaml 批量导入器
================================================================
把测试集 Excel/CSV（中/英列名均可，xlsx/csv 均可）自动转成 quick_poc 的 yaml，
一个语义块(条款)一个 yaml，免去手填。

列名识别（大小写/空格无关，中英任一）：
  expected_value  期望值 / 期望结果              （必需）
  block_code      语义块编码 / 条款编码
  block_name      语义块名称 / 条款名称
  doc_id          文档ID / 文档编号
  doc_name        文档名称
  actual_value    抽取值 / 实际值                （可选；有→optimize，无→generate）
  text            合同原文 / 原文                 （可选；badcase 原文）

用法：
  python quick_poc/import_excel.py <测试集.xlsx|csv> [输出目录]
  # 默认输出到 quick_poc/data/imported/，然后批量跑：
  python quick_poc/rule_pipeline.py quick_poc/data/imported/
================================================================
"""
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

COL_MAP = {
    "doc_name": ["doc_name", "文档名称", "文档名"],
    "doc_id": ["doc_id", "文档id", "文档编号"],
    "block_code": ["block_code", "语义块编码", "语义块id", "条款编码"],
    "block_name": ["block_name", "语义块名称", "语义块名", "条款名称", "条款名"],
    "expected_value": ["expected_value", "期望值", "期望结果", "期望"],
    "actual_value": ["actual_value", "抽取值", "实际值", "实际结果", "抽取结果", "actual"],
    "match": ["是否匹配", "match", "匹配", "命中", "是否命中"],
    "similarity": ["相似度", "similarity", "相似", "覆盖率", "coverage"],
    "text": ["text", "合同原文", "原文", "doc_text", "片段", "content"],
}


def norm(s):
    return re.sub(r"\s+", "", str(s)).lower()


def find_col(df, keys):
    nmap = {norm(c): c for c in df.columns}
    for k in keys:
        if norm(k) in nmap:
            return nmap[norm(k)]
    return None


def safe(name):
    return re.sub(r"[^\w一-龥]+", "_", str(name)).strip("_") or "block"


def read_table(src: Path):
    """xlsx/xls 走 read_excel；csv 尝试常见中文编码。"""
    if src.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(src)
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return pd.read_csv(src, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(src)


def main():
    if len(sys.argv) < 2:
        sys.exit("用法：python quick_poc/import_excel.py <测试集.xlsx|csv> [输出目录]")
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "data" / "imported"
    if not src.exists():
        sys.exit(f"✗ 找不到文件：{src}")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = read_table(src).fillna("")
    cols = {k: find_col(df, v) for k, v in COL_MAP.items()}
    if not cols["expected_value"]:
        sys.exit("✗ 找不到【期望值】列（expected_value / 期望值 / 期望结果）")
    if not cols["block_name"] and not cols["block_code"]:
        sys.exit("✗ 找不到【语义块】列（block_name / block_code / 语义块名称）")

    has_actual = bool(cols["actual_value"])
    has_match = bool(cols["match"])
    key_col = cols["block_code"] or cols["block_name"]
    mode = "optimize" if (has_actual or has_match) else "generate"
    print(f"输入: {src.name} | 行数: {len(df)} | 场景: {mode}"
          f"（{'含抽取值/是否匹配→优化' if (has_actual or has_match) else '仅期望值→初始生成'}）\n")

    def _is_bad(r):
        # 优先用平台的「是否匹配」判定（覆盖率结论，比 expected≠actual 可靠：近似匹配也算「是」）
        if has_match:
            return str(r[cols["match"]]).strip().lower() in ("否", "no", "false", "0", "f", "未匹配", "不匹配")
        return str(r[cols["expected_value"]]).strip() != str(r[cols["actual_value"]]).strip()

    n = 0
    for key, g in df.groupby(key_col):
        name = (g[cols["block_name"]].iloc[0] if cols["block_name"] else key) or key
        code = (g[cols["block_code"]].iloc[0] if cols["block_code"] else "")
        expected = list(dict.fromkeys(str(x).strip() for x in g[cols["expected_value"]] if str(x).strip()))

        data = {
            "mode": mode,
            "clause": str(name),
            "block_code": str(code),
            "current_bom": f"（由 {src.name} 导入；block_code={code}；尚无既有规则）",
            "positive_candidates": expected,
            "keyword_count": 10,
            "section_count": 6,
            "query_count": 3,
        }

        bad_n = 0
        if mode == "optimize":
            bads = []
            for i, (_, r) in enumerate(g.iterrows()):
                if not _is_bad(r):
                    continue  # 抽对了（是否匹配=是），跳过
                exp = str(r[cols["expected_value"]]).strip()
                act = str(r[cols["actual_value"]]).strip() if has_actual else ""
                btype = "false_positive" if (not exp and act) else "miss"
                txt = str(r[cols["text"]]).strip() if cols["text"] else (exp or act)
                did = str(r[cols["doc_id"]]).strip() if cols["doc_id"] else "doc"
                bc = {"id": f"{did}_{i}", "type": btype, "expected": exp, "actual": act, "text": txt}
                if cols["similarity"]:
                    sim = str(r[cols["similarity"]]).strip()
                    if sim:
                        bc["similarity"] = sim
                bads.append(bc)
            data["badcases"] = bads
            bad_n = len(bads)

        fname = out_dir / f"{safe(code or name)}.yaml"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(f"# 自动导入自 {src.name} | 场景: {mode}（已写入 mode 字段，批量跑自动识别）\n")
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
        print(f"  ✓ {fname.name}   候选{len(expected)}  badcase{bad_n}")
        n += 1

    print(f"\n完成：{n} 个条款 yaml → {out_dir}")
    print("批量跑：python quick_poc/rule_pipeline.py " + str(out_dir).replace("\\", "/"))


if __name__ == "__main__":
    main()
