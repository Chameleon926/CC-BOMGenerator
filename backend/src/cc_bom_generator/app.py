"""FastAPI 应用工厂。"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routers.generate import router as generate_router
from .api.routers.runs import router as runs_router
from .api.routers.clauses import router as clauses_router
from .api.routers.config import router as config_router


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

    # 按资源拆分的 4 个 router（优化模块后加 tuning_router）
    app.include_router(generate_router, prefix="/api")
    app.include_router(runs_router, prefix="/api")
    app.include_router(clauses_router, prefix="/api")
    app.include_router(config_router, prefix="/api")
    return app
