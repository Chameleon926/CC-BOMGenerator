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


class RootComponent(str, Enum):
    """归因路由：问题在抽取层还是 DQ 校验层。"""
    EXTRACTION = "extraction"   # 抽取规则/模型/画像 → 进 optimize
    DQ = "dq"                   # 新平台 DQ 漏拦 → 交新平台团队，不进 optimize


class Severity(str, Enum):
    """错例严重性。fatal = 方向/主体/金额反转（业务致命）。"""
    NORMAL = "normal"
    FATAL = "fatal"
