#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_poc · 规则编排智能体（两个场景）
================================================================
场景① 初始生成 (generate)：名称 + 定义/规则(种子) + 测试集期望值，【无 Badcase/Trace】
      → 直接生成首版 BOM（召回画像 → 定义+规则）。
场景② 已跑优化 (optimize)：当前 BOM + Badcase(期望/抽取) + 准确率 + Trace(多样)
      → 诊断(5类归因，依赖 Trace) → 优化（召回画像 → 定义+规则）。

两场景都走"两步法"：召回画像(发散) → 抽取规则(收敛)，同一对话上下文连贯。
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
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL") or None          # 留空 → 用 SDK 默认端点
MODEL = os.getenv("LLM_MODEL") or "gpt-4o-mini"

SYS = (
    "你是资深合同语义 BOM 规则工程师，精通合同要素抽取与 RAG 召回。"
    "你将分两个阶段工作：先发散（召回画像），再收敛（语义定义 + 抽取规则）。"
    "每个阶段【只输出一个合法 JSON 对象】，不要任何额外文字，不要 ``` 代码块标记。"
)


def parse_json(raw: str) -> dict:
    """容错解析：去代码块围栏、截取首个 {...}。"""
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        s = s[i:j + 1]
    return json.loads(s)


def call(client, messages):
    """调用大模型并解析为 JSON；失败则追加一次强约束重试。"""
    raw = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=0.3,
    ).choices[0].message.content
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
    return "\n".join(lines)


def fmt_cands(cands):
    cands = cands or []
    return "\n".join(f"  ({i}) {c}" for i, c in enumerate(cands, 1)) if cands else "  （未提供候选）"


# ===================== 场景②：优化（吃 Badcase，含诊断）=====================
def opt_stage1_user(d):
    return f"""【阶段 1：诊断与召回画像】
【目标条款】{d.get('clause', '')}
【当前语义定义与抽取规则（旧 BOM）】
{d.get('current_bom', '')}
【候选正例（来自测试集期望值）】
{fmt_cands(d.get('positive_candidates'))}
【测试集 Badcase 列表】
{fmt_badcases(d.get('badcases', []))}

任务：
1) 逐一归因每个 Badcase：漏抽/误抽分别是因为召回失败（缺关键词）、被规则误杀、缺易混淆词隔离，还是拦截不严？
2) 重构召回画像。positive_examples **必须从【候选正例】中挑选 3-5 条互相差异最大的**（禁止编造、禁止挑近义重复）。

只输出如下 JSON：
{{
  "diagnosis": [{{"case_id":"样本1","case_type":"miss|false_positive","category":"召回问题|混合问题|BOM问题|Prompt模板待优化|大模型推理问题","reason":"..."}}],
  "recall_profile": {{"positive_keywords":[],"confusion_words":[],"section_hints":[],"semantic_queries":[],"positive_examples":[]}}
}}"""


def opt_stage2_user(s1):
    return f"""【阶段 2：精炼语义定义与抽取规则】（基于阶段 1）
【阶段 1 诊断与召回画像】
{json.dumps(s1, ensure_ascii=False, indent=2)}

任务：彻底重构「语义定义」与「抽取规则」，修复所有 Badcase。
⚠️ 必须【提炼泛化特征】，禁止针对具体公司名/金额/人名写规则（防过拟合）。
只输出如下 JSON：
{{
  "semantic_definition": "...",
  "extraction_rules": {{"absolute_interception_rules":[{{"rule":"...","fixes":"针对哪个误抽"}}],"core_match_rules":[{{"rule":"...","fixes":"针对哪个漏抽"}}]}},
  "self_consistency_check": "新拦截+匹配规则能否解决所有 Badcase"
}}"""


# ===================== 场景①：初始生成（无 Badcase，纯生成）=====================
def gen_stage1_user(d):
    return f"""【阶段 1：召回画像生成（初始生成，尚无 Badcase）】
【目标条款】{d.get('clause', '')}
【已有定义/规则（种子，可简略）】
{d.get('current_bom', '（无）')}
【候选正例（来自测试集期望值）】
{fmt_cands(d.get('positive_candidates'))}

任务：构建该条款的召回画像。
- positive_examples **必须从【候选正例】中挑选 3-5 条互相差异最大的**（禁止编造、禁止挑近义重复）。
- positive_keywords / confusion_words / section_hints / semantic_queries 基于条款含义与候选推断。

只输出如下 JSON：
{{
  "recall_profile": {{"positive_keywords":[],"confusion_words":[],"section_hints":[],"semantic_queries":[],"positive_examples":[]}}
}}"""


def gen_stage2_user(s1):
    return f"""【阶段 2：语义定义 + 抽取规则（初始生成）】
【阶段 1 召回画像】
{json.dumps(s1, ensure_ascii=False, indent=2)}

任务：生成该条款的语义定义与抽取规则。
⚠️ 必须【提炼泛化特征】，禁止针对具体公司名/金额/人名写规则（防过拟合）。
- 绝对拦截规则：基于条款性质，预判常见误抽陷阱并拦截。
- 核心匹配规则：能覆盖候选正例多样性的提取条件。

只输出如下 JSON：
{{
  "semantic_definition": "...",
  "extraction_rules": {{"absolute_interception_rules":[{{"rule":"...","fixes":"针对哪类误抽陷阱"}}],"core_match_rules":[{{"rule":"...","fixes":"覆盖哪类正例"}}]}},
  "coverage_check": "定义+规则是否覆盖候选正例的多样性"
}}"""


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
        final["diagnosis"] = s1.get("diagnosis", [])   # 仅优化场景有诊断
    return final


def main():
    if not API_KEY:
        sys.exit("✗ 未读到 LLM_API_KEY，请先 cp .env.example .env 并填入。")

    p = argparse.ArgumentParser(description="规则编排智能体 PoC（generate 初始生成 / optimize 已跑优化）")
    p.add_argument("data", nargs="?", default=str(Path(__file__).parent / "data" / "sample_slice.yaml"))
    p.add_argument("--mode", choices=["generate", "optimize"], default="optimize",
                   help="generate=初始生成(无Badcase)；optimize=已跑优化(吃Badcase诊断)")
    args = p.parse_args()

    data = yaml.safe_load(Path(args.data).read_text(encoding="utf-8"))
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    print(f"→ 模型 {MODEL} | base_url: {BASE_URL or '(默认)'} | 场景: {args.mode}\n")

    final = run_pipeline(client, data, args.mode)
    print("\n=== 最终 BOM ===")
    print(json.dumps(final, ensure_ascii=False, indent=2))

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"new_bom_{args.mode}_{stamp}.json"
    out_file.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 已存档：{out_file}（拿去手工录入新/旧平台跑准确率）")


if __name__ == "__main__":
    main()
