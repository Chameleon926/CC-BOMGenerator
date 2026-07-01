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


class ModificationType(str, Enum):
    """BOM 改动类型（对齐 rule_modifications.modification_type 列）。"""
    DEFINITION = "definition"
    INTERCEPTION = "interception"
    MATCH = "match"
    KEYWORD = "positive_keywords"
    CONFUSION = "confusion_words"
    PROFILE = "profile"


class ModificationAction(str, Enum):
    """BOM 改动动作。"""
    ADD = "add"
    UPDATE = "update"
    DELETE = "delete"
