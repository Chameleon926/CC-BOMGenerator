"""
B 模块第 4 步：规则自检（用大模型，温度 0.0）

输入：
- 完整 BOM（定义 + 规则 + 画像）
- 正例列表（期望值）
- 误抽反例（可选，生成场景一般没有）

输出：
- Verification（逐条验证 + 红旗 + 覆盖估计 + 结论）

准确率保障逻辑：
- 验证正例能否被匹配规则命中（命中不了=漏抽风险）
- 验证正例是否被拦截规则误杀（误杀=规则矛盾）
- 验证反例能否被拦截规则挡住（挡不住=误抽风险）
- 检测规则是否过拟合（写死公司名/金额）
"""

from __future__ import annotations

import json
from typing import List

from ..contracts.bom import BOM
from ..contracts.diagnosis import Verification
from ..llm.client import call_json, render_prompt


def verify_bom(
    bom: BOM,
    positive_examples: List[str],
    negative_examples: List[str] | None = None,
) -> Verification:
    """
    调大模型对 BOM 做规则自检。

    Args:
        bom: 完整 BOM（定义 + 规则 + 画像）
        positive_examples: 正例列表（期望值，验证能否被正确抽出）
        negative_examples: 误抽反例（验证能否被拦截，可选）

    Returns:
        Verification 契约（逐条验证 + 红旗 + 覆盖估计 + 结论）
    """
    # ---- 准备大模型输入 ----
    bom_dict = bom.model_dump(mode="json")  # mode="json" 自动把 datetime 转 ISO 字符串
    bom_json = json.dumps(bom_dict, ensure_ascii=False, indent=2)

    positives_text = _format_list(positive_examples, "正例")

    negatives_text = _format_list(negative_examples or [], "误抽反例")
    if not negative_examples:
        negatives_text = "（无，本次为生成场景，暂无误抽反例）"

    # ---- 渲染提示词 ----
    user_prompt = render_prompt(
        "verify",
        bom_json=bom_json,
        positives=positives_text,
        negatives=negatives_text,
    )

    system_prompt = render_prompt("system")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # ---- 调大模型（温度 0.0，最确定性）----
    result = call_json(messages, temperature=0.0)

    # ---- 解析结果 ----
    verification = Verification(
        checks=result.get("checks", []),
        red_flags=result.get("red_flags", []),
        coverage_estimate=result.get("coverage_estimate", ""),
        summary=result.get("summary", ""),
    )

    return verification


def has_blocking_issues(verification: Verification) -> bool:
    """
    判断自检结果是否有阻塞性问题（有 fail verdict 或有红旗）。

    业务可以用这个函数判断是否需要人工介入。
    """
    if verification.red_flags:
        return True
    for check in verification.checks:
        verdict = check.get("verdict", "") if isinstance(check, dict) else ""
        if verdict == "fail":
            return True
    return False


# ==================== 内部函数 ====================

def _format_list(items: List[str], label: str = "") -> str:
    """格式化列表文本。"""
    if not items:
        return f"（无{label}）"
    prefix = f"{label}：" if label else ""
    lines = [f"{prefix}"]
    for i, item in enumerate(items, 1):
        lines.append(f"  ({i}) {item}")
    return "\n".join(lines)
