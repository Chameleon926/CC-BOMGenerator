#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则编排智能体 · PoC
================================================================
验证核心假设：LLM 能否基于「旧 BOM 规则 + Badcase」归纳出更准的新规则。

KISS —— 只做"脑子"：
    组装 Meta-Prompt  →  调大模型  →  输出【归因 + 新 BOM】
不造"躯干"：抽取与准确率交给真实新/旧平台手工跑（平台自带准确率）。

用法：
    python poc/run_rule_agent.py [切片数据.yaml]
    （默认读取 poc/data/sample_slice.yaml）
================================================================
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


def build_prompt(d: dict) -> str:
    """组装 Meta-Prompt：把黄金切片填进规则工程师指令。"""
    def block(items):
        return "\n".join(f"  ({i}) {x}" for i, x in enumerate(items, 1)) if items else "  （无）"

    return f"""你是一位资深法务科技工程师，精通合同语义分析与大模型抽取规则（语义 BOM）配置。
你的任务：分析当前「抽取规则」在真实数据上的错误（漏抽/误抽），归纳出更精准的新规则。

【目标条款】
{d.get('clause', '')}

【当前业务定义与规则（旧 BOM）】
{d.get('current_bom', '')}

【正例：当前规则已经抽对的合同原文】
{block(d.get('good_cases', []))}

【漏抽反例：本该抽出、却被拦截或未匹配的原文】
{block(d.get('miss_cases', []))}

【误抽反例：本不该抽出、却错误匹配的原文】
{block(d.get('false_cases', []))}

请完成两件事：

1) 错误归因诊断
   先判断主要错误类型（从以下 5 类中选，可多选并说明依据）：
   - 召回问题：原文根本没进入上下文窗口
   - 混合问题：召回与规则都参与了，归不到单层
   - BOM 问题：定义/规则有误（过严→漏抽，或过松→误抽）
   - Prompt 模板待优化：自动拼装的提示词模板有缺陷
   - 大模型推理问题：规则与召回都对，是模型自己推理错
   再简要说明：为什么当前规则会导致上述漏抽/误抽？

2) 提炼新规则（BOM 更新）
   ⚠️ 必须【提炼泛化特征】，禁止针对具体公司名/具体金额/具体人名写规则（防过拟合）。
     例：✅「初始付款方为供应商主体时拦截」 ❌「遇到 XX 公司就拦截」
   【新增正向关键词】（命中即倾向抽取）
   【新增易混淆词】（常导致误抽，需警惕）
   【新增/修改 绝对拦截规则】（一句话，命中即放弃；针对误抽反例）
   【新增/修改 核心匹配规则】（针对漏抽反例做条件豁免或放宽）

要求：输出业务人员能直接看懂的自然语言逻辑；不要代码、不要正则。"""


def main():
    if not API_KEY:
        sys.exit("✗ 未读到 LLM_API_KEY。请先 cp .env.example .env 并填入 api-key/base_url/model。")

    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data" / "sample_slice.yaml"
    if not data_path.exists():
        sys.exit(f"✗ 找不到切片数据：{data_path}")

    data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    prompt = build_prompt(data)

    print(f"→ 模型: {MODEL}  | base_url: {BASE_URL or '(默认)'}\n")
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)  # OpenAI 兼容接口，可接任意端点
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    out = resp.choices[0].message.content.strip()

    print("=" * 60)
    print(out)
    print("=" * 60)

    # 存档，便于手工配置进平台
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"new_bom_{stamp}.md"
    out_file.write_text(out, encoding="utf-8")
    print(f"\n✓ 已存档：{out_file}（拿去手工配置进新/旧平台跑准确率）")


if __name__ == "__main__":
    main()
