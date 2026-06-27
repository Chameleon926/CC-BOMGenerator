#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_poc · 规则编排智能体（两个场景）
================================================================
场景① 初始生成 (generate)：名称 + 定义/规则(种子) + 测试集期望值，【无 Badcase/Trace】
场景② 已跑优化 (optimize)：当前 BOM + Badcase(期望/抽取) + Trace(输入/输出)

两场景都走"两步法"：召回画像(发散) → 抽取规则(收敛)，同一对话上下文连贯。
场景② 的诊断会吃【结构化 Trace】（trace_parser 解析），做覆盖率缺口 + 边界规则冲突诊断
（阈值固定 80%，靠让模型抽得更完整来达标）。
提示词与代码分离：prompt 在 prompts/（纯文本 + {{var}} 占位）。模型配置见根目录 .env。
================================================================
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from trace_parser import TraceError, extract_structured, load_trace

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL") or None          # 留空 → 用 SDK 默认端点
MODEL = os.getenv("LLM_MODEL") or "gpt-4o-mini"


def load_prompt(name):
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def render(tpl, **kw):
    def sub(m):
        k = m.group(1).strip()
        return str(kw.get(k, m.group(0)))
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, tpl)


SYS = load_prompt("system")


def parse_json(raw):
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    return json.loads(s)


def call(client, messages):
    raw = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.3).choices[0].message.content
    try:
        return parse_json(raw), raw
    except Exception:
        msgs = messages + [{"role": "user",
                            "content": "上一次输出无法解析为 JSON。请只返回一个合法 JSON 对象，不要任何额外文字。"}]
        raw2 = client.chat.completions.create(model=MODEL, messages=msgs, temperature=0.2).choices[0].message.content
        return parse_json(raw2), raw2


def fmt_cands(cands):
    cands = cands or []
    return "\n".join(f"  ({i}) {c}" for i, c in enumerate(cands, 1)) if cands else "  （未提供候选）"


def fmt_badcases_rich(cases):
    """富 badcase：含结构化 trace 证据（覆盖率缺口诊断用）。"""
    lines = []
    for c in cases:
        lines.append(f"  - {c.get('id', '?')}（{c.get('type', '?')}）：期望=[{c.get('expected', '')}] 实际=[{c.get('actual', '')}]"
                     + (f" 覆盖率/相似度=[{c.get('similarity')}]" if c.get("similarity") else ""))
        lines.append(f"      原文：{c.get('text', '')}")
        t = c.get("_trace_struct")
        if t:
            lines.append(f"      [Trace] 当前规则/画像：{(t.get('current_rules_profile') or '')[:1200]}")
            lines.append(f"      [Trace] 合同原文窗口：{(t.get('context_window') or '（未提取到窗口）')[:1500]}")
            lines.append(f"      [Trace] 模型抽取：{t.get('model_extracted', '（无）')}")
            lines.append(f"      [Trace] 模型 reasoning：{t.get('model_reasoning', '（无）')}")
            if t.get("chunks"):
                lines.append("      [Trace] 可用 chunks：" + "; ".join(
                    f"{ch.get('chunkId', '')}@{ch.get('section') or ''}" for ch in t["chunks"][:6]))
        else:
            lines.append("      [Trace] （未提供；只能判误抽/漏抽，类别低置信猜测）")
    return "\n".join(lines)


def load_badcase_trace(c, base_dir):
    """按 badcase 的 trace 引用加载结构化 trace；无引用返回 None；解析失败抛 TraceError。"""
    inp_p, out_p, comb = c.get("trace_input"), c.get("trace_output"), c.get("trace")
    if not (inp_p or out_p or comb):
        return None

    def resolve(p):
        p = Path(p)
        return p if p.is_absolute() else (base_dir / p)

    inp, out = load_trace(
        input_path=resolve(inp_p) if inp_p else None,
        output_path=resolve(out_p) if out_p else None,
        combined_path=resolve(comb) if comb else None,
    )
    return extract_structured(inp, out) if (inp or out) else None


def recall_rules(d):
    hint = str(d.get("language_hint", "") or "").strip()
    lang = (f"语言要求：{hint}。" if hint
            else "中文为主；若输入文本含英文（尤其英文占比高），按比例补充英文短词。")
    return render(load_prompt("recall"),
                  nkw=d.get("keyword_count", 10), nsec=d.get("section_count", 6),
                  nq=d.get("query_count", 3), lang=lang)


# ===== 场景②：优化（吃 Badcase + Trace，覆盖率缺口诊断）=====
def opt_stage1_user(d):
    return render(load_prompt("opt_stage1"),
                  clause=d.get("clause", ""), block_code=d.get("block_code", ""),
                  current_bom=d.get("current_bom", ""),
                  cands=fmt_cands(d.get("positive_candidates")),
                  badcases=fmt_badcases_rich(d.get("badcases", [])),
                  recall_rules=recall_rules(d))


def opt_stage2_user(s1):
    return render(load_prompt("opt_stage2"), stage1_json=json.dumps(s1, ensure_ascii=False, indent=2))


# ===== 场景①：初始生成（无 Badcase，纯生成）=====
def gen_stage1_user(d):
    return render(load_prompt("gen_stage1"),
                  clause=d.get("clause", ""), current_bom=d.get("current_bom", "（无）"),
                  cands=fmt_cands(d.get("positive_candidates")),
                  recall_rules=recall_rules(d))


def gen_stage2_user(s1):
    return render(load_prompt("gen_stage2"), stage1_json=json.dumps(s1, ensure_ascii=False, indent=2))


def run_pipeline(client, data, mode, base_dir):
    if mode == "optimize":
        for c in (data.get("badcases") or []):
            c["_trace_struct"] = load_badcase_trace(c, base_dir)  # 解析失败会抛 TraceError

    msgs = [{"role": "system", "content": SYS}]
    s1_user = gen_stage1_user if mode == "generate" else opt_stage1_user
    s2_user = gen_stage2_user if mode == "generate" else opt_stage2_user

    print(f"=== [{mode}] Stage 1：召回画像{'生成' if mode == 'generate' else ' + 诊断'} ===")
    msgs.append({"role": "user", "content": s1_user(data)})
    s1, raw1 = call(client, msgs)
    msgs.append({"role": "assistant", "content": raw1})
    print(json.dumps(s1, ensure_ascii=False, indent=2))

    print(f"\n=== [{mode}] Stage 2：定义 + 抽取规则 ===")
    msgs.append({"role": "user", "content": s2_user(s1)})
    s2, _ = call(client, msgs)
    print(json.dumps(s2, ensure_ascii=False, indent=2))

    final = {
        "mode": mode,
        "clause": data.get("clause", ""),
        "block_code": data.get("block_code", ""),
        "semantic_definition": s2.get("semantic_definition", ""),
        "recall_profile": s1.get("recall_profile", {}),
        "extraction_rules": s2.get("extraction_rules", {}),
    }
    if mode == "optimize":
        final["diagnosis"] = s1.get("diagnosis", [])
    return final


def run_one(client, data_path, mode_override):
    data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    mode = mode_override or data.get("mode") or "optimize"
    print(f"→ {data_path.name} | 模型 {MODEL} | base_url: {BASE_URL or '(默认)'} | 场景: {mode}\n")
    try:
        final = run_pipeline(client, data, mode, data_path.parent)
    except TraceError as e:
        print(f"\n✗ Trace 解析失败，已跳过 {data_path.name}：\n{e}\n")
        return
    print("\n=== 最终 BOM ===")
    print(json.dumps(final, ensure_ascii=False, indent=2))
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w一-龥]+", "_", data_path.stem).strip("_") or "bom"
    out_file = out_dir / f"{safe_name}_{mode}_{stamp}.json"
    out_file.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 已存档：{out_file}（拿去手工录入新/旧平台跑准确率）\n")


def main():
    if not API_KEY:
        sys.exit("✗ 未读到 LLM_API_KEY，请先 cp .env.example .env 并填入。")

    p = argparse.ArgumentParser(description="规则编排智能体 PoC（generate/optimize；支持单文件或目录批量）")
    p.add_argument("data", nargs="?", default=str(Path(__file__).parent / "data" / "sample_slice.yaml"),
                   help="yaml 文件，或目录（批量跑其中所有 *.yaml）")
    p.add_argument("--mode", choices=["generate", "optimize"], default=None,
                   help="覆盖 yaml 内的 mode；不填则用 yaml 的 mode 字段，再缺省 optimize")
    args = p.parse_args()

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    target = Path(args.data)
    if target.is_dir():
        yamls = sorted(target.glob("*.yaml"))
        print(f"========== 批量模式：{len(yamls)} 个 yaml ==========\n")
        for y in yamls:
            print(f"##### {y.name} #####")
            run_one(client, y, args.mode)
    else:
        run_one(client, target, args.mode)


if __name__ == "__main__":
    main()
