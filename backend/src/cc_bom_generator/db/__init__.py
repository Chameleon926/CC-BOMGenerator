"""数据库初始化 —— Engine + Session 工厂。"""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

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


def get_session():
    """获取数据库会话（上下文管理器用法）。"""
    session = SessionLocal()
    try:
        return session
    except Exception:
        session.close()
        raise