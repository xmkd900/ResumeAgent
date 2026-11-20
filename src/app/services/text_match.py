"""文本定位工具：判断一段引用能否在原文里找到，并回填原文片段。

为什么需要它：
- 判卷要求"命中要点必须有原文依据"，但模型抄引用时常改标点、加空格、全半角混用；
  用严格 `in` 判断会把真实引用判成伪造（假阴性）。
- 简历诊断/要点抽取同理：PDF 解析出的空格与模型输出的引用几乎不可能逐字一致。

所以这里只做一件**机械可验证**的事：
    引用能否在原文中定位？能，就返回原文里真实存在的那一段。

语义是否等价不归它管——那属于模型判断。
"""

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

# 只去掉"排版差异"，不去掉实义字符：空白、常见中英文标点
_IGNORABLE = set(" \t\r\n\u3000，。！？；：、,.!?;:\"'“”‘’（）()[]【】<>《》—-·…/\\|~`@#$%^&*+=_")
_MIN_QUOTE = 4


@dataclass(slots=True)
class QuoteMatch:
    """引用定位结果。score=1.0 表示规范化后完全一致。"""

    score: float
    text: str
    start: int
    end: int

    @property
    def grounded(self) -> bool:
        return self.score >= 0.9


def _compact(source: str) -> tuple[str, list[int]]:
    """把文本压缩成"无空白无标点"的形式，同时记录每个字符回到原文的下标。"""
    chars: list[str] = []
    index_map: list[int] = []
    for index, raw in enumerate(source or ""):
        char = unicodedata.normalize("NFKC", raw)
        if not char or char.isspace() or char in _IGNORABLE:
            continue
        for piece in char:
            chars.append(piece.lower())
            index_map.append(index)
    return "".join(chars), index_map


def _span(source_map: list[int], start: int, end: int, source: str) -> str:
    """压缩下标 → 原文片段（end 为开区间）。"""
    if not source_map:
        return ""
    left = source_map[max(0, min(start, len(source_map) - 1))]
    right = source_map[max(0, min(end - 1, len(source_map) - 1))]
    return source[left : right + 1]


def locate_quote(quote: str, source: str) -> QuoteMatch:
    """在 source 中定位 quote，返回匹配度与原文片段。

    定位策略（从严格到宽松）：
    1. 规范化后完全包含 → 1.0；
    2. 用最长公共块定位锚点，再取锚点附近的窗口算相似度；
    3. 都失败 → 返回 0 分与空片段。
    """
    raw_quote = (quote or "").strip()
    if len(raw_quote) < _MIN_QUOTE or not (source or "").strip():
        return QuoteMatch(0.0, "", -1, -1)

    quote_c, _ = _compact(raw_quote)
    if len(quote_c) < _MIN_QUOTE:
        return QuoteMatch(0.0, "", -1, -1)
    source_c, source_map = _compact(source)
    if not source_c:
        return QuoteMatch(0.0, "", -1, -1)

    position = source_c.find(quote_c)
    if position >= 0:
        return QuoteMatch(
            score=1.0,
            text=_span(source_map, position, position + len(quote_c), source),
            start=source_map[position],
            end=source_map[position + len(quote_c) - 1] + 1,
        )

    matcher = SequenceMatcher(None, quote_c, source_c)
    block = matcher.find_longest_match(0, len(quote_c), 0, len(source_c))
    if block.size == 0:
        return QuoteMatch(0.0, "", -1, -1)

    # 用锚点在原文中的位置对齐，截一个略宽的窗口再算整体相似度
    window_start = max(0, block.b - block.a)
    window_end = min(len(source_c), window_start + len(quote_c) + 24)
    window = source_c[window_start:window_end]
    score = SequenceMatcher(None, quote_c, window).ratio()
    # 相似度太低说明"这段引用不在原文里"，不要返回一段无关文本误导调用方
    if score < 0.6:
        return QuoteMatch(score, "", -1, -1)
    return QuoteMatch(
        score=score,
        text=_span(source_map, window_start, window_end, source),
        start=source_map[window_start],
        end=source_map[window_end - 1] + 1,
    )


def normalize_phrase(text: str) -> str:
    """短语归一化：用于标签/关键词比较（去掉空格、标点、大小写差异）。

    注意边界：它只适合"同一个词的不同写法"（Spring Cloud / SpringCloud），
    不能用来判断两句话语义是否相同。
    """
    compact, _ = _compact(text)
    return compact


def contains_phrase(haystack: str, needle: str) -> bool:
    """标签级包含判断（已归一化），比原始 `in` 容忍空格与全半角。"""
    if not needle:
        return False
    return normalize_phrase(needle) in normalize_phrase(haystack)


__all__ = ["QuoteMatch", "contains_phrase", "locate_quote", "normalize_phrase"]
