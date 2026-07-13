"""FastAPI 应用工厂。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.routers.generate import router as generate_router
from .api.routers.runs import router as runs_router
from .api.routers.clauses import router as clauses_router
from .api.routers.config import router as config_router
from .errors import AppError


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

    # 领域异常统一转 HTTP：service 层抛 AppError 子类，handler 按 MRO 通吃。
    # 返回体 {detail(=message), code, context(可选)}，detail 与 FastAPI HTTPException 形状一致（前端拦截器读 .detail）。
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        content = {"detail": exc.message, "code": exc.code}
        if exc.detail is not None:
            content["context"] = exc.detail
        return JSONResponse(status_code=exc.status_code, content=content)

    return app
