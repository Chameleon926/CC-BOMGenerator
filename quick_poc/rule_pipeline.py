#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_poc · 规则编排智能体（两个场景）
================================================================
场景① 初始生成 (generate)：名称 + 定义/规则(种子) + 测试集期望值，【无 Badcase/Trace】
场景② 已跑优化 (optimize)：当前 BOM + Badcase(期望/抽取/Trace) + 准确率

两场景都走"两步法"：召回画像(发散) → 抽取规则(收敛)，同一对话上下文连贯。
【提示词与代码分离】所有 prompt 在 prompts/ 目录（纯文本 + {{var}} 占位），本文件只负责加载渲染。
召回画像数量/语言可在数据 yaml 配置（keyword_count/section_count/query_count/language_hint）。
抽取与准确率交给真实新/旧平台手工跑（金标准）。模型配置见根目录 .env。
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

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL") or None          # 留空 → 用 SDK 默认端点
MODEL = os.getenv("LLM_MODEL") or "gpt-4o-mini"


def load_prompt(name: str) -> str:
    """从 prompts/ 读取纯文本提示词模板。"""
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def render(tpl: str, **kw) -> str:
    """渲染 {{var}} 占位；未知占位原样保留（便于排查漏填）。"""
    def sub(m):
        k = m.group(1).strip()
        return str(kw.get(k, m.group(0)))
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", sub, tpl)


SYS = load_prompt("system")


def parse_json(raw: str) -> dict:
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


def fmt_badcases(cases):
    lines = []
    for c in cases:
        lines.append(f"  - {c.get('id', '?')}（{c.get('type', '?')}）：期望=[{c.get('expected', '')}] 实际=[{c.get('actual', '')}]")
        lines.append(f"      原文：{c.get('text', '')}")
        tr = str(c.get("trace", "") or "").strip()
        if tr:
            lines.append(f"      Trace：{tr}")
    return "\n".join(lines)


def fmt_cands(cands):
    cands = cands or []
    return "\n".join(f"  ({i}) {c}" for i, c in enumerate(cands, 1)) if cands else "  （未提供候选）"


def recall_rules(d):
    hint = str(d.get("language_hint", "") or "").strip()
    lang = (f"语言要求：{hint}。" if hint
            else "中文为主；若输入文本含英文（尤其英文占比高），按比例补充英文短词。")
    return render(load_prompt("recall"),
                  nkw=d.get("keyword_count", 10), nsec=d.get("section_count", 6),
                  nq=d.get("query_count", 3), lang=lang)


# ===== 场景②：优化（吃 Badcase + Trace，含诊断）=====
def opt_stage1_user(d):
    return render(load_prompt("opt_stage1"),
                  clause=d.get("clause", ""), current_bom=d.get("current_bom", ""),
                  cands=fmt_cands(d.get("positive_candidates")),
                  badcases=fmt_badcases(d.get("badcases", [])),
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


def run_pipeline(client, data, mode):
    msgs = [{"role": "system", "content": SYS}]
    s1_user = gen_stage1_user if mode == "generate" else opt_stage1_user
    s2_user = gen_stage2_user if mode == "generate" else opt_stage2_user

    print(f"=== [{mode}] Stage 1：召回画像{'生成' if mode == 'generate' else ' + 诊断'} ===")
    msgs.append({"role": "user", "content": s1_user(data)})
    s1, raw1 = call(client, msgs)
    msgs.append({"role": "assistant", "content": raw1})   # 纳入上下文供 Stage 2 续用
    print(json.dumps(s1, ensure_ascii=False, indent=2))

    print(f"\n=== [{mode}] Stage 2：定义 + 抽取规则 ===")
    msgs.append({"role": "user", "content": s2_user(s1)})
    s2, _ = call(client, msgs)
    print(json.dumps(s2, ensure_ascii=False, indent=2))

    final = {
        "mode": mode,
        "clause": data.get("clause", ""),
        "semantic_definition": s2.get("semantic_definition", ""),
        "recall_profile": s1.get("recall_profile", {}),
        "extraction_rules": s2.get("extraction_rules", {}),
    }
    if mode == "optimize":
        final["diagnosis"] = s1.get("diagnosis", [])
    return final


def run_one(client, data_path, mode_override):
    """跑单个 yaml：mode 优先用命令行覆盖，其次 yaml 内 mode 字段，再缺省 optimize。"""
    data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    mode = mode_override or data.get("mode") or "optimize"
    print(f"→ {data_path.name} | 模型 {MODEL} | base_url: {BASE_URL or '(默认)'} | 场景: {mode}\n")
    final = run_pipeline(client, data, mode)
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
