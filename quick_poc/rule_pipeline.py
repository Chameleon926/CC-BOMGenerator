#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_poc · 规则编排智能体（两阶段，与平台逻辑对齐：定义+规则 → 召回画像）
================================================================
场景① generate：名称 + 种子 + 期望值（无 Badcase）→ 首版 BOM
场景② optimize：当前 BOM + Badcase(期望/抽取) + Trace → 优化 BOM + 诊断

两阶段（翻转后，匹配平台"先定义规则、再派生画像"）：
  Stage 1：语义定义 + 抽取规则（optimize 另含 diagnosis[fix_target]）   [收敛，低温]
  Stage 2：召回画像（从 Stage 1 派生）                                   [发散，中温]
- 提示词结构化(XML标签)+各阶段独立角色，在 prompts/。
- positive_keywords 生成后程序化过滤（去数字/超长/整句，防过拟合）。
- 默认只生成提示词（PoC）；--api 调模型；--combine 合并两段返回为可读 BOM。
================================================================
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

from dedup import near_dedup, near_dedup_report
from trace_parser import TraceError, extract_structured, load_trace

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
CFG_PATH = ROOT / "config" / "llm.yaml"


def _load_llm_config():
    if not CFG_PATH.exists():
        return {}
    return yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}


_CFG = _load_llm_config()
API_KEY = str(_CFG.get("api_key") or "").strip()
BASE_URL = str(_CFG.get("base_url") or "").strip() or None
MODEL = str(_CFG.get("model") or "").strip()
TEMP_S1 = float(_CFG.get("temperature_stage1", 0.2))   # Stage1 定义+规则：收敛低温
TEMP_S2 = float(_CFG.get("temperature_stage2", 0.5))   # Stage2 召回画像：发散中温


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


def call(client, messages, temperature):
    raw = client.chat.completions.create(model=MODEL, messages=messages, temperature=temperature).choices[0].message.content
    try:
        return parse_json(raw), raw
    except Exception:
        msgs = messages + [{"role": "user",
                            "content": "上一次输出无法解析为 JSON。请只返回一个合法 JSON 对象，不要任何额外文字。"}]
        raw2 = client.chat.completions.create(model=MODEL, messages=msgs, temperature=max(0.0, temperature - 0.1)).choices[0].message.content
        return parse_json(raw2), raw2


def fmt_cands(cands):
    cands = cands or []
    return "\n".join(f"  ({i}) {c}" for i, c in enumerate(cands, 1)) if cands else "  （未提供候选）"


_TRACE_FIELDS = [
    ("current_rules", "当前规则/画像", "current_rules_profile", 1200),
    ("context_window", "合同原文窗口", "context_window", 1500),
    ("model_extracted", "模型抽取", "model_extracted", 800),
    ("reasoning", "模型 reasoning", "model_reasoning", 400),
]
ALL_TRACE_FIELDS = [f[0] for f in _TRACE_FIELDS] + ["chunks"]


def fmt_badcases_rich(cases, fields=None):
    sel = set(fields) if fields else set(ALL_TRACE_FIELDS)
    show_chunks = "chunks" in sel
    lines = []
    for c in cases:
        lines.append(f"  - {c.get('id', '?')}（{c.get('type', '?')}）：期望=[{c.get('expected', '')}] 实际=[{c.get('actual', '')}]"
                     + (f" 覆盖率/相似度=[{c.get('similarity')}]" if c.get("similarity") else ""))
        lines.append(f"      原文：{c.get('text', '')}")
        t = c.get("_trace_struct")
        if not t:
            lines.append("      [Trace] （未提供；只能判误抽/漏抽，类别低置信猜测）")
            continue
        for key, label, dkey, n in _TRACE_FIELDS:
            if key not in sel:
                continue
            val = (t.get(dkey) or "（无）")
            if len(val) > n:
                val = val[:n] + "…"
            lines.append(f"      [Trace] {label}：{val}")
        if show_chunks and t.get("chunks"):
            lines.append("      [Trace] 可用 chunks：" + "; ".join(
                f"{ch.get('chunkId', '')}@{ch.get('section') or ''}" for ch in t["chunks"][:6]))
    return "\n".join(lines)


def load_badcase_trace(c, base_dir):
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


def recall_params(d):
    hint = str(d.get("language_hint", "") or "").strip()
    lang = (f"语言要求：{hint}。" if hint
            else "中文为主；若输入文本含英文（尤其英文占比高），按比例补充英文短词。")
    return {"nkw": d.get("keyword_count", 10), "nsec": d.get("section_count", 6),
            "nq": d.get("query_count", 3), "lang": lang}


def sanitize_keywords(kws):
    """过滤过拟合关键词：含数字/整句标点/超长的一律丢。"""
    out, seen = [], set()
    for kw in (kws or []):
        s = str(kw).strip()
        if not s or s in seen:
            continue
        cn = sum(1 for c in s if "一" <= c <= "鿿")
        if re.search(r"\d", s):                       # 含数字/金额/百分比 → 过拟合
            continue
        if re.search(r"[，,；;。.!！？?]", s):         # 整句标点
            continue
        if cn > 8 or len(s) > 12:                     # 太长
            continue
        seen.add(s)
        out.append(s)
    return out


# ===== Stage 1：语义定义 + 抽取规则（optimize 含诊断）=====
def gen_stage1_user(d):
    return render(load_prompt("gen_stage1"),
                  clause=d.get("clause", ""), current_bom=d.get("current_bom", "（无）"),
                  cands=fmt_cands(d.get("positive_candidates")))


def opt_stage1_user(d):
    return render(load_prompt("opt_stage1"),
                  clause=d.get("clause", ""), block_code=d.get("block_code", ""),
                  current_bom=d.get("current_bom", ""),
                  cands=fmt_cands(d.get("positive_candidates")),
                  badcases=fmt_badcases_rich(d.get("badcases", []), d.get("trace_fields")))


# ===== Stage 2：召回画像（从 Stage 1 派生）=====
def gen_stage2_user(s1, d):
    return render(load_prompt("gen_stage2"),
                  stage1_json=json.dumps(s1, ensure_ascii=False, indent=2),
                  cands=fmt_cands(d.get("positive_candidates")), **recall_params(d))


def opt_stage2_user(s1, d):
    return render(load_prompt("opt_stage2"),
                  stage1_json=json.dumps(s1, ensure_ascii=False, indent=2),
                  cands=fmt_cands(d.get("positive_candidates")), **recall_params(d))


def run_pipeline(client, data, mode):
    msgs = [{"role": "system", "content": SYS}]
    s1_user = gen_stage1_user if mode == "generate" else opt_stage1_user
    s2_user = gen_stage2_user if mode == "generate" else opt_stage2_user

    print(f"=== [{mode}] Stage 1：语义定义 + 抽取规则{'（+诊断）' if mode == 'optimize' else ''} ===")
    msgs.append({"role": "user", "content": s1_user(data)})
    s1, raw1 = call(client, msgs, TEMP_S1)
    msgs.append({"role": "assistant", "content": raw1})
    print(json.dumps(s1, ensure_ascii=False, indent=2))

    print(f"\n=== [{mode}] Stage 2：召回画像（派生自 Stage 1）===")
    msgs.append({"role": "user", "content": s2_user(s1, data)})
    s2, _ = call(client, msgs, TEMP_S2)
    print(json.dumps(s2, ensure_ascii=False, indent=2))

    rp = s2.get("recall_profile", {}) or {}
    before = rp.get("positive_keywords", []) or []
    rp["positive_keywords"] = sanitize_keywords(before)
    if len(rp["positive_keywords"]) < len(before):
        print(f"  ℹ 关键词过滤：{len(before)} → {len(rp['positive_keywords'])}（去掉含数字/超长/整句的过拟合项）")

    final = {
        "mode": mode, "clause": data.get("clause", ""), "block_code": data.get("block_code", ""),
        "semantic_definition": s1.get("semantic_definition", ""),
        "extraction_rules": s1.get("extraction_rules", {}),
        "recall_profile": rp,
    }
    if mode == "optimize":
        final["diagnosis"] = s1.get("diagnosis", [])

    print(f"\n=== [{mode}] Stage 3：规则自检（提前抓矛盾/过拟合/漏覆盖）===")
    negatives = [c for c in (data.get("badcases") or []) if c.get("type") == "false_positive"] if mode == "optimize" else []
    verify_user = render(load_prompt("verify"),
                         bom_json=json.dumps(final, ensure_ascii=False, indent=2),
                         positives=fmt_cands(data.get("positive_candidates")),
                         negatives=(fmt_badcases_rich(negatives) if negatives else "（无）"))
    s3, _ = call(client, [{"role": "system", "content": SYS}, {"role": "user", "content": verify_user}], 0.0)
    print(json.dumps(s3, ensure_ascii=False, indent=2))
    final["verification"] = s3
    return final


def render_readable(bom):
    L = [f"【条款】{bom.get('clause', '')}（{bom.get('block_code', '')}）\n",
         "【业务定义】", (bom.get("semantic_definition") or "（无）").strip() + "\n",
         "【抽取规则】", "🛑 绝对拦截规则（命中即放弃，针对误抽）："]
    inter = (bom.get("extraction_rules") or {}).get("absolute_interception_rules") or []
    L += [f"  {i}. {r.get('rule', '')}   —— {r.get('fixes', '')}" for i, r in enumerate(inter, 1)] if inter else ["  （无）"]
    L.append("✅ 核心匹配规则（提取条件，针对漏抽）：")
    core = (bom.get("extraction_rules") or {}).get("core_match_rules") or []
    L += [f"  {i}. {r.get('rule', '')}   —— {r.get('fixes', '')}" for i, r in enumerate(core, 1)] if core else ["  （无）"]
    L.append("")
    rp = bom.get("recall_profile") or {}
    L += ["【召回画像】",
          f"- 正向关键词：{', '.join(rp.get('positive_keywords') or []) or '（无）'}",
          f"- 易混淆词：{', '.join(rp.get('confusion_words') or []) or '（无）'}",
          f"- 章节提示：{', '.join(rp.get('section_hints') or []) or '（无）'}",
          "- 语义查询（向量召回用）："]
    sq = rp.get("semantic_queries") or []
    L += [f"    · {q}" for q in sq] if sq else ["    （无）"]
    L.append("- 正例参考：")
    pe = rp.get("positive_examples") or []
    L += [f"    · {p}" for p in pe] if pe else ["    （无）"]
    if bom.get("diagnosis"):
        L.append("\n【Badcase 诊断】（仅 optimize）")
        for d in bom["diagnosis"]:
            tgt = d.get("fix_target", "")
            L += [f"- {d.get('case_id', '')}（{d.get('case_type', '')}）[{d.get('category', '')}]" + (f" →修{tgt}" if tgt else ""),
                  f"    根因：{d.get('reason', '')}",
                  f"    建议修法：{d.get('suggested_fix', '')}"]
    v = bom.get("verification")
    if v:
        L.append("\n【规则自检】")
        L.append(f"结论：{v.get('summary', '')}")
        L.append(f"覆盖估计：{v.get('coverage_estimate', '')}")
        rf = v.get("red_flags") or []
        if rf:
            L.append("🚩 红旗（建议修复）：")
            L += [f"  - {r}" for r in rf]
        else:
            L.append("✓ 无红旗")
    return "\n".join(L)


def combine_and_render(paths, mode_override):
    """外网返回的 Stage1(定义+规则[+诊断]) + Stage2(召回画像) → 合并为最终 BOM 并渲染可读版。"""
    yaml_p, s1_p, s2_p = paths
    data = yaml.safe_load(Path(yaml_p).read_text(encoding="utf-8"))
    mode = mode_override or data.get("mode") or "optimize"
    s1 = parse_json(Path(s1_p).read_text(encoding="utf-8"))   # Stage1：定义+规则(+诊断)
    s2 = parse_json(Path(s2_p).read_text(encoding="utf-8"))   # Stage2：召回画像
    rp = s2.get("recall_profile", {}) or {}
    rp["positive_keywords"] = sanitize_keywords(rp.get("positive_keywords"))
    final = {
        "mode": mode, "clause": data.get("clause", ""), "block_code": data.get("block_code", ""),
        "semantic_definition": s1.get("semantic_definition", ""),
        "extraction_rules": s1.get("extraction_rules", {}),
        "recall_profile": rp,
    }
    if mode == "optimize":
        final["diagnosis"] = s1.get("diagnosis", [])
    print("\n=== 业务可读 BOM ===")
    print(render_readable(final))
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    stem = re.sub(r"[^\w一-龥]+", "_", Path(yaml_p).stem).strip("_") or "bom"
    (out_dir / f"{stem}_BOM.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"{stem}_BOM_readable.md").write_text(render_readable(final), encoding="utf-8")
    print(f"\n✓ 已存：{out_dir / (stem + '_BOM.json')}（原始JSON）+ {stem}_BOM_readable.md（业务可读）")


def dedup_step(items, threshold=0.8):
    if not items:
        return []
    kept, dropped = near_dedup_report(items, threshold)
    if dropped:
        print(f"  ℹ 候选去重：{len(items)} 条 → 组装 {len(kept)} 条进提示词（去掉 {len(dropped)} 条近重复）")
        for d, m in dropped[:3]:
            print(f"     ✗ 去掉「{str(d)[:36]}…」（≈ 保留「{str(m)[:36]}…」）")
        if len(dropped) > 3:
            print(f"     …另有 {len(dropped) - 3} 条近重复被去掉")
    else:
        print(f"  ℹ 候选 {len(kept)} 条（无需去重），全部组装进提示词")
    return kept


def print_prompts(data, mode, data_path):
    """渲染并打印两阶段提示词（不调 API）。"""
    s1_user = gen_stage1_user if mode == "generate" else opt_stage1_user
    s1 = s1_user(data)
    s2 = render(load_prompt("gen_stage2" if mode == "generate" else "opt_stage2"),
                stage1_json="\n<<< 把 Stage 1 返回的 JSON 粘贴到这里 >>>\n",
                cands=fmt_cands(data.get("positive_candidates")), **recall_params(data))
    s3 = render(load_prompt("verify"),
                bom_json="\n<<< 把 Stage1+Stage2 合并后的完整 BOM JSON 粘贴到这里（第④步合并后再跑这步）>>>\n",
                positives=fmt_cands(data.get("positive_candidates")),
                negatives="（optimize：把误抽反例粘这里；generate：填'无'）")
    bar = "=" * 64
    print(f"\n{bar}\n【Stage 1 提示词：语义定义+抽取规则】复制到外网模型，拿回 JSON\n{bar}\n")
    print(s1)
    print(f"\n{bar}\n【Stage 2 提示词：召回画像】先把 Stage 1 的 JSON 粘到 <<<>>> 处，再发给模型\n{bar}\n")
    print(s2)
    print(f"\n{bar}\n【Stage 3 提示词：规则自检（可选，推荐）】把合并后的完整 BOM 粘到 <<<>>> 处，发给模型查矛盾\n{bar}\n")
    print(s3)
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    f = out_dir / f"{data_path.stem}_prompts.txt"
    f.write_text(f"===== Stage 1 提示词 =====\n{s1}\n\n===== Stage 2 提示词 =====\n{s2}\n\n"
                 f"===== Stage 3 提示词（自检，可选）=====\n{s3}\n", encoding="utf-8")
    print(f"\n✓ 三段提示词已存：{f}（方便整体复制）\n")


def run_one(client, data_path, mode_override, use_api):
    data = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    mode = mode_override or data.get("mode") or "optimize"

    print(f"→ {data_path.name} | 场景: {mode}")
    data["positive_candidates"] = dedup_step(data.get("positive_candidates") or [],
                                             data.get("dedup_threshold", 0.8))
    if mode == "optimize":
        try:
            for c in (data.get("badcases") or []):
                c["_trace_struct"] = load_badcase_trace(c, data_path.parent)
            print(f"  ℹ badcase {len(data.get('badcases') or [])} 条（trace 已加载）")
        except TraceError as e:
            print(f"\n✗ Trace 解析失败，已跳过 {data_path.name}：\n{e}\n")
            return

    if not use_api:
        print_prompts(data, mode, data_path)
        return

    print(f"  调模型 {MODEL} | base_url: {BASE_URL or '(默认)'}\n")
    final = run_pipeline(client, data, mode)
    print("\n=== 最终 BOM ===")
    print(render_readable(final))
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w一-龥]+", "_", data_path.stem).strip("_") or "bom"
    out_file = out_dir / f"{safe_name}_{mode}_{stamp}.json"
    out_file.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ 已存档：{out_file}\n")


def main():
    p = argparse.ArgumentParser(
        description="规则编排智能体 PoC（阶段：定义+规则 → 召回画像；默认生成提示词；--api 调模型；--combine 合并结果）")
    p.add_argument("data", nargs="?", default=str(Path(__file__).parent / "data" / "sample_slice.yaml"),
                   help="yaml 文件，或目录（批量）")
    p.add_argument("--mode", choices=["generate", "optimize"], default=None)
    p.add_argument("--api", action="store_true", help="调 config/llm.yaml 的模型（默认只生成提示词）")
    p.add_argument("--combine", nargs=3, metavar=("YAML", "STAGE1_JSON", "STAGE2_JSON"),
                   help="把外网返回的 Stage1/Stage2 JSON 合并成业务可读 BOM")
    args = p.parse_args()

    if args.combine:
        combine_and_render(args.combine, args.mode)
        return

    target = Path(args.data)
    files = sorted(target.glob("*.yaml")) if target.is_dir() else [target]

    client = None
    if args.api:
        missing = [n for n, v in (("api_key", API_KEY), ("model", MODEL)) if not v]
        if missing:
            sys.exit("✗ config/llm.yaml 未填写：" + "、".join(missing) + "。PoC 默认只生成提示词（不加 --api）；"
                     "如要自动调模型请填 config/llm.yaml。")
        from openai import OpenAI
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    if len(files) > 1:
        print(f"========== 共 {len(files)} 个 yaml ==========\n")
    for f in files:
        run_one(client, f, args.mode, args.api)


if __name__ == "__main__":
    main()
