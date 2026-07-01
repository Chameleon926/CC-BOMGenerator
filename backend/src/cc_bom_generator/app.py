"""FastAPI 应用工厂。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routers.generate import router as generate_router


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用（生成场景）。"""
    app = FastAPI(
        title="CC-BOMGenerator API",
        description="语义 BOM 规则编译器 — 生成场景后端接口",
        version="0.1.0",
    )

    # 允许前端跨域（开发期）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(generate_router, prefix="/api")
    return app
