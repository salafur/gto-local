"""牌力评估器。

evaluate5 / evaluate7 返回一个整数，数值越大牌越强。
编码方式：category * 13^5 + 各 tiebreak rank 按 13 进制展开，
保证"先比牌型、再按规则比点数"的顺序与整数比较完全一致。

牌型 category: 8同花顺 7四条 6葫芦 5同花 4顺子 3三条 2两对 1一对 0高牌
"""
from __future__ import annotations

from itertools import combinations
from typing import Sequence

_BASE = 13

# 牌型名称，用于展示
CATEGORY_NAMES = [
    "高牌", "一对", "两对", "三条", "顺子", "同花", "葫芦", "四条", "同花顺",
]


def _encode(category: int, tiebreaks: Sequence[int]) -> int:
    score = category
    for r in tiebreaks:
        score = score * _BASE + r
    # 补齐长度，保证同 category 不同长度的 tiebreak 可比
    for _ in range(5 - len(tiebreaks)):
        score *= _BASE
    return score


def evaluate5(cards: Sequence[int]) -> int:
    """评估 5 张牌的牌力。"""
    assert len(cards) == 5
    ranks = [c >> 2 for c in cards]
    suits = [c & 3 for c in cards]

    flush = len(set(suits)) == 1

    # 统计每个 rank 出现次数，按 (次数, rank) 降序
    count = {}
    for r in ranks:
        count[r] = count.get(r, 0) + 1
    groups = sorted(count.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    counts_desc = [c for _, c in groups]

    # 顺子检测（含 A-5 轮子）
    uniq = sorted(set(ranks))
    straight_high = -1
    if len(uniq) == 5:
        if uniq[-1] - uniq[0] == 4:
            straight_high = uniq[-1]
        elif uniq == [0, 1, 2, 3, 12]:  # A 2 3 4 5
            straight_high = 3  # 5 高顺

    if flush and straight_high >= 0:
        return _encode(8, [straight_high])
    if counts_desc[0] == 4:
        quad = groups[0][0]
        kicker = groups[1][0]
        return _encode(7, [quad, kicker])
    if counts_desc[0] == 3 and counts_desc[1] == 2:
        return _encode(6, [groups[0][0], groups[1][0]])
    if flush:
        return _encode(5, sorted(ranks, reverse=True))
    if straight_high >= 0:
        return _encode(4, [straight_high])
    if counts_desc[0] == 3:
        trip = groups[0][0]
        kickers = sorted((r for r, c in groups[1:]), reverse=True)
        return _encode(3, [trip] + kickers)
    if counts_desc[0] == 2 and counts_desc[1] == 2:
        pairs = sorted((r for r, c in groups[:2]), reverse=True)
        kicker = groups[2][0]
        return _encode(2, pairs + [kicker])
    if counts_desc[0] == 2:
        pair = groups[0][0]
        kickers = sorted((r for r, c in groups[1:]), reverse=True)
        return _encode(1, [pair] + kickers)
    return _encode(0, sorted(ranks, reverse=True))


def evaluate7(cards: Sequence[int]) -> int:
    """评估 7 张牌（或 5/6 张）取最优 5 张组合的牌力。"""
    if len(cards) == 5:
        return evaluate5(cards)
    best = -1
    for five in combinations(cards, 5):
        s = evaluate5(five)
        if s > best:
            best = s
    return best


def hand_category(score: int) -> str:
    """从分数还原牌型名称（用于展示/调试）。"""
    return CATEGORY_NAMES[score // (_BASE ** 5)]
