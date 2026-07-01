"""
统一日志配置。

规范：
- 使用 log.info / log.error（不使用 log.debug / log.warn）
- 格式：时间 | 级别 | 模块 | 消息
- 输出：控制台（开发期）+ 可选文件（后续）
"""

import logging
import sys

# 全局配置（只初始化一次）
_configured = False


def get_logger(name: str) -> logging.Logger:
    """获取统一配置的 logger。"""
    global _configured
    if not _configured:
        _setup()
        _configured = True
    return logging.getLogger(name)


def _setup():
    """初始化根 logger 配置。"""
    root = logging.getLogger()
    root.setLevel(logging.INFO)  # 只用 INFO 和 ERROR，不开 DEBUG

    # 控制台输出
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | %(name)-20s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
