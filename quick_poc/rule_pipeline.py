#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_poc · 两步法规则编排智能体（Recall_Agent → Rule_Agent）
================================================================
架构洞察：召回画像(发散) 与 抽取规则(收敛) 在认知上冲突，
故拆成两步、在【同一对话上下文】中连贯进行，避免模型逻辑混乱。

  Stage 1  Recall_Agent：逐条 Badcase 归因(5类) + 重构召回画像   → JSON
  Stage 2  Rule_Agent  ：基于 Stage1，精炼语义定义 + 抽取规则     → JSON
  Combine  最终新 BOM  ：definition + recall_profile + rules      → JSON（配进平台）

抽取与准确率仍交给真实新/旧平台手工跑（金标准）。
模型 api-key / base_url / model 见根目录 .env（base_url 留空=用默认端点）。
================================================================
"""
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
    "你将分两个阶段工作：先发散（归因 + 召回画像），再收敛（语义定义 + 抽取规则）。"
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


def stage1_user(d):
    return f"""【阶段 1：诊断与召回画像】
【目标条款】{d.get('clause', '')}
【当前语义定义与抽取规则（旧 BOM）】
{d.get('current_bom', '')}
【测试集 Badcase 列表】
{fmt_badcases(d.get('badcases', []))}

任务：
1) 逐一归因每个 Badcase：漏抽/误抽分别是因为召回失败（缺关键词）、被规则误杀、缺易混淆词隔离，还是拦截不严？
2) 重构召回画像。

只输出如下 JSON（字段不可少，数组可为空）：
{{
  "diagnosis": [
    {{"case_id":"样本1","case_type":"miss|false_positive","category":"召回问题|混合问题|BOM问题|Prompt模板待优化|大模型推理问题","reason":"..."}}
  ],
  "recall_profile": {{
    "positive_keywords": [],
    "confusion_words": [],
    "section_hints": [],
    "semantic_queries": [],
    "positive_examples": []
  }}
}}"""


def stage2_user(s1):
    return f"""【阶段 2：精炼语义定义与抽取规则】（基于你阶段 1 的结论）
【阶段 1 诊断与召回画像】
{json.dumps(s1, ensure_ascii=False, indent=2)}

任务：彻底重构「语义定义」与「抽取规则」，修复上面所有 Badcase。
⚠️ 必须【提炼泛化特征】，禁止针对具体公司名/金额/人名写规则（防过拟合）。
  - 绝对拦截规则：针对误抽场景，命中即输出空集。
  - 核心匹配规则：针对漏抽场景，放宽或豁免条件。

只输出如下 JSON：
{{
  "semantic_definition": "一段话界定该条款业务内涵（覆盖漏抽、排除误抽）",
  "extraction_rules": {{
    "absolute_interception_rules": [{{"rule":"...","fixes":"针对哪个误抽"}}],
    "core_match_rules": [{{"rule":"...","fixes":"针对哪个漏抽"}}]
  }},
  "self_consistency_check": "一句话说明新拦截+匹配规则能否解决所有 Badcase"
}}"""


def main():
    if not API_KEY:
        sys.exit("✗ 未读到 LLM_API_KEY，请先 cp .env.example .env 并填入。")

    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data" / "sample_slice.yaml"
    data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    print(f"→ 模型 {MODEL}  | base_url: {BASE_URL or '(默认)'}\n")
    msgs = [{"role": "system", "content": SYS}]

    # ---- Stage 1 ----
    print("=== Stage 1：诊断 + 召回画像 ===")
    msgs.append({"role": "user", "content": stage1_user(data)})
    s1, raw1 = call(client, msgs)
    msgs.append({"role": "assistant", "content": raw1})   # 纳入上下文，供 Stage 2 续用
    print(json.dumps(s1, ensure_ascii=False, indent=2))

    # ---- Stage 2（同一对话上下文）----
    print("\n=== Stage 2：定义 + 抽取规则 ===")
    msgs.append({"role": "user", "content": stage2_user(s1)})
    s2, _ = call(client, msgs)
    print(json.dumps(s2, ensure_ascii=False, indent=2))

    # ---- 合并最终 BOM ----
    final = {
        "clause": data.get("clause", ""),
        "semantic_definition": s2.get("semantic_definition", ""),
        "recall_profile": s1.get("recall_profile", {}),
        "extraction_rules": s2.get("extraction_rules", {}),
    }
    print("\n=== 最终新 BOM（配进平台）===")
    print(json.dumps(final, ensure_ascii=False, indent=2))

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"new_bom_{stamp}.json"
    out_file.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 已存档：{out_file}（拿去手工录入新/旧平台跑准确率）")


if __name__ == "__main__":
    main()
