"""诊断相关枚举（唯一事实源）。"""

from enum import Enum


class DiagnosisCategory(str, Enum):
    """5 类归因。"""
    RECALL = "召回问题"
    MIXED = "混合问题"
    BOM = "BOM问题"
    PROMPT_TEMPLATE = "Prompt模板待优化"
    MODEL_REASONING = "大模型推理问题"


class ConfidenceLevel(str, Enum):
    """归因置信度。"""
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class FixTarget(str, Enum):
    """修复落点。"""
    RULES = "rules"
    RECALL_PROFILE = "recall_profile"
    BOTH = "both"


class CaseType(str, Enum):
    """Badcase 类型。"""
    MISS = "miss"
    FALSE_POSITIVE = "false_positive"
