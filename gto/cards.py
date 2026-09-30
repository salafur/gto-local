"""扑克牌基础表示。

牌用 0-51 的整数表示：card = rank * 4 + suit
rank: 0=2, 1=3, ..., 8=T, 9=J, 10=Q, 11=K, 12=A
suit: 0=梅花c, 1=方块d, 2=红桃h, 3=黑桃s
"""
from __future__ import annotations

from typing import List, Tuple

RANKS = "23456789TJQKA"
SUITS = "cdhs"

Combo = Tuple[int, int]  # 两张手牌，升序存储


def card_rank(c: int) -> int:
    return c >> 2


def card_suit(c: int) -> int:
    return c & 3


def parse_card(s: str) -> int:
    """解析单张牌，如 "Ah" -> 50, "2c" -> 0。"""
    s = s.strip()
    if len(s) != 2:
        raise ValueError(f"非法的牌: {s!r}（应为两张字符，如 Ah/Td/2c）")
    r, su = s[0].upper(), s[1].lower()
    if r not in RANKS or su not in SUITS:
        raise ValueError(f"非法的牌: {s!r}")
    return RANKS.index(r) * 4 + SUITS.index(su)


def parse_cards(s: str) -> Tuple[int, ...]:
    """解析一串牌，如 "AhKd7c3s2h" 或空格分隔 "Ah Kd 7c"。兼容 10 写法。"""
    s = s.strip().replace("10", "T")
    if " " in s:
        return tuple(parse_card(p) for p in s.split())
    if len(s) % 2 != 0:
        raise ValueError(f"牌串长度应为偶数: {s!r}")
    return tuple(parse_card(s[i:i + 2]) for i in range(0, len(s), 2))


def parse_combo(s: str) -> Combo:
    """解析一个手牌组合，如 "AhKd" -> (rank 排序后的两张牌)。"""
    c = parse_cards(s)
    if len(c) != 2:
        raise ValueError(f"组合必须是两张牌: {s!r}")
    if c[0] == c[1]:
        raise ValueError(f"两张牌不能相同: {s!r}")
    return (min(c), max(c))


def card_str(c: int) -> str:
    return RANKS[card_rank(c)] + SUITS[card_suit(c)]


def cards_str(cards) -> str:
    return " ".join(card_str(c) for c in cards)


def combo_str(combo: Combo) -> str:
    """组合转字符串，高牌在前，如 "AhKd"。"""
    a, b = combo
    if card_rank(a) >= card_rank(b):
        return card_str(a) + card_str(b)
    return card_str(b) + card_str(a)


def full_deck() -> List[int]:
    return list(range(52))


def combos_conflict(a: Combo, b: Combo) -> bool:
    return bool({a[0], a[1]} & {b[0], b[1]})
