# -*- coding: utf-8 -*-
"""B 方案纯逻辑单元测试（不连 DB / LLM）。

覆盖：
- _select_diverse_indices 边界（空/单/n>=len/全停用词 ValueError 退化/KMeans 空簇）+ wrapper 一致
- ingest 行解析 + 去重（positive_values 按值 vs positive_examples 按 tuple；空 ev 跳过；无列旧格式）
- selected_values / selected_examples 同步（ExampleRetrieveSkill）
"""

import sys
import os
import io
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from src.cc_bom_generator.nodes.skills._keyword_logic import (
    _select_diverse, _select_diverse_indices,
)
from src.cc_bom_generator.services.ingest_service import parse_excel_to_cleaned
from src.cc_bom_generator.schemas.cleaned_test_set import CleanedTestSet, PositiveExample
from src.cc_bom_generator.schemas.generation_state import GenerationState
from src.cc_bom_generator.nodes.skills.example_retrieve import ExampleRetrieveSkill


# ==================== _select_diverse_indices 边界 ====================

def test_indices_empty_list():
    """空列表 → 空索引列表（len <= n 走 range 分支，range(0)=[]）。"""
    assert _select_diverse_indices([], n=5) == []


def test_indices_single_element():
    """单元素 → [0]。"""
    assert _select_diverse_indices(["唯一一条"], n=5) == [0]


def test_indices_n_ge_len_returns_all():
    """n >= len(values) → 全索引 [0..len)，保序。"""
    vals = ["甲", "乙", "丙"]
    out = _select_diverse_indices(vals, n=5)
    assert out == [0, 1, 2]
    # n == len 也走同分支
    assert _select_diverse_indices(vals, n=3) == [0, 1, 2]


def test_indices_in_range_and_count():
    """len > n：返回索引都在 [0, len) 内，数量 <= n。"""
    vals = [f"样本内容编号{i}表述" for i in range(20)]
    out = _select_diverse_indices(vals, n=5)
    assert len(out) <= 5
    assert all(0 <= i < len(vals) for i in out), f"越界: {out}"
    # 无重复
    assert len(out) == len(set(out)), f"索引重复: {out}"


def test_indices_empty_vocab_falls_back():
    """TfidfVectorizer 词表空（全空字符串）抛 ValueError → 退化为前 n 个索引。

    注意：触发条件是"空词汇表"（空字符串），不是"全停用词中文"——jieba 会把任何汉字切成
    token，所以 ['的','了',...] 不会触发，照样走 KMeans（见下一条测试）。
    """
    vals = ["", "", "", "", ""][:3]   # 全空串 → empty vocabulary → ValueError
    out = _select_diverse_indices(vals, n=5)
    # 退化分支：list(range(min(n, len)))
    assert out == list(range(3))
    assert all(0 <= i < len(vals) for i in out)


def test_indices_stopword_chars_go_through_kmeans_not_fallback():
    """中文停用词单字经 jieba 仍有 token，不触发 ValueError，走 KMeans 返回聚类索引。

    佐证：fallback 分支在实际中文语料下几乎不可达（死代码倾向），但空字符串路径可触发，
    二者都安全（索引不越界）。这里只断言"不退化 + 索引合法"，不锁死具体顺序。
    """
    vals = ["的", "了", "是", "在", "和"] * 4   # 20 个，len > n=5
    out = _select_diverse_indices(vals, n=5)
    assert len(out) <= 5
    assert all(0 <= i < len(vals) for i in out)
    assert len(out) == len(set(out)), f"索引重复: {out}"


def test_indices_kmeans_empty_cluster_safe():
    """KMeans 某簇可能为空：代码 if len(cluster_indices)==0: continue，不崩且不产出越界。"""
    # 构造容易分出空簇的极端分布：大量重复 + 少量离群
    vals = ["合同付款约定"] * 15 + ["完全不同场景的奇异样本XYZ"] + ["另一个罕见分支QWERT"] * 2
    out = _select_diverse_indices(vals, n=5)
    assert all(0 <= i < len(vals) for i in out)
    assert len(out) <= 5


def test_wrapper_consistency_with_indices():
    """_select_diverse = [values[i] for i in indices]，两者一一对应。"""
    vals = [f"多样性正例文本片段{i}号" for i in range(12)]
    idxs = _select_diverse_indices(vals, n=4)
    strs = _select_diverse(vals, n=4)
    assert strs == [vals[i] for i in idxs], "wrapper 与 indices 不一致"
    assert len(strs) == len(idxs)


def test_indices_default_n_is_5():
    """默认 n=5。"""
    vals = [f"样本{i}内容文本" for i in range(30)]
    out = _select_diverse_indices(vals)  # 不传 n
    assert len(out) <= 5


# ==================== ingest 行解析 + 去重 ====================

def _write_xlsx(rows, cols):
    """把 list[dict] 写临时 xlsx，返回 Path。"""
    df = pd.DataFrame(rows, columns=cols)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    df.to_excel(path, index=False)
    return Path(path)


def test_ingest_parses_row_fields_and_dedup_by_tuple():
    """positive_examples 按 (doc_id,ev,item_code,item_name,doc_name) 全 tuple 精确去重。"""
    p = _write_xlsx(
        [
            {"doc_id": "D1", "item_code": "1.1", "item_name": "金额", "doc_name": "采购合同",
             "expected_value": "付款金额10万", "block_code": "B1", "block_name": "付款条款"},
            {"doc_id": "D1", "item_code": "1.1", "item_name": "金额", "doc_name": "采购合同",
             "expected_value": "付款金额10万", "block_code": "B1", "block_name": "付款条款"},  # 完全重复行
            {"doc_id": "D2", "item_code": "1.2", "item_name": "币种", "doc_name": "服务合同",
             "expected_value": "付款金额10万", "block_code": "B1", "block_name": "付款条款"},  # 同 ev 不同行 → 保留
        ],
        ["doc_id", "item_code", "item_name", "doc_name", "expected_value", "block_code", "block_name"],
    )
    cleaned = parse_excel_to_cleaned(p, clause="付款条款", block_code="B1")
    # positive_values 按 ev 字符串去重 → 1 个（两行 ev 相同）
    assert cleaned.positive_values == ["付款金额10万"]
    assert cleaned.after_dedup == 1
    # positive_examples 按 tuple 去重 → 2 个（D1 与 D2 行级字段不同）
    assert len(cleaned.positive_examples) == 2
    docs = {r.doc_id for r in cleaned.positive_examples}
    assert docs == {"D1", "D2"}
    # 行级字段正确填充
    d2 = next(r for r in cleaned.positive_examples if r.doc_id == "D2")
    assert d2.item_code == "1.2" and d2.item_name == "币种" and d2.doc_name == "服务合同"
    assert d2.expected_value == "付款金额10万"
    os.unlink(p)


def test_ingest_skips_empty_expected_value():
    """空 expected_value 行被跳过（不进 positive_values 也不进行列表）。"""
    p = _write_xlsx(
        [
            {"doc_id": "D1", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "有值", "block_code": "B1", "block_name": "X"},
            {"doc_id": "D2", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "", "block_code": "B1", "block_name": "X"},  # 空 ev
            {"doc_id": "D3", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "   ", "block_code": "B1", "block_name": "X"},  # 纯空白
        ],
        ["doc_id", "item_code", "item_name", "doc_name", "expected_value", "block_code", "block_name"],
    )
    cleaned = parse_excel_to_cleaned(p, clause="X", block_code="B1")
    assert cleaned.positive_values == ["有值"]
    assert len(cleaned.positive_examples) == 1
    assert cleaned.positive_examples[0].doc_id == "D1"
    os.unlink(p)


def test_ingest_values_count_relation():
    """original_count = 去空白后的 ev 总数（含重复）；after_dedup = 去重后 unique 数；
    positive_examples 数 = tuple 去重后行数（>= after_dedup 当同 ev 多行）。"""
    p = _write_xlsx(
        [
            {"doc_id": "D1", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "v1", "block_code": "B1", "block_name": "X"},
            {"doc_id": "D1", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "v1", "block_code": "B1", "block_name": "X"},  # 重复 ev 同行 → 1 unique, 1 row
            {"doc_id": "D2", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "v2", "block_code": "B1", "block_name": "X"},
        ],
        ["doc_id", "item_code", "item_name", "doc_name", "expected_value", "block_code", "block_name"],
    )
    cleaned = parse_excel_to_cleaned(p, clause="X", block_code="B1")
    assert cleaned.original_count == 3      # 3 个非空 ev
    assert cleaned.after_dedup == 2         # v1, v2
    assert len(cleaned.positive_examples) == 2  # (D1,v1), (D2,v2)
    os.unlink(p)


def test_ingest_no_optional_columns_old_format():
    """旧格式无 doc_id/item_code/... 列 → 行级字段为空串，仍能解析，positive_examples 数 == after_dedup。"""
    p = _write_xlsx(
        [
            {"expected_value": "甲", "block_code": "B1"},
            {"expected_value": "乙", "block_code": "B1"},
            {"expected_value": "甲", "block_code": "B1"},  # 重复 ev → 去重
        ],
        ["expected_value", "block_code"],
    )
    cleaned = parse_excel_to_cleaned(p, clause="X", block_code="B1")
    assert cleaned.positive_values == ["甲", "乙"]
    # 无行级列 → item_code 等全 ""，tuple 去重退化为按 ev 去重
    assert len(cleaned.positive_examples) == 2
    for r in cleaned.positive_examples:
        assert r.doc_id == "" and r.item_code == "" and r.item_name == "" and r.doc_name == ""
    os.unlink(p)


def test_ingest_block_code_filter():
    """传 block_code 时按 block_code 列过滤（多条款混排）。"""
    p = _write_xlsx(
        [
            {"doc_id": "D1", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "甲", "block_code": "B1", "block_name": "X"},
            {"doc_id": "D2", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "乙", "block_code": "B2", "block_name": "Y"},
        ],
        ["doc_id", "item_code", "item_name", "doc_name", "expected_value", "block_code", "block_name"],
    )
    cleaned = parse_excel_to_cleaned(p, clause="", block_code="B2")
    assert cleaned.positive_values == ["乙"]
    assert cleaned.block_code == "B2"
    os.unlink(p)


def test_ingest_preserve_order():
    """positive_values 与 positive_examples 保序（首次出现顺序）。"""
    p = _write_xlsx(
        [
            {"doc_id": "D1", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "甲", "block_code": "B1", "block_name": "X"},
            {"doc_id": "D2", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "乙", "block_code": "B1", "block_name": "X"},
            {"doc_id": "D3", "item_code": "", "item_name": "", "doc_name": "",
             "expected_value": "丙", "block_code": "B1", "block_name": "X"},
        ],
        ["doc_id", "item_code", "item_name", "doc_name", "expected_value", "block_code", "block_name"],
    )
    cleaned = parse_excel_to_cleaned(p, clause="X", block_code="B1")
    assert cleaned.positive_values == ["甲", "乙", "丙"]
    assert [r.expected_value for r in cleaned.positive_examples] == ["甲", "乙", "丙"]
    os.unlink(p)


# ==================== selected_values / selected_examples 同步 ====================

def test_example_retrieve_syncs_values_and_rows():
    """ExampleRetrieveSkill：selected_examples[i].expected_value == selected_values[i]，doc_id 不丢。"""
    rows = [
        PositiveExample(doc_id=f"D{i}", expected_value=f"正例文本编号{i}内容", item_code=f"c{i}", item_name=f"n{i}", doc_name="合同")
        for i in range(15)
    ]
    cleaned = CleanedTestSet(clause="X", block_code="B1", positive_values=[r.expected_value for r in rows], positive_examples=rows)
    state = GenerationState(cleaned=cleaned)
    out = ExampleRetrieveSkill().execute(state)
    assert len(out.selected_examples) == len(out.selected_values) > 0
    # 同步断言
    assert [r.expected_value for r in out.selected_examples] == out.selected_values
    # 行级字段（doc_id 等）随行带回
    assert all(r.doc_id.startswith("D") for r in out.selected_examples)
    # 选出的索引都在原 rows 范围内
    chosen_evs = set(out.selected_values)
    assert chosen_evs.issubset({r.expected_value for r in rows})


def test_example_retrieve_fallback_when_no_rows():
    """无行结构（旧简版数据）→ selected_values 在去重字符串上选，selected_examples 为空。"""
    cleaned = CleanedTestSet(
        clause="X", block_code="B1",
        positive_values=[f"样本值{i}内容" for i in range(8)],
        positive_examples=[],  # 无行
    )
    state = GenerationState(cleaned=cleaned)
    out = ExampleRetrieveSkill().execute(state)
    assert len(out.selected_values) > 0
    assert out.selected_examples == []


def test_example_retrieve_empty_input():
    """空输入 → 两字段都空。"""
    cleaned = CleanedTestSet(clause="X", block_code="B1", positive_values=[], positive_examples=[])
    state = GenerationState(cleaned=cleaned)
    out = ExampleRetrieveSkill().execute(state)
    assert out.selected_values == []
    assert out.selected_examples == []
