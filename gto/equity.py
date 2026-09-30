"""胜率（Equity）计算器：蒙特卡洛模拟。

支持 手牌 vs 范围、手牌 vs 手牌，可带 0~5 张公共牌。
"""
from __future__ import annotations

import bisect
import random
from typing import Iterable, Optional, Sequence, Tuple

from .cards import Combo, parse_cards, parse_combo
from .evaluator import evaluate7
from .ranges import WeightedRange, filter_blocked, parse_range


def _weighted_sample(items: Sequence[Combo], cum_weights: Sequence[float], rng: random.Random) -> Combo:
    r = rng.random() * cum_weights[-1]
    return items[bisect.bisect_left(cum_weights, r)]


def equity_vs_range(
    hand: Combo,
    villain_range: WeightedRange,
    board: Sequence[int] = (),
    trials: int = 20000,
    seed: Optional[int] = None,
) -> float:
    """蒙特卡洛估计 hand 对阵 villain_range 的胜率（平分按 0.5 计）。"""
    if len(board) > 5:
        raise ValueError("公共牌最多 5 张")
    rng = random.Random(seed)

    dead = set(hand) | set(board)
    deck = [c for c in range(52) if c not in dead]
    allowed = filter_blocked(villain_range, dead)
    if not allowed:
        raise ValueError("对手范围与已知牌完全冲突")

    combos = list(allowed)
    cum = []
    total = 0.0
    for c in combos:
        total += allowed[c]
        cum.append(total)

    need = 5 - len(board)
    score = 0.0
    for _ in range(trials):
        v = _weighted_sample(combos, cum, rng)
        rest = [c for c in deck if c not in v]
        runout = rng.sample(rest, need) if need else []
        my = evaluate7(tuple(hand) + tuple(board) + tuple(runout))
        op = evaluate7(tuple(v) + tuple(board) + tuple(runout))
        if my > op:
            score += 1.0
        elif my == op:
            score += 0.5
    return score / trials


def equity_vs_hand(
    hero: Combo,
    villain: Combo,
    board: Sequence[int] = (),
    trials: int = 20000,
    seed: Optional[int] = None,
) -> float:
    return equity_vs_range(hero, {villain: 1.0}, board, trials, seed)


def equity_from_strings(
    hand: str,
    villain: str,
    board: str = "",
    trials: int = 20000,
    seed: Optional[int] = None,
) -> float:
    """字符串便捷接口：equity_from_strings("AhAc", "KK") 或 ("AhKh", "random", "2c3d4h")"""
    h = parse_combo(hand)
    b = parse_cards(board) if board.strip() else ()
    if len(villain.strip()) == 4 and "," not in villain and "+" not in villain:
        try:
            return equity_vs_hand(h, parse_combo(villain), b, trials, seed)
        except ValueError:
            pass
    return equity_vs_range(h, parse_range(villain), b, trials, seed)
