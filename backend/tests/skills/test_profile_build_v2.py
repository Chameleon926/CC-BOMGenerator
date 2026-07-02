"""
T5：画像加 negative_examples（反例召回锚点）

覆盖 _merge_profile 对 llm_profile.negative_examples 的解析：
- 正确解析
- 去重 + trim（去空 + 保序去重 + 限 5）
- 缺省为空 []
"""
import sys
from pathlib import Path

# 让 from src... 可导入
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.cc_bom_generator.nodes.skills._profile_logic import _merge_profile


def _merge(llm_profile: dict):
    """调 _merge_profile，固定统计输入为空，关注 negative_examples 行为。"""
    return _merge_profile(
        llm_profile=llm_profile,
        stat_keywords=[],
        stat_confusion=[],
        stat_examples=[],
        nkw=10,
        nsec=6,
        nq=3,
    )


def test_merge_negative_examples():
    """llm_profile 含 negative_examples → RecallProfile.negative_examples 解析对。"""
    llm_profile = {
        "negative_examples": [
            "供应商应交纳履约保证金",
            "买方支付预付款",
        ]
    }
    profile = _merge(llm_profile)
    assert profile.negative_examples == [
        "供应商应交纳履约保证金",
        "买方支付预付款",
    ]


def test_negative_examples_dedup_trim():
    """含重复/空串/空白 → 去空 + trim + 保序去重 + 限 5。"""
    llm_profile = {
        "negative_examples": [
            "  供应商应交纳履约保证金  ",  # 两端空白需 trim
            "供应商应交纳履约保证金",        # 与上一条 trim 后重复
            "",                              # 空串
            "   ",                           # 纯空白
            "买方支付预付款",
            "第三方代付货款",
            "甲方向乙方退款",
            "第6条超额部分",                 # 第 5 个有效项（前 4 项去重后：押金/预付/代付/退款）
            "超出限额外的应被截断",          # 第 6 个有效项（限 5，被截断）
        ]
    }
    profile = _merge(llm_profile)
    assert profile.negative_examples == [
        "供应商应交纳履约保证金",
        "买方支付预付款",
        "第三方代付货款",
        "甲方向乙方退款",
        "第6条超额部分",
    ]
    assert len(profile.negative_examples) == 5
    assert "超出限额外的应被截断" not in profile.negative_examples


def test_negative_examples_default_empty():
    """llm_profile 无 negative_examples → 默认 []。"""
    profile = _merge({})
    assert profile.negative_examples == []
