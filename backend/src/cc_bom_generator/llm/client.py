"""
LLM 客户端

支持两种 API 格式：
- OpenAI 兼容（api_format: "openai" 或不填）
- Anthropic 兼容（api_format: "anthropic"）

配置从 config/llm.yaml 读取。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

# 项目根目录（backend/ 的上一级 = CC-BOMGenerator/）
# client.py 在 backend/src/cc_bom_generator/llm/client.py，往上 5 级
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CONFIG_PATH = _PROJECT_ROOT / "config" / "llm.yaml"
_PROMPTS_DIR = _PROJECT_ROOT / "prompts"

_config_cache: dict | None = None


def _load_config() -> dict:
    """读 config/llm.yaml（带缓存）"""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"找不到 {_CONFIG_PATH}，请执行 cp config/llm.example.yaml config/llm.yaml 并填写"
        )
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        _config_cache = yaml.safe_load(f) or {}
    return _config_cache


def get_api_format() -> str:
    """返回 API 格式: 'openai' 或 'anthropic'"""
    return _load_config().get("api_format", "openai")


def render_prompt(name: str, **kwargs: Any) -> str:
    """
    读 prompts/{name}.txt，填充 {{var}} 占位符。
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"找不到提示词文件: {path}")
    text = path.read_text(encoding="utf-8")

    def _replace(match):
        key = match.group(1).strip()
        if key in kwargs:
            return str(kwargs[key])
        return match.group(0)

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", _replace, text)


def call(
    messages: list[dict],
    temperature: float = 0.3,
) -> str:
    """
    调大模型，返回文本。自动判断 OpenAI / Anthropic 格式。

    Args:
        messages: OpenAI 格式的消息列表 [{"role": "...", "content": "..."}]
        temperature: 采样温度

    Returns:
        模型输出的文本
    """
    fmt = get_api_format()
    if fmt == "anthropic":
        return _call_anthropic(messages, temperature)
    else:
        return _call_openai(messages, temperature)


def call_json(
    messages: list[dict],
    temperature: float = 0.3,
    max_retries: int = 1,
) -> dict:
    """
    调大模型，返回 JSON 字典。解析失败自动重试。
    """
    for attempt in range(max_retries + 1):
        text = call(messages, temperature)
        try:
            return _parse_json(text)
        except (json.JSONDecodeError, ValueError):
            if attempt < max_retries:
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "上一次输出无法解析为 JSON。请只返回一个合法 JSON 对象，不要任何额外文字。"},
                ]
            else:
                raise ValueError(f"大模型输出无法解析为 JSON（重试 {max_retries} 次后仍失败）:\n{text[:500]}")


# ==================== OpenAI 兼容 ====================

def _call_openai(messages: list[dict], temperature: float) -> str:
    from openai import OpenAI
    cfg = _load_config()
    client = OpenAI(
        api_key=cfg.get("api_key", ""),
        base_url=cfg.get("base_url") or None,
    )
    resp = client.chat.completions.create(
        model=cfg.get("model", "gpt-4o-mini"),
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


# ==================== Anthropic 兼容 ====================

def _call_anthropic(messages: list[dict], temperature: float) -> str:
    """
    用 Anthropic SDK 调用。
    自动把 OpenAI 格式的 messages 转成 Anthropic 格式。
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("需要安装 anthropic SDK: pip install anthropic")

    cfg = _load_config()

    # 分离 system 消息和对话消息
    system_parts = []
    chat_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            chat_messages.append({"role": msg["role"], "content": msg["content"]})

    client = anthropic.Anthropic(
        api_key=cfg.get("api_key", ""),
        base_url=cfg.get("base_url"),
    )

    resp = client.messages.create(
        model=cfg.get("model", "claude-sonnet-4-20250514"),
        max_tokens=8192,
        temperature=temperature,
        system="\n\n".join(system_parts) if system_parts else None,
        messages=chat_messages,
    )
    # Anthropic 返回的是 content blocks
    return resp.content[0].text if resp.content else ""


# ==================== 工具 ====================

def _parse_json(text: str) -> dict:
    """容错 JSON 解析"""
    s = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        s = s[start : end + 1]
    return json.loads(s)
