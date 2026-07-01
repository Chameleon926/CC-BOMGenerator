"""
B 模块第 1 步：关键词抽取（不用大模型）

从 CleanedTestSet 的期望值列表中，用 jieba 分词 + 词频统计 + 规则过滤，
抽出正向关键词、易混淆词、多样性正例。

输出供后续 profile_build.py 和 generate.py 使用。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import List, Tuple

import jieba
import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from ...contracts.cleaned_test_set import CleanedTestSet


# ==================== 停用词 ====================

# 合同文本常见停用词（无信息量的通用词）
STOPWORDS = frozenset({
    # 代词/通用名词
    "甲方", "乙方", "丙方", "双方", "一方", "对方", "本方", "各方",
    "公司", "有限", "股份", "集团", "有限公司", "股份有限公司",
    # 通用动词
    "应当", "应该", "可以", "不得", "进行", "做出", "提供", "根据",
    "按照", "依据", "关于", "对于", "应当按", "有权",
    # 通用形容词/副词
    "及时", "合理", "相关", "以下", "以上", "上述", "下列",
    "其他", " its", "全部", "所有", "任何",
    # 连词/介词/量词
    "并且", "或者", "以及", "但是", "如果", "对于", "等于",
    "个", "项", "条", "款", "种", "类",
    # 合同通用结构词
    "合同", "协议", "约定", "条款", "规定", "执行", "生效",
    "签字", "盖章", "签署", "订", "立",
    # 标点
    "，", "。", "、", "：", "；", "！", "？", "（", "）",
    "(", ")", "[", "]", "【", "】", "{", "}", "-", "—", "/", "\\", "|",
    "的", "了", "在", "是", "为", "对", "与", "和", "或", "按",
    "向", "从", "由", "将", "被", "把", "给", "到", "于", "及",
    "以", "其", "该", "此", "这", "那", "些", "某",
})

# 合同高频领域词——这些是有价值的，不在停用词里
# （付款、发票、验收、违约金、保证金 等保留）

# 规则过滤用的正则
_RE_DIGIT = re.compile(r"\d")
_RE_PERCENT_MONEY = re.compile(r"[\d%％万元亿]")
_RE_COMPANY_SUFFIX = re.compile(r"[有限股份集团总公司院局办]")


def extract_keywords(
    cleaned: CleanedTestSet,
    top_n: int = 10,
) -> Tuple[List[str], List[str], List[str]]:
    """
    从 CleanedTestSet 抽取三样东西（全不用大模型）：

    Args:
        cleaned: A 模块交付的清洗后测试集
        top_n: 正向关键词数量上限

    Returns:
        (positive_keywords, confusion_words, positive_examples)
        - positive_keywords: 过滤后的短词关键词列表
        - confusion_words: 易混淆词列表
        - positive_examples: 多样性聚类挑选的正例
    """
    values = cleaned.positive_values

    if not values:
        return [], [], []

    # ---- 第1步：分词 + 词频 ----
    all_words = []
    for val in values:
        words = jieba.lcut(val)
        all_words.extend(words)

    # ---- 第2步：过滤停用词 + 标点 + 单字 ----
    filtered = [
        w for w in all_words
        if len(w) >= 2
        and w not in STOPWORDS
        and not _RE_DIGIT.search(w)              # 不含数字
        and not _RE_PERCENT_MONEY.search(w)      # 不含金额/百分比符号
        and not _RE_COMPANY_SUFFIX.search(w)      # 不含公司名后缀
        and not all(c in '，。、：；！？（）()[]【】""''…—·-/' for c in w)
    ]

    freq = Counter(filtered)

    # ---- 第3步：取 top_n * 3 候选，再做规则过滤 ----
    candidates = freq.most_common(top_n * 3)
    positive_keywords = _filter_keywords(candidates, top_n)

    # ---- 第4步：易混淆词 ----
    confusion_words = _extract_confusion(positive_keywords, all_words, freq)

    # ---- 第5步：多样性正例 ----
    positive_examples = _select_diverse(values, n=5)

    return positive_keywords, confusion_words, positive_examples


# ==================== 内部函数 ====================

def _filter_keywords(
    candidates: List[Tuple[str, int]],
    top_n: int,
) -> List[str]:
    """
    规则过滤候选关键词，返回最终的短词列表。
    规则：
      - 长度 2-8 字
      - 不含数字/金额/百分比
      - 不含公司名后缀
      - 词频 >= 2（至少出现两次）
    """
    result = []
    seen = set()
    total = len(candidates)

    for word, count in candidates:
        if len(result) >= top_n:
            break

        # 长度
        if len(word) < 2 or len(word) > 8:
            continue

        # 含数字/金额
        if _RE_DIGIT.search(word):
            continue
        if _RE_PERCENT_MONEY.search(word):
            continue

        # 公司名后缀
        if _RE_COMPANY_SUFFIX.search(word) and len(word) <= 4:
            continue

        # 频次门槛：至少出现 2 次
        if count < 2:
            continue

        # 去重
        if word in seen:
            continue
        seen.add(word)

        result.append(word)

    return result


def _extract_confusion(
    keywords: List[str],
    all_words: List[str],
    freq: Counter,
    top_n: int = 6,
) -> List[str]:
    """
    从全词频中找"与关键词相近但不在关键词列表里"的高频词。
    方法：编辑距离 <= 2 且不在关键词列表。
    """
    kw_set = set(keywords)
    confusion = []
    seen = set()

    for word, count in freq.most_common(200):
        if len(confusion) >= top_n:
            break
        if word in kw_set or word in seen:
            continue
        if len(word) < 2 or len(word) > 8:
            continue
        # 与任一关键词编辑距离 <= 2
        for kw in keywords:
            if _levenshtein(word, kw) <= 2 and _levenshtein(word, kw) > 0:
                confusion.append(word)
                seen.add(word)
                break

    return confusion


def _select_diverse(values: List[str], n: int = 5) -> List[str]:
    """
    从期望值列表中选 n 个互相差异最大的代表性样本。
    方法：TF-IDF 向量化 → KMeans 聚类 → 每类取离中心最近的样本。
    """
    if len(values) <= n:
        return list(values)

    try:
        vectorizer = TfidfVectorizer(
            tokenizer=lambda x: jieba.lcut(x),
            token_pattern=None,
        )
        X = vectorizer.fit_transform(values)
    except ValueError:
        # TF-IDF 可能因为全停用词而失败，退化为取前 n 个
        return list(values[:n])

    k = min(n, X.shape[0])
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    km.fit(X)

    selected = []
    for i in range(k):
        cluster_indices = np.where(km.labels_ == i)[0]
        if len(cluster_indices) == 0:
            continue
        # 取离中心最近的
        distances = km.transform(X[cluster_indices])[:, i]
        nearest = cluster_indices[distances.argmin()]
        selected.append(values[nearest])

    return selected[:n]


def _levenshtein(s1: str, s2: str) -> int:
    """编辑距离（标准 DP 实现）。"""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]
