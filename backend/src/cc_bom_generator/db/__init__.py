"""数据库初始化 —— Engine + Session 工厂 + 事务上下文 + Repository。"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

# 读配置
_ROOT = Path(__file__).resolve().parents[3]  # backend/src/cc_bom_generator/db → backend
_CFG_PATH = _ROOT.parent / "config" / "llm.yaml"  # 项目根目录下的 config/llm.yaml

_db_config = {}
if _CFG_PATH.exists():
    with open(_CFG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    _db_config = {
        "host": cfg.get("mysql_host", "127.0.0.1"),
        "port": cfg.get("mysql_port", 3306),
        "user": cfg.get("mysql_user", "root"),
        "password": cfg.get("mysql_password", ""),
        "database": cfg.get("mysql_database", "cc_bom_generator"),
    }

DATABASE_URL = (
    f"mysql+pymysql://{_db_config['user']}:{_db_config['password']}"
    f"@{_db_config['host']}:{_db_config['port']}/{_db_config['database']}"
    "?charset=utf8mb4"
)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """同步事务上下文（供非 HTTP 入口用，如 nodes.pipeline.generate_bom）。

    出块统一 commit / 异常 rollback / 结束 close。
    一次管线 run 包在一个 session_scope 里 = 一个事务（run 级 Unit-of-Work）。
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：yield session 给路由，**不 commit**（事务边界由 service 层控制）。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session() -> Session:
    """[已废弃] 裸 Session 工厂，不管理生命周期。新代码用 session_scope() 或 get_db()。"""
    return SessionLocal()


# 放在末尾避免循环 import（repository 只依赖 .models，models 依赖上方已定义的 Base）
from .repository import PipelineRepository  # noqa: E402

__all__ = [
    "engine", "SessionLocal", "Base",
    "session_scope", "get_db", "get_session",
    "PipelineRepository", "DATABASE_URL",
]
