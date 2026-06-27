#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_poc · 一步到位：选定 Excel + 模式 → 详细控制台输出 + 生成提示词。
================================================================
业务只需两步选：① 选 Excel ② 选模式（generate / optimize）。

  python quick_poc/run_excel.py 初始测试集.xlsx --mode generate
  python quick_poc/run_excel.py 跑批结果.xlsx   --mode optimize

PoC 默认【只生成提示词】（不调 API）：控制台逐条款打印
去重细节(哪些被去掉/组装多少) + Stage1/Stage2 提示词。
拿到外网模型返回的两段 JSON 后，用下面命令合并成业务可读 BOM：
  python quick_poc/rule_pipeline.py --combine <条款.yaml> <stage1.json> <stage2.json>

加 --api 则自动调 config/llm.yaml 的模型。
================================================================
"""
import argparse
import sys
from pathlib import Path

import yaml

import rule_pipeline as rp
from import_excel import COL_MAP, find_col, read_table, safe


def build_badcases(g, cols):
    """从跑批结果里圈出 badcase（是否匹配=否 优先，否则期望≠实际）。"""
    has_match, has_actual = bool(cols["match"]), bool(cols["actual_value"])

    def is_bad(r):
        if has_match:
            return str(r[cols["match"]]).strip().lower() in ("否", "no", "false", "0", "f", "未匹配", "不匹配")
        return has_actual and str(r[cols["expected_value"]]).strip() != str(r[cols["actual_value"]]).strip()

    bads = []
    for i, (_, r) in enumerate(g.iterrows()):
        if not is_bad(r):
            continue
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
    return bads


def main():
    ap = argparse.ArgumentParser(description="一步到位：Excel + 模式 → 提示词（PoC默认）/ 调模型(--api)")
    ap.add_argument("excel", help="测试集 / 跑批结果（xlsx 或 csv，中英列名均可）")
    ap.add_argument("--mode", choices=["generate", "optimize"], required=True,
                    help="generate=初始生成(只有期望值)；optimize=已跑优化(有实际值/是否匹配)")
    ap.add_argument("--api", action="store_true", help="调 config/llm.yaml 的模型（默认只生成提示词）")
    args = ap.parse_args()

    src = Path(args.excel)
    if not src.exists():
        sys.exit(f"✗ 找不到文件：{src}")
    df = read_table(src).fillna("")
    cols = {k: find_col(df, v) for k, v in COL_MAP.items()}
    if not cols["expected_value"]:
        sys.exit("✗ 找不到【期望值】列（expected_value / 期望值 / 期望结果）")
    if not (cols["block_name"] or cols["block_code"]):
        sys.exit("✗ 找不到【语义块】列（block_name / block_code / 语义块名称）")

    has_match, has_actual = bool(cols["match"]), bool(cols["actual_value"])
    if args.mode == "optimize" and not (has_match or has_actual):
        print("⚠ optimize 模式但 Excel 无 实际值/是否匹配 列 → 无 badcase（等同 generate）\n")
    if args.mode == "generate" and (has_match or has_actual):
        print("ℹ generate 模式：忽略 实际值/是否匹配 列，仅用期望值生成首版 BOM\n")

    print(f"========== Excel: {src.name} | 场景: {args.mode} | 行数 {len(df)} ==========\n")

    client = None
    if args.api:
        missing = [n for n, v in (("api_key", rp.API_KEY), ("model", rp.MODEL)) if not v]
        if missing:
            sys.exit("✗ config/llm.yaml 未填写：" + "、".join(missing) + "（或去掉 --api 只生成提示词）")
        from openai import OpenAI
        client = OpenAI(api_key=rp.API_KEY, base_url=rp.BASE_URL)

    key_col = cols["block_code"] or cols["block_name"]
    out_dir = Path(rp.__file__).parent / "data" / "imported"
    out_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    for key, g in df.groupby(key_col):
        name = (g[cols["block_name"]].iloc[0] if cols["block_name"] else key) or key
        code = (g[cols["block_code"]].iloc[0] if cols["block_code"] else "")
        print(f"##### 条款：{name}（{code}）— {len(g)} 行 #####")

        # 期望值候选：先精确去重，再近义去重（打印去掉哪些 / 组装多少）
        cands = list(dict.fromkeys(str(x).strip() for x in g[cols["expected_value"]] if str(x).strip()))
        cands = rp.dedup_step(cands, 0.8)

        data = {
            "mode": args.mode, "clause": str(name), "block_code": str(code),
            "current_bom": f"（由 {src.name} 导入；尚无既有规则）",
            "positive_candidates": cands,
            "keyword_count": 10, "section_count": 6, "query_count": 3,
        }
        if args.mode == "optimize":
            bads = build_badcases(g, cols)
            print(f"  ℹ badcase {len(bads)} 条（是否匹配=否 / 期望≠实际）")
            data["badcases"] = bads

        # 存 yaml（供后续 --combine 合并结果用）
        yf = out_dir / f"{safe(code or name)}.yaml"
        yf.write_text(f"# 由 run_excel 从 {src.name} 生成 | mode: {args.mode}\n"
                      + yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

        # 生成提示词（默认）或 调模型
        if args.api:
            print(f"  调模型 {rp.MODEL} ...")
            final = rp.run_pipeline(client, data, args.mode)
            print(rp.render_readable(final))
        else:
            rp.print_prompts(data, args.mode, yf)
        n += 1
        print()

    print(f"========== 完成：{n} 个条款 ==========")
    print("下一步：把每段的 Stage1/Stage2 提示词 copy 到外网模型，拿到两段 JSON 后合并成可读 BOM：")
    print("  python quick_poc/rule_pipeline.py --combine <条款.yaml> <stage1.json> <stage2.json>")


if __name__ == "__main__":
    main()
