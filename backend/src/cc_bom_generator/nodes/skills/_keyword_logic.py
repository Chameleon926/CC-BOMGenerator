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
from sklearn.metrics.pairwise import cosine_similarity

from ...schemas.cleaned_test_set import CleanedTestSet


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


def _select_diverse_indices(values: List[str], n: int = 5) -> List[int]:
    """
    TF-IDF + KMeans 聚类，每类取离中心最近的样本，返回其在 values 中的索引列表。

    返回索引而非值，使调用方能同时取回值与对应的行级字段（如 doc_id），
    供 selected_examples 追溯。
    """
    if len(values) <= n:
        return list(range(len(values)))

    try:
        vectorizer = TfidfVectorizer(
            tokenizer=lambda x: jieba.lcut(x),
            token_pattern=None,
        )
        X = vectorizer.fit_transform(values)
    except ValueError:
        # TF-IDF 可能因为全停用词而失败，退化为取前 n 个
        return list(range(min(n, len(values))))

    k = min(n, X.shape[0])
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    km.fit(X)

    selected_idx: List[int] = []
    for i in range(k):
        cluster_indices = np.where(km.labels_ == i)[0]
        if len(cluster_indices) == 0:
            continue
        # 取离中心最近的
        distances = km.transform(X[cluster_indices])[:, i]
        nearest = cluster_indices[distances.argmin()]
        selected_idx.append(int(nearest))

    return selected_idx[:n]


def _select_diverse(values: List[str], n: int = 5) -> List[str]:
    """聚类选 n 个互相差异最大的代表性样本（字符串），保留供 extract_keywords 等旧调用方。"""
    return [values[i] for i in _select_diverse_indices(values, n)]


# ==================== 反例选取（误抽值去重 + 相似度排序）====================

def _clean_for_similarity(text: str) -> str:
    """剥离 markdown 表格/HTML 噪音符号，只留语义文本（TF-IDF 前调用）。"""
    text = re.sub(r'<br\s*/?>', ' ', text)
    text = re.sub(r'\|{2,}', ' ', text)
    text = re.sub(r'(?<=\S)\|(?=\S)', '', text)
    text = re.sub(r'^[-:|]+\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _dedup_misextract(values: List[str], threshold: float = 0.9) -> List[str]:
    """去重相似度 > threshold 的误抽内容，保留第一个出现的（TF-IDF cosine）。"""
    if len(values) <= 1:
        return list(values)
    cleaned = [_clean_for_similarity(v) for v in values]
    try:
        vectorizer = TfidfVectorizer(tokenizer=lambda x: jieba.lcut(x), token_pattern=None)
        X = vectorizer.fit_transform(cleaned)
    except ValueError:
        return list(dict.fromkeys(values))
    unique_idx = [0]
    for i in range(1, len(values)):
        is_dup = any(cosine_similarity(X[i], X[j])[0][0] > threshold for j in unique_idx)
        if not is_dup:
            unique_idx.append(i)
    return [values[i] for i in unique_idx]


def _rank_by_confusion(misextract: List[str], positive_pool: List[str]) -> List[str]:
    """按与正例池的最大 TF-IDF 相似度排序（越像正例 = 越危险 = 排越前）。"""
    if not misextract:
        return []
    if not positive_pool:
        return list(misextract)
    cleaned_mis = [_clean_for_similarity(v) for v in misextract]
    cleaned_pos = [_clean_for_similarity(v) for v in positive_pool]
    try:
        all_texts = cleaned_pos + cleaned_mis
        vectorizer = TfidfVectorizer(tokenizer=lambda x: jieba.lcut(x), token_pattern=None)
        X_all = vectorizer.fit_transform(all_texts)
    except ValueError:
        return list(misextract)
    n_pos = len(cleaned_pos)
    scored = []
    for i, val in enumerate(misextract):
        mis_vec = X_all[n_pos + i]
        pos_vecs = X_all[:n_pos]
        max_sim = cosine_similarity(mis_vec, pos_vecs).max()
        scored.append((val, max_sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [v for v, _ in scored]


def select_prompt_misextract(misextract_values: List[str], positive_pool: List[str], cap: int = 5) -> List[str]:
    """反例选取全流程：去重 → 相似度排序 → TOP cap。"""
    if not misextract_values:
        return []
    deduped = _dedup_misextract(misextract_values)
    ranked = _rank_by_confusion(deduped, positive_pool)
    return ranked[:cap]


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
