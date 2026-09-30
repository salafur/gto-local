"""HU 短码全下/弃牌纳什均衡（Jam/Fold Nash）。

模型：有效筹码 S bb。BTN(SB) 只有两个动作：全下 S bb 或弃牌；
BB 面对全下只有：跟注或弃牌。这是 HU SNG/MTT 尾局的经典简化模型，
纳什均衡可以用"胜率矩阵 + 最优应对迭代"在本地精确逼近。

方法：
1. 169 种手牌类的两两胜率矩阵（蒙特卡洛，结果缓存到磁盘，只算一次）
2. 给定 SB 全下范围，BB 每手牌选择 EV 更大的应对（跟注/弃牌）；
   给定 BB 跟注范围，SB 每手牌选择 EV 更大的动作（全下/弃牌）。
   反复迭代（fictitious play，带阻尼）直到稳定——该博弈结构下收敛。

EV 定义（单位 bb，含已投盲注的净收益）：
- SB 弃牌: -0.5
- SB 全下, BB 弃牌: +1
- SB 全下, BB 跟注: equity * 2S - S
- BB 弃牌: -1；BB 跟注: equity * 2S - S
"""
from __future__ import annotations

import json
import os
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .cards import RANKS, Combo
from .equity import equity_vs_hand

CACHE_DIR = Path.home() / ".gto-local"

# 手牌类权重：对子 6 组合，同花 4，不同花 12
def hand_weight(label: str) -> int:
    if len(label) == 2:
        return 6
    return 4 if label.endswith("s") else 12


def canonical_hands() -> List[str]:
    """全部 169 种手牌类标签：对子 AA..22，同花/不同花按强度排序。"""
    hands = []
    for r in range(12, -1, -1):
        hands.append(RANKS[r] * 2)  # 对子
    for hi in range(12, -1, -1):
        for lo in range(hi - 1, -1, -1):
            hands.append(RANKS[hi] + RANKS[lo] + "s")
            hands.append(RANKS[hi] + RANKS[lo] + "o")
    return hands


HANDS = canonical_hands()
HAND_INDEX = {h: i for i, h in enumerate(HANDS)}


def label_to_combo(label: str) -> Combo:
    """手牌类标签 -> 代表组合（固定花色，仅用于胜率估计）。

    对子用 红桃+黑桃；同花用全红桃；不同花用 红桃+黑桃。
    """
    if len(label) == 2:
        r = RANKS.index(label[0])
        a, b = r * 4 + 2, r * 4 + 3
    elif label.endswith("s"):
        r1, r2 = RANKS.index(label[0]), RANKS.index(label[1])
        a, b = r1 * 4 + 2, r2 * 4 + 2
    else:
        r1, r2 = RANKS.index(label[0]), RANKS.index(label[1])
        a, b = r1 * 4 + 2, r2 * 4 + 3
    return (min(a, b), max(a, b))


_COMBOS: List[Combo] = [label_to_combo(h) for h in HANDS]


def equity_matrix(trials: int = 200, use_cache: bool = True,
                  seed: int = 20260930) -> List[List[float]]:
    """169x169 胜率矩阵，E[i][j] = 手牌 i 对手牌 j 的胜率（0.5 计平分）。

    只算 i<j 的一半，另一半用 1-E 对称填充（平分各计 0.5 时该对称性精确成立）。
    结果缓存到 ~/.gto-local/equity169_<trials>.json。
    """
    cache_file = CACHE_DIR / f"equity169_{trials}.json"
    n = len(HANDS)
    if use_cache and cache_file.exists():
        data = json.loads(cache_file.read_text())
        if len(data) == n:
            return data

    E = [[0.5] * n for _ in range(n)]
    for i in range(n):
        ci = _COMBOS[i]
        for j in range(i + 1, n):
            cj = _COMBOS[j]
            # 代表组合可能撞牌（同花标签的花色冲突），错开黑桃花色即可
            if ci[0] in cj or ci[1] in cj:
                cj = _shift_combo(cj, ci)
            e = equity_vs_hand(ci, cj, trials=trials, seed=seed + i * 997 + j)
            E[i][j] = e
            E[j][i] = 1.0 - e
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(E))
    return E


def _shift_combo(combo: Combo, avoid: Combo) -> Combo:
    """把组合的花色平移，避开与 avoid 撞牌（保持手牌类不变）。"""
    dead = set(avoid)
    r1, r2 = combo[0] >> 2, combo[1] >> 2
    suited = (combo[0] & 3) == (combo[1] & 3)
    for s1 in range(4):
        for s2 in range(4):
            if suited and s1 != s2:
                continue
            if not suited and r1 != r2 and s1 == s2:
                continue
            if r1 == r2 and s1 == s2:
                continue
            a, b = r1 * 4 + s1, r2 * 4 + s2
            if a not in dead and b not in dead:
                return (min(a, b), max(a, b))
    raise RuntimeError("无法避开撞牌")


def nash_push_fold(stack_bb: float,
                   E: Optional[List[List[float]]] = None,
                   iterations: int = 300) -> Dict[str, Dict[str, float]]:
    """求 HU jam/fold 纳什解。

    返回 {"push": {手牌: 全下频率}, "call": {手牌: 跟注频率}}。
    """
    if stack_bb <= 0:
        raise ValueError("筹码必须大于 0")
    if E is None:
        E = equity_matrix()
    n = len(HANDS)
    S = stack_bb
    w = [hand_weight(h) for h in HANDS]
    w_sum = sum(w)

    push = [1.0] * n
    call = [1.0] * n
    push_acc = [0.0] * n
    call_acc = [0.0] * n
    collect_from = int(iterations * 0.6)  # 后 40% 迭代做平均（fictitious play）

    for t in range(iterations):
        # BB 最优应对：跟注 EV > 弃牌 EV(-1) 则跟注
        new_call = [0.0] * n
        for j in range(n):
            num = 0.0
            den = 0.0
            Ej = E[j]
            for i in range(n):
                wp = w[i] * push[i]
                if wp <= 0:
                    continue
                num += wp * (Ej[i] * 2 * S - S)
                den += wp
            ev_call = num / den if den > 0 else -1.0
            new_call[j] = 1.0 if ev_call > -1.0 else 0.0
        # SB 最优应对：全下 EV > 弃牌 EV(-0.5) 则全下
        new_push = [0.0] * n
        for i in range(n):
            ev = 0.0
            Ei = E[i]
            for j in range(n):
                cj = call[j]
                if cj >= 1.0:
                    ev += w[j] * (Ei[j] * 2 * S - S)
                elif cj <= 0.0:
                    ev += w[j] * 1.0
                else:
                    ev += w[j] * ((1 - cj) * 1.0 + cj * (Ei[j] * 2 * S - S))
            ev /= w_sum
            new_push[i] = 1.0 if ev > -0.5 else 0.0
        # 阻尼更新，避免边界手牌来回震荡
        for k in range(n):
            push[k] = 0.5 * push[k] + 0.5 * new_push[k]
            call[k] = 0.5 * call[k] + 0.5 * new_call[k]
        if t >= collect_from:
            for k in range(n):
                push_acc[k] += push[k]
                call_acc[k] += call[k]

    m = iterations - collect_from
    push_avg = [x / m for x in push_acc]
    call_avg = [x / m for x in call_acc]
    return {
        "push": {HANDS[i]: round(push_avg[i], 4) for i in range(n)},
        "call": {HANDS[i]: round(call_avg[i], 4) for i in range(n)},
    }


def push_call_summary(table: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """汇总：SB 全下比例 / BB 跟注比例（按组合权重加权）。"""
    tw = 0.0
    pw = 0.0
    cw = 0.0
    for h in HANDS:
        wgt = hand_weight(h)
        tw += wgt
        pw += wgt * table["push"][h]
        cw += wgt * table["call"][h]
    return {
        "push_pct": round(pw / tw * 100, 1),
        "call_pct": round(cw / tw * 100, 1),
    }
