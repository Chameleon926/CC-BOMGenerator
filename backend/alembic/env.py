"""Alembic env.py —— 自动发现 models 中的模型表。"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic 配置
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入 Base 和所有模型（让 Alembic 发现表）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cc_bom_generator.db import Base
from src.cc_bom_generator.db.models import (
    Clause, BomVersion, PipelineRun, NodeExecution, LlmCall, RuleModification,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直接执行到数据库。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()