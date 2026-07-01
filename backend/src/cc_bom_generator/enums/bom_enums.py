"""BOM 相关枚举（唯一事实源）。"""

from enum import Enum


class BomSource(str, Enum):
    """BOM 来源。"""
    GENERATE = "generate"
    OPTIMIZE = "optimize"
    MANUAL = "manual"


class BOMStatus(str, Enum):
    """BOM 状态。"""
    DRAFT = "draft"
    REVIEWED = "reviewed"
    DEACTIVATED = "deactivated"


class PipelineMode(str, Enum):
    """管线模式。"""
    GENERATE = "generate"
    OPTIMIZE = "optimize"


class RunStatus(str, Enum):
    """管线执行状态。"""
    RUNNING = "running"
    SUCCESS = "success"
    FAIL = "fail"
