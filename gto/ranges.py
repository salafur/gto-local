"""范围（Range）解析与操作。

支持的语法（逗号分隔多个条目）：
  AA          对子（6 个组合）
  77+         77 及以上所有对子
  AKs         同花 AK（4 个组合）
  ATs+        ATs 及更高同花 Ax（ATs,AJs,AQs,AKs）
  76s+        76s 及更高同花连张（76s..KQs）
  KQo         不同花 KQ（12 个组合）
  AJo+        AJo 及更高不同花 Ax
  AK          同花+不同花全部（16 个组合）
  random      全部 1326 个组合
  AKs:0.5     带权重（0~1），表示该手牌只有一半概率在范围里
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, Iterable, Tuple

from .cards import RANKS, SUITS, Combo, combos_conflict

WeightedRange = Dict[Combo, float]


def all_combos() -> WeightedRange:
    deck = range(52)
    return {(a, b): 1.0 for a, b in combinations(deck, 2)}


def _pair_combos(rank: int) -> Iterable[Combo]:
    for s1, s2 in combinations(range(4), 2):
        yield (min(rank * 4 + s1, rank * 4 + s2), max(rank * 4 + s1, rank * 4 + s2))


def _suited_combos(r_hi: int, r_lo: int) -> Iterable[Combo]:
    for s in range(4):
        a, b = r_hi * 4 + s, r_lo * 4 + s
        yield (min(a, b), max(a, b))


def _offsuit_combos(r_hi: int, r_lo: int) -> Iterable[Combo]:
    for s1 in range(4):
        for s2 in range(4):
            if s1 != s2:
                a, b = r_hi * 4 + s1, r_lo * 4 + s2
                yield (min(a, b), max(a, b))


def _expand_ladder(r_hi: int, r_lo: int, suited: str):
    """处理 "ATs+" / "76s+" / "KQo+" 的 + 扩展，返回 (hi, lo) 列表。

    遵循 PokerStove/Equilab 标准语义：
    - 连张（如 76s、T9s、KQo）：整体提升，直到高牌为 K（76s+ -> 76s..KQs）
    - 非连张（如 ATs、K7s、96s）：高牌固定，低牌提升到高牌-1
      （ATs+ -> ATs,AJs,AQs,AKs；K7s+ -> K7s..KQs；96s+ -> 96s,97s,98s）
    """
    if r_hi - r_lo == 1 and r_hi != 12:  # 连张：整体提升
        pairs = []
        hi, lo = r_hi, r_lo
        while hi <= 11:
            pairs.append((hi, lo))
            hi += 1
            lo += 1
        return pairs
    # 非连张：高牌固定，低牌提升（A 开头时低牌升到 K）
    return [(r_hi, lo) for lo in range(r_lo, r_hi)]


def _expand_token(token: str) -> Iterable[Tuple[Combo, float]]:
    token = token.strip()
    if not token:
        return
    weight = 1.0
    if ":" in token:
        token, w = token.rsplit(":", 1)
        weight = float(w)
        if not 0 < weight <= 1:
            raise ValueError(f"权重必须在 (0,1] 之间: {token}:{w}")

    if token.lower() in ("random", "any", "100%"):
        for c in all_combos():
            yield c, weight
        return

    # 具体组合写法，如 "AhKd"、"8c8d"
    if len(token) == 4 and token[1].lower() in SUITS and token[3].lower() in SUITS:
        from .cards import parse_combo
        yield parse_combo(token), weight
        return

    plus = token.endswith("+")
    if plus:
        token = token[:-1]

    suited = None
    if token.endswith(("s", "o")):
        suited = token[-1]
        token = token[:-1]

    if len(token) != 2 or token[0] not in RANKS or token[1] not in RANKS:
        raise ValueError(f"无法解析的范围条目: {token!r}")

    r0, r1 = RANKS.index(token[0]), RANKS.index(token[1])

    if r0 == r1:  # 对子
        start = r0
        end = 12 if plus else r0
        for r in range(start, end + 1):
            for c in _pair_combos(r):
                yield c, weight
        return

    r_hi, r_lo = max(r0, r1), min(r0, r1)
    ladder = _expand_ladder(r_hi, r_lo, suited) if plus else [(r_hi, r_lo)]
    for hi, lo in ladder:
        if suited == "s":
            gen = _suited_combos(hi, lo)
        elif suited == "o":
            gen = _offsuit_combos(hi, lo)
        else:
            gen = list(_suited_combos(hi, lo)) + list(_offsuit_combos(hi, lo))
        for c in gen:
            yield c, weight


def parse_range(text: str) -> WeightedRange:
    """解析范围字符串为 {组合: 权重}，同组合取最大权重（并集语义）。

    支持减法语法：以 "-" 开头的条目表示从范围中移除，如
    "random,-TT+,-AKs" = 全部手牌去掉 TT 以上对子和 AKs。
    减法条目在所有加法条目之后统一应用。
    """
    result: WeightedRange = {}
    removals = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if token.startswith("-"):
            removals.append(token[1:])
            continue
        for combo, w in _expand_token(token):
            if combo in result:
                result[combo] = max(result[combo], w)
            else:
                result[combo] = w
    for token in removals:
        for combo, _ in _expand_token(token):
            result.pop(combo, None)
    if not result:
        raise ValueError(f"范围为空或无法解析: {text!r}")
    return result


def filter_blocked(rng: WeightedRange, dead_cards: Iterable[int]) -> WeightedRange:
    """移除与已知牌（公共牌/自己手牌）冲突的组合。"""
    dead = set(dead_cards)
    return {c: w for c, w in rng.items() if c[0] not in dead and c[1] not in dead}


def range_size(rng: WeightedRange) -> float:
    """范围的加权组合数。"""
    return sum(rng.values())


def range_text(rng: WeightedRange, max_items: int = 20) -> str:
    from .cards import combo_str
    items = sorted(rng, key=lambda c: -rng[c])
    parts = [combo_str(c) if w == 1.0 else f"{combo_str(c)}:{w}" for c, w in
             ((c, rng[c]) for c in items[:max_items])]
    suffix = f" ... 共{len(rng)}个组合" if len(rng) > max_items else ""
    return ", ".join(parts) + suffix
