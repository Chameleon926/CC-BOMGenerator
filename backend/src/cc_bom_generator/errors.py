"""领域异常基类 + 具体异常（service 层抛，app.py 注册一个 handler 统一转 HTTP）。

设计（架构师版，带基类）：
- service 层抛领域异常（AppError 子类），router 不用堆 try/except。
- app.py 注册 `@app.exception_handler(AppError)`，按 MRO 通吃所有子类，
  统一返回 {detail(=message，前端兼容), code, context(可选)}。
- 现有 HTTPException 散抛暂不动；新代码（优化模块等）用 AppError 子类。

可延展：加新错误类型 = 加一个 AppError 子类（设 status_code/code/default_message），
自动被 handler 通吃，零改调用方/注册。
"""

from __future__ import annotations

from typing import Any, Optional


class AppError(Exception):
    """领域异常基类。子类设 status_code（HTTP 状态）/ code（机器码）/ default_message。"""
    status_code: int = 500
    code: str = "app_error"
    default_message: str = "服务内部错误"

    def __init__(self, message: Optional[str] = None, detail: Any = None):
        self.message = message or self.default_message
        self.detail = detail  # 可选上下文（如乐观锁的 from/current 版本）
        super().__init__(self.message)


class NotFound(AppError):
    """资源不存在。"""
    status_code = 404
    code = "not_found"
    default_message = "资源不存在"


class ConcurrencyError(AppError):
    """乐观锁冲突：基线版本已变（如 apply BOMDelta 时 from_bom_version_id 过期）。"""
    status_code = 409
    code = "concurrency_conflict"
    default_message = "基线已变更，请基于最新版本重试"


class ClassifyFailed(AppError):
    """badcase 自动判类失败（启发式无法判定 召回失败/抽取失败，需人填）。"""
    status_code = 422
    code = "classify_failed"
    default_message = "badcase 判类失败，请人工标注问题类型"


class DeltaConflict(AppError):
    """BOMDelta 冲突（modifications 矛盾 / 无法确定性合并到当前 BOM）。"""
    status_code = 409
    code = "delta_conflict"
    default_message = "BOMDelta 冲突，无法合并"
