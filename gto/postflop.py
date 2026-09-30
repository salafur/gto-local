"""翻牌/转牌/河牌通用场景求解器：外部采样 MCCFR + 机会节点采样。

输入一个具体场景（3~5 张公共牌、底池、筹码、双方范围、下注尺度），
用 Counterfactual Regret Minimization 求解"从当前街到摊牌"的完整子博弈。

与河牌单街求解的关键区别：当一条街的行动关闭（双方过牌或一方跟注）
而公共牌还未发完时，进入机会节点（chance node）——从剩余牌堆中采样
下一张公共牌，然后继续下一条街的博弈。因此：

- 信息集 = (行动方, 自己的手牌组合, 当前公共牌, 行动历史)
  不同转牌/河牌产生不同的信息集（玩家能观察到发出的公共牌）
- 每次迭代对机会节点只采样一张牌（外部采样对机会节点同样适用）
- 翻牌圈求解需要的迭代数远大于河牌：河牌 ~5-20 万，转牌 ~20-50 万，
  翻牌 ~100 万以上。这是无抽象精确求解的固有代价。

历史编码：一条街内的动作用 ";" 分隔，街道之间用 "|" 分隔。
例如 "X0;B33;C33|X0" 表示：第一条街 过牌/下注33/跟注33，第二条街 过牌（进行中）。
"""
from __future__ import annotations

import bisect
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .cards import Combo, card_str, combo_str
from .evaluator import evaluate7
from .ranges import WeightedRange, filter_blocked

# 动作类型: X=过牌 F=弃牌 C=跟注 B=下注 R=加注 A=全下
Action = Tuple[str, int]  # (类型, 本次投入筹码)

STREET_NAMES = {3: "翻牌圈", 4: "转牌圈", 5: "河牌圈"}

_FULL_DECK = tuple(range(52))


class PostflopSolver:
    """翻牌/转牌/河牌通用 MCCFR 求解器（HU 两人）。"""

    def __init__(
        self,
        board: Sequence[int],
        pot: int,
        stack: int,
        oop_range: WeightedRange,
        ip_range: WeightedRange,
        bet_sizes: Sequence[float] = (0.33, 0.75, 1.5),
        raise_sizes: Sequence[float] = (0.75,),
        max_raises: int = 1,
        seed: Optional[int] = None,
    ):
        if len(board) not in (3, 4, 5):
            raise ValueError(f"公共牌必须是 3/4/5 张（翻牌/转牌/河牌），当前 {len(board)} 张")
        if len(set(board)) != len(board):
            raise ValueError("公共牌有重复")
        self.base_board = tuple(board)
        self.base_street = len(board)  # 3=flop 4=turn 5=river
        self.pot = pot
        self.stack = stack
        self.bet_sizes = tuple(bet_sizes)
        self.raise_sizes = tuple(raise_sizes)
        self.max_raises = max_raises
        self.rng = random.Random(seed)

        # 范围预处理：移除与公共牌冲突的组合
        self.ranges: List[WeightedRange] = [
            filter_blocked(oop_range, board),
            filter_blocked(ip_range, board),
        ]
        for name, r in zip(("OOP", "IP"), self.ranges):
            if not r:
                raise ValueError(f"{name} 范围与公共牌完全冲突")

        self.combos: List[List[Combo]] = [list(r) for r in self.ranges]
        self.weights: List[List[float]] = [
            [r[c] for c in self.combos[i]] for i, r in enumerate(self.ranges)
        ]

        # 每个组合 -> 可用对手组合（无牌冲突）的累积权重表，用于按权重采样
        self._opp_index: List[List[Tuple[List[int], List[float]]]] = [[], []]
        for p in (0, 1):
            for c in self.combos[p]:
                cards = {c[0], c[1]}
                idxs, cum, total = [], [], 0.0
                for j, oc in enumerate(self.combos[1 - p]):
                    if oc[0] in cards or oc[1] in cards:
                        continue
                    total += self.weights[1 - p][j]
                    idxs.append(j)
                    cum.append(total)
                self._opp_index[p].append((idxs, cum))

        # 摊牌牌力缓存：公共牌会随机会节点变化，按 (组合, 公共牌) 记忆化
        self._rank_cache: Dict[Tuple[Combo, Tuple[int, ...]], int] = {}

        # CFR 状态：信息集 -> (遗憾值, 平均策略累计)
        self._regret: Dict[Tuple, List[float]] = {}
        self._strat_sum: Dict[Tuple, List[float]] = {}
        self._action_cache: Dict[str, Tuple[List[Action], List[int], int]] = {}
        self.iterations_done = 0

    # ------------------------------------------------------------------
    # 历史解析与博弈树
    # ------------------------------------------------------------------

    @staticmethod
    def _split(history: str) -> Tuple[List[str], List[str]]:
        """返回 (各街段, 当前街动作 token 列表)。"""
        segs = history.split("|")
        cur = [t for t in segs[-1].split(";") if t]
        return segs, cur

    def _street_of(self, history: str) -> int:
        """当前所在街道（3/4/5）。"""
        return self.base_street + history.count("|")

    def _gen_actions(self, history: str) -> Tuple[List[Action], List[int], int]:
        """生成当前节点可用动作。返回 (动作列表, 本街双方投入, 本街加注次数)。"""
        cached = self._action_cache.get(history)
        if cached is not None:
            return cached

        segs, cur = self._split(history)
        c = [0, 0]
        n_raises = 0
        player = 0
        prior = [0, 0]  # 之前各街双方分别的投入（已到底池，不再属于后手）
        for si, seg in enumerate(segs):
            tokens = [t for t in seg.split(";") if t]
            if si == len(segs) - 1:
                for token in tokens:
                    c[player] += int(token[1:])
                    if token[0] == "R":
                        n_raises += 1
                    player = 1 - player
            else:
                p = 0
                for token in tokens:
                    prior[p] += int(token[1:])
                    p = 1 - p

        me, opp = c[player], c[1 - player]
        to_call = opp - me
        pot_now = self.pot + prior[0] + prior[1] + c[0] + c[1]
        # 剩余筹码 = 场景开始后手 - 之前各街投入 - 本街已投入
        remaining = self.stack - prior[player] - me

        acts: List[Action] = []
        if to_call == 0:
            acts.append(("X", 0))
            if remaining > 0:
                seen = set()
                for pct in self.bet_sizes:
                    amt = min(int(round(pot_now * pct)), remaining)
                    if 0 < amt < remaining and amt not in seen:
                        seen.add(amt)
                        acts.append(("B", amt))
                if remaining not in seen:
                    acts.append(("A", remaining))
        else:
            acts.append(("F", 0))
            acts.append(("C", min(to_call, remaining)))
            if n_raises < self.max_raises and remaining > to_call:
                for r in self.raise_sizes:
                    amt = min(to_call + int(round((pot_now + to_call) * r)), remaining)
                    if to_call < amt < remaining:
                        acts.append(("R", amt))
                if remaining > to_call:
                    acts.append(("A", remaining))

        result = (acts, c, n_raises)
        self._action_cache[history] = result
        return result

    def _street_closed(self, history: str) -> Optional[str]:
        """当前街是否关闭: 'F'=弃牌结束 'S'=行动关闭（跟注或双过牌） None=进行中。"""
        if not history:
            return None
        _, cur = self._split(history)
        if not cur:
            return None
        last = cur[-1]
        if last.startswith("F"):
            return "F"
        if last.startswith("C"):
            return "S"
        if len(cur) >= 2 and cur[-1].startswith("X") and cur[-2].startswith("X"):
            return "S"
        return None

    # ------------------------------------------------------------------
    # MCCFR 主循环
    # ------------------------------------------------------------------

    def _strategy(self, key, n: int) -> List[float]:
        r = self._regret.get(key)
        if r is None:
            r = [0.0] * n
            self._regret[key] = r
            self._strat_sum[key] = [0.0] * n
        pos = 0.0
        for x in r:
            if x > 0:
                pos += x
        if pos <= 0:
            return [1.0 / n] * n
        return [(x / pos if x > 0 else 0.0) for x in r]

    def _rank(self, combo: Combo, board: Tuple[int, ...]) -> int:
        key = (combo, board)
        v = self._rank_cache.get(key)
        if v is None:
            v = evaluate7(combo + board)
            self._rank_cache[key] = v
        return v

    def _utility(self, term: str, invested: List[int], folder: int,
                 tp: int, hc: Combo, vc: Combo, board: Tuple[int, ...]) -> float:
        final_pot = self.pot + invested[0] + invested[1]
        if term == "F":
            received = final_pot if folder != tp else 0
        else:
            rh = self._rank(hc, board)
            rv = self._rank(vc, board)
            if rh > rv:
                received = final_pot
            elif rh == rv:
                received = final_pot / 2
            else:
                received = 0
        return received - invested[tp]

    def _total_invested(self, history: str) -> List[int]:
        """双方从场景开始的总投入（跨所有街）。"""
        invested = [0, 0]
        for seg in history.split("|"):
            player = 0
            for token in seg.split(";"):
                if not token:
                    continue
                invested[player] += int(token[1:])
                player = 1 - player
        return invested

    def _walk(self, history: str, board: Tuple[int, ...], tp: int,
              hc: Combo, vc: Combo, reach_opp: float, reach_self: float) -> float:
        acts, c_street, _ = self._gen_actions(history)

        closed = self._street_closed(history)
        if closed is not None:
            street = self._street_of(history)
            if closed == "F" or street >= 5:
                invested = self._total_invested(history)
                folder = -1
                if closed == "F":
                    _, cur = self._split(history)
                    folder = (len(cur) - 1) % 2
                return self._utility(closed, invested, folder, tp, hc, vc, board)
            # 机会节点：采样下一张公共牌，进入下一条街
            dead = set(board)
            dead.add(hc[0])
            dead.add(hc[1])
            deck = [x for x in _FULL_DECK if x not in dead]
            nxt = deck[self.rng.randrange(len(deck))]
            return self._walk(history + "|", board + (nxt,), tp, hc, vc,
                              reach_opp, reach_self)

        _, cur = self._split(history)
        player = len(cur) % 2
        key = (player, hc if player == tp else vc, board, history)
        sigma = self._strategy(key, len(acts))

        def append(token: str) -> str:
            if not history or history.endswith("|"):
                return history + token
            return history + ";" + token

        if player == tp:
            utils = []
            node_util = 0.0
            for i, (kind, amt) in enumerate(acts):
                u = self._walk(append(f"{kind}{amt}"), board, tp, hc, vc,
                               reach_opp, reach_self * sigma[i])
                utils.append(u)
                node_util += sigma[i] * u
            reg = self._regret[key]
            strat = self._strat_sum[key]
            for i in range(len(acts)):
                reg[i] += (utils[i] - node_util) * reach_opp
                strat[i] += sigma[i] * reach_self
            return node_util
        else:
            r = self.rng.random()
            acc = 0.0
            i = len(acts) - 1
            for k, p in enumerate(sigma):
                acc += p
                if r <= acc:
                    i = k
                    break
            kind, amt = acts[i]
            return self._walk(append(f"{kind}{amt}"), board, tp, hc, vc,
                              reach_opp * sigma[i], reach_self)

    def solve(self, iterations: int = 200000,
              progress_cb: Optional[Callable[[int, int], None]] = None) -> None:
        """运行 MCCFR。每次迭代：交替遍历方 -> 等概率采样其一个组合 ->
        按权重采样对手组合 -> 一次外部采样树遍历（含机会节点采样）。"""
        cb_every = max(1, iterations // 100)
        for it in range(iterations):
            tp = it & 1
            ci = self.rng.randrange(len(self.combos[tp]))
            hc = self.combos[tp][ci]
            idxs, cum = self._opp_index[tp][ci]
            if not cum:
                continue
            j = bisect.bisect_left(cum, self.rng.random() * cum[-1])
            vc = self.combos[1 - tp][idxs[min(j, len(idxs) - 1)]]
            self._walk("", self.base_board, tp, hc, vc, 1.0, self.weights[tp][ci])
            self.iterations_done += 1
            if progress_cb and (it % cb_every == 0 or it == iterations - 1):
                progress_cb(it + 1, iterations)

    # ------------------------------------------------------------------
    # 结果导出
    # ------------------------------------------------------------------

    @staticmethod
    def action_label(kind: str, amt: int, pot_now: int = 0) -> str:
        if kind == "X":
            return "过牌"
        if kind == "F":
            return "弃牌"
        if kind == "C":
            return f"跟注 {amt}"
        if kind == "B":
            return f"下注 {amt}"
        if kind == "R":
            return f"加注 {amt}"
        return f"全下 {amt}"

    def history_label(self, history: str) -> str:
        street = self._street_of(history)
        street_name = STREET_NAMES.get(street, f"{street}牌圈")
        if not history or history.endswith("|"):
            return f"{street_name} · OOP 先行动"
        names = {"X": "过牌", "F": "弃牌", "C": "跟注"}
        _, cur = self._split(history)
        parts = []
        for t in cur:
            kind = t[0]
            if kind in names:
                parts.append(names[kind])
            elif kind == "B":
                parts.append(f"下注{t[1:]}")
            elif kind == "R":
                parts.append(f"加注{t[1:]}")
            else:
                parts.append(f"全下{t[1:]}")
        actor = "IP" if len(parts) % 2 == 1 else "OOP"
        return f"{street_name} · {actor} 行动（本街 {' / '.join(parts)} 后）"

    @staticmethod
    def node_id(board: Tuple[int, ...], history: str) -> str:
        return "".join(card_str(c) for c in board) + "|" + history

    def average_strategy(self) -> Dict:
        """导出所有信息集的平均策略。

        返回 {node_id: {"label", "street", "board", "history", "player",
                        "player_name", "actions": [...], "combos": {combo: [p...]}}}
        node_id = 公共牌 + "|" + 历史（同一历史在不同公共牌下是不同节点）。
        """
        out: Dict = {}
        for (player, combo, board, history), strat in self._strat_sum.items():
            total = sum(strat)
            if total <= 0:
                continue
            acts, _, _ = self._gen_actions(history)
            probs = [x / total for x in strat]
            nid = self.node_id(board, history)
            entry = out.setdefault(nid, {
                "label": self.history_label(history),
                "street": self._street_of(history),
                "board": "".join(card_str(c) for c in board),
                "history": history,
                "player": player,
                "player_name": "OOP" if player == 0 else "IP",
                "actions": [self.action_label(k, a) for k, a in acts],
                "combos": {},
            })
            entry["combos"][combo_str(combo)] = [round(p, 4) for p in probs]
        return out

    def root_strategy_matrix(self, history: str = "") -> Dict[str, List[float]]:
        """便捷接口：取某个历史节点下各组合的平均策略（跨公共牌汇总时不适用，
        仅供单街/河牌场景或测试使用）。"""
        result = {}
        for (player, combo, board, h), strat in self._strat_sum.items():
            if h != history:
                continue
            total = sum(strat)
            if total > 0:
                result[combo_str(combo)] = [x / total for x in strat]
        return result
