#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quick_poc · Trace 解析器
================================================================
从新平台 trace 解析诊断需要的关键字段；格式错误时报【具体原因 + 行号附近 + 来源】。

支持三种读法：
  - 两文件（输入/输出分开）：load_trace(input_path=..., output_path=...)
  - 合并文件（含 "输入:"/"输出:" 标记）：load_trace(combined_path=...)
  - 只给 input 或 output 也行

抽出字段（喂给诊断 prompt）：
  block_code/block_name、可用 chunks、当前规则+画像、合同原文窗口、
  模型抽取 blockText + reasoning + confidence
================================================================
"""
import json
import re
from pathlib import Path


class TraceError(Exception):
    """带位置（行/列/附近/来源）的 trace 解析错误。"""

    def __init__(self, msg, lineno=None, col=None, near=None, source=None):
        self.lineno, self.col, self.near, self.source = lineno, col, near, source
        where = source or "trace"
        loc = f" 第 {lineno} 行" + (f" 第 {col} 列" if col else "") if lineno else ""
        near_s = f"\n附近内容：\n{near}" if near else ""
        super().__init__(f"[{where}]{loc} {msg}{near_s}")


def _find_json_block(text):
    """抠出第一个 { ... } 块；返回 (block_text, block_start_line)。"""
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return None, None
    return text[i:j + 1], text.count("\n", 0, i) + 1


def _parse_json(text, source):
    block, start_line = _find_json_block(text)
    if block is None:
        raise TraceError("未找到 JSON 对象（缺少 { ... }）", source=source,
                         near=(text[:200] + "…") if text.strip() else "（文件为空）")
    try:
        return json.loads(block)
    except json.JSONDecodeError as e:
        real_line = (start_line + e.lineno - 1) if start_line else e.lineno  # 块内行号→原文件行号
        lines = block.splitlines()
        ctx = []
        for k in range(max(0, e.lineno - 2), min(len(lines), e.lineno + 1)):
            ctx.append(f"{start_line + k:>5} | {lines[k]}")
        raise TraceError(f"JSON 解析失败：{e.msg}", lineno=real_line, col=e.colno,
                         near=("\n".join(ctx) if ctx else None), source=source)


def _split_combined(text):
    """合并文件按 '输入:'/'输出:' 标记拆分；返回 (input_text, output_text)。"""
    m_in = re.search(r"(?im)^[>\s#*]*输入\s*[:：]", text)
    m_out = re.search(r"(?im)^[>\s#*]*输出\s*[:：]", text)
    if m_in and m_out and m_in.start() < m_out.start():
        return text[m_in.end():m_out.start()], text[m_out.end():]
    if m_in:
        return text[m_in.end():], None
    if m_out:
        return None, text[m_out.end():]
    return None, None


def load_trace(input_path=None, output_path=None, combined_path=None):
    """加载并解析 trace，返回 (input_json, output_json)；缺的为 None。"""
    inp = out = None
    if combined_path:
        text = Path(combined_path).read_text(encoding="utf-8")
        i_text, o_text = _split_combined(text)
        if i_text is None and o_text is None:   # 没标记 → 整文件当 input
            i_text = text
        if i_text and i_text.strip():
            inp = _parse_json(i_text, f"{combined_path}（输入）")
        if o_text and o_text.strip():
            out = _parse_json(o_text, f"{combined_path}（输出）")
    else:
        if input_path:
            inp = _parse_json(Path(input_path).read_text(encoding="utf-8"), f"{input_path}（输入）")
        if output_path:
            out = _parse_json(Path(output_path).read_text(encoding="utf-8"), f"{output_path}（输出）")
    return inp, out


def _section(text, start_marker, end_marker):
    i = text.find(start_marker)
    if i < 0:
        return None
    j = text.find(end_marker, i + len(start_marker))
    return text[i:j] if j > i else text[i:]


def _find_reasoning(o):
    """递归在（可能是多层字符串化的）JSON 里找 reasoning 字段。"""
    if isinstance(o, dict):
        if "reasoning" in o and o["reasoning"]:
            return o["reasoning"]
        for v in o.values():
            r = _find_reasoning(v)
            if r:
                return r
    elif isinstance(o, str):
        try:
            return _find_reasoning(json.loads(o))
        except Exception:
            return None
    return None


def extract_structured(inp, out):
    """从 input/output JSON 抽诊断关键字段（控长度）。"""
    res = {}
    if inp:
        nt = inp.get("normalizedTarget") or {}
        res["block_code"] = nt.get("blockCode")
        res["block_name"] = nt.get("blockName")
        res["chunks"] = [
            {"chunkId": c.get("chunkId"), "section": c.get("sectionPathText"),
             "snippet": (c.get("text") or "")[:160]}
            for c in (inp.get("_fallback_chunks") or [])[:8]
        ]
        prompt = ((inp.get("perWindowPrompts") or [{}])[0]).get("prompt", "")
        res["current_rules_profile"] = (
            _section(prompt, "目标定义", "--- 合同原文窗口 ---")
            or _section(prompt, "目标定义", "--- 输出格式 ---")
            or prompt[:1500]
        )
        res["context_window"] = _section(prompt, "--- 合同原文窗口 ---", "--- 输出格式 ---")
    if out:
        bers = out.get("blockExtractionResults") or []
        if bers:
            b = bers[0]
            res["model_extracted"] = (b.get("blockText") or "")[:800]
            res["model_reasoning"] = (b.get("reasoning") or _find_reasoning(out) or "")[:400]
            res["model_confidence"] = b.get("llmConfidence") or b.get("confidence")
    return res
