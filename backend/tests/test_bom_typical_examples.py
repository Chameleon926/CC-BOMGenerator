# -*- coding: utf-8 -*-
"""TE-1: BOM typical_examples 契约测试。"""
from src.cc_bom_generator.schemas.bom import BOM, TypicalExample


def test_typical_example_model():
    te = TypicalExample(value="由买方在3日内以T/T支付价款", reason="依据匹配规则『付款时间+方式』命中")
    assert te.value == "由买方在3日内以T/T支付价款"
    assert te.reason.startswith("依据匹配规则")


def test_bom_typical_examples_default_empty():
    bom = BOM(clause="测试")
    assert bom.typical_examples == []


def test_bom_typical_examples_roundtrip():
    bom = BOM(
        clause="返利条款",
        typical_examples=[
            TypicalExample(value="v1", reason="r1"),
            TypicalExample(value="v2", reason="r2"),
        ],
    )
    d = bom.model_dump(mode="json")
    assert len(d["typical_examples"]) == 2
    assert d["typical_examples"][0] == {"value": "v1", "reason": "r1"}
    # 反序列化往返
    bom2 = BOM.model_validate(d)
    assert bom2.typical_examples[1].value == "v2"
    assert bom2.typical_examples[1].reason == "r2"
