#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quick_poc · 近义去重（组装提示词前：控 token、防重复淹没）。

PoC 用 difflib 字符相似度贪心去重（纯标准库、无需模型）。
正式工具升级为 embedding + MMR/聚类（更准，Phase 2 向量库）。
"""
import difflib


def near_dedup(items, threshold=0.8):
    """贪心近义去重：依次保留，与已保留任一相似度 ≥ threshold 的丢弃；保序。

    threshold 越高越宽松（保留越多）；0.8 = 高度相似才去重。
    """
    kept = []
    for it in items:
        s = str(it)
        if any(difflib.SequenceMatcher(None, s, str(k)).ratio() >= threshold for k in kept):
            continue
        kept.append(it)
    return kept


def near_dedup_report(items, threshold=0.8):
    """同 near_dedup，但额外返回被去掉的项及其命中的保留项，便于打印"去掉了哪些"。

    返回 (kept, dropped)；dropped = [(被去掉项, 命中的保留项), ...]。
    """
    kept = []
    dropped = []
    for it in items:
        s = str(it)
        hit = next((k for k in kept if difflib.SequenceMatcher(None, s, str(k)).ratio() >= threshold), None)
        if hit is None:
            kept.append(it)
        else:
            dropped.append((it, hit))
    return kept, dropped
