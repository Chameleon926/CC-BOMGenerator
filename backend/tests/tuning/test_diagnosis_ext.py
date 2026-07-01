"""DiagnosisResult 扩展字段测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.schemas.diagnosis import DiagnosisResult
from src.cc_bom_generator.enums import (
    DiagnosisCategory, CaseType, RootComponent, Severity,
)


def test_root_component_default_extraction():
    d = DiagnosisResult(case_id="b1", case_type=CaseType.MISS, category=DiagnosisCategory.RECALL)
    assert d.root_component == RootComponent.EXTRACTION
    assert d.severity == Severity.NORMAL


def test_severity_fatal_for_directional():
    d = DiagnosisResult(
        case_id="b2", case_type=CaseType.FALSE_POSITIVE,
        category=DiagnosisCategory.BOM,
        root_component=RootComponent.EXTRACTION, severity=Severity.FATAL,
        reason="资金方向抽反",
    )
    assert d.severity == Severity.FATAL
