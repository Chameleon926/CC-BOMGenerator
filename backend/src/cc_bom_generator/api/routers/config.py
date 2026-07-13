"""/api 模型配置：读写 config/llm.yaml。"""

from __future__ import annotations

from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...llm.client import _CONFIG_PATH

router = APIRouter()


class ConfigModel(BaseModel):
    """模型配置。POST 时字段留空 = 不改。"""
    api_format: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None  # 留空=不改；填了=覆盖
    temperature_stage1: Optional[float] = None
    temperature_stage2: Optional[float] = None
    temperature_stage3: Optional[float] = None


def _mask_key(k: str) -> str:
    return (k[:4] + "..." + k[-4:]) if len(k) > 8 else "***"


def _clear_llm_cache() -> None:
    """清 llm.client 配置缓存，让后续 LLM 调用读到新配置。"""
    from ...llm import client as _c
    _c._config_cache = None


@router.get("/config")
def get_config():
    """读当前模型配置（api_key 脱敏返回）。"""
    if not _CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="config/llm.yaml 不存在")
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    api_key = cfg.get("api_key", "")
    return {
        "api_format": cfg.get("api_format", "openai"),
        "base_url": cfg.get("base_url", ""),
        "model": cfg.get("model", ""),
        "api_key_masked": _mask_key(api_key),
        "has_api_key": bool(api_key),
        "temperature_stage1": cfg.get("temperature_stage1", 0.2),
        "temperature_stage2": cfg.get("temperature_stage2", 0.5),
        "temperature_stage3": cfg.get("temperature_stage3", 0.0),
    }


@router.post("/config")
def update_config(body: ConfigModel):
    """更新模型配置（写回 config/llm.yaml）。api_key 留空=保持原值（防误清）。"""
    if not _CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="config/llm.yaml 不存在")
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    data = body.model_dump(exclude_none=True)
    if "api_key" in data and not data["api_key"]:
        data.pop("api_key")  # 空值=不改
    cfg.update(data)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    _clear_llm_cache()
    return {"status": "ok", "updated_fields": list(data.keys())}
