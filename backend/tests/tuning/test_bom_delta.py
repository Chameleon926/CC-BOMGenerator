"""BOMDelta 契约测试。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.cc_bom_generator.schemas.bom_delta import (
    BOMDelta, Modification, ModificationType
)
from src.cc_bom_generator.enums import FixTarget, ModificationAction


def test_modification_minimal():
    m = Modification(type=ModificationType.KEYWORD, action="add", after={"word": "保函"})
    assert m.type == ModificationType.KEYWORD
    assert m.before is None
    assert m.diagnosis_ids == []


def test_bom_delta_full():
    delta = BOMDelta(
        block_code="FSB0000004",
        from_version=1,
        fix_targets=[FixTarget.RULES],
        modifications=[
            Modification(type=ModificationType.MATCH, action="update",
                         before={"rule": "旧"}, after={"rule": "新"}, reason="漏抽保函"),
        ],
        regression_warnings=["删关键词'付款'可能影响条款B"],
    )
    assert delta.block_code == "FSB0000004"
    assert len(delta.modifications) == 1
    assert delta.modifications[0].type == ModificationType.MATCH
    assert delta.regression_warnings[0].startswith("删关键词")
    assert delta.fix_targets == [FixTarget.RULES]
    assert delta.modifications[0].after == {"rule": "新"}
    assert delta.modifications[0].action == ModificationAction.UPDATE
