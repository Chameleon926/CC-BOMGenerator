# -*- coding: utf-8 -*-
"""AF-4 领域异常 + 全局 handler 测试。"""
from fastapi.testclient import TestClient

from src.cc_bom_generator.app import create_app
from src.cc_bom_generator.errors import (
    AppError, NotFound, ConcurrencyError, ClassifyFailed, DeltaConflict,
)


def test_error_subclasses_metadata():
    """子类 status_code/code 正确，都是 AppError 子类。"""
    assert issubclass(NotFound, AppError) and NotFound.status_code == 404 and NotFound.code == "not_found"
    assert issubclass(ConcurrencyError, AppError) and ConcurrencyError.status_code == 409
    assert issubclass(ClassifyFailed, AppError) and ClassifyFailed.status_code == 422
    assert issubclass(DeltaConflict, AppError) and DeltaConflict.code == "delta_conflict"


def _app_with_raiser():
    """create_app + 一个测试路由抛 AppError 子类。"""
    app = create_app()

    @app.get("/_test/raise_concurrency")
    def _r():
        raise ConcurrencyError(detail={"from_version": 3, "current": 5})

    @app.get("/_test/raise_classify")
    def _r2():
        raise ClassifyFailed("自定义判类失败消息")

    return app


def test_handler_converts_concurrency_to_409():
    """AppError 子类经全局 handler 转 HTTP（按 MRO 通吃基类 handler）。"""
    client = TestClient(_app_with_raiser())
    r = client.get("/_test/raise_concurrency")
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "concurrency_conflict"
    assert "基线" in body["detail"]  # 默认 message
    assert body["context"] == {"from_version": 3, "current": 5}  # 上下文透传


def test_handler_custom_message_and_no_context():
    """自定义 message 生效；无 detail 时 context 不出现。"""
    client = TestClient(_app_with_raiser())
    r = client.get("/_test/raise_classify")
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "classify_failed"
    assert body["detail"] == "自定义判类失败消息"
    assert "context" not in body  # ClassifyFailed 无 detail → context 不出现
