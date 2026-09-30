"""河牌场景 GTO 求解器：外部采样 MCCFR。

输入一个具体场景（公共牌、底池、筹码、双方范围、可用下注尺度），
用 Counterfactual Regret Minimization 迭代逼近纳什均衡策略。

算法说明（面试/学习向）：
- 每个"信息集"= (行动方, 自己的两张手牌, 行动历史)，不做任何抽象，逐组合求解
- 每次迭代：选定一个遍历方，遍历其范围内每个组合，按权重采样一个对手组合，
  在对手节点按当前策略采样动作（外部采样），在自己节点展开所有动作
- 自己节点更新累计遗憾值（regret matching 产生当前策略）与平均策略
- 平均策略随迭代次数增加收敛到纳什均衡（两人零和博弈下 CFR 保证收敛）

由于所有下注额度由配置决定，行动历史唯一确定底池/筹码状态，
因此按历史字符串缓存动作列表，避免重复计算。
"""
from __future__ import annotations

import bisect
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .cards import Combo, combo_str, parse_cards
from .evaluator import evaluate7
from .ranges import WeightedRange, filter_blocked, parse_range

# 动作类型: X=过牌 F=弃牌 C=跟注 B=下注 R=加注 A=全下
Action = Tuple[str, int]  # (类型, 本次投入筹码)


class RiverSolver:
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
        if len(board) != 5:
            raise ValueError("河牌场景需要 5 张公共牌")
        self.board = tuple(board)
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
        self.weights: List[List[float]] = [[r[c] for c in self.combos[i]] for i, r in enumerate(self.ranges)]

        # 每个组合预计算牌力（公共牌固定，只需算一次）
        self.rank: Dict[Combo, int] = {}
        for r in self.ranges:
            for c in r:
                self.rank[c] = evaluate7(c + self.board)

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

        # CFR 状态：信息集 -> (动作列表, 遗憾值, 平均策略累计)
        self._regret: Dict[Tuple, List[float]] = {}
        self._strat_sum: Dict[Tuple, List[float]] = {}
        self._action_cache: Dict[str, List[Tuple[str, List[Action]]]] = {}
        self.iterations_done = 0

    # ------------------------------------------------------------------
    # 博弈树
    # ------------------------------------------------------------------

    def _gen_actions(self, history: str) -> Tuple[List[Action], List[int], int]:
        """生成当前节点可用动作（按历史缓存，同一历史状态必然相同）。"""
        cached = self._action_cache.get(history)
        if cached is not None:
            return cached

        # 重放历史得到筹码状态
        c = [0, 0]
        n_raises = 0
        player = 0
        for token in history.split(";"):
            if not token:
                continue
            kind, amt = token[0], int(token[1:])
            c[player] += amt
            if kind == "R":
                n_raises += 1
            player = 1 - player

        me, opp = c[player], c[1 - player]
        to_call = opp - me
        pot_now = self.pot + c[0] + c[1]
        remaining = self.stack - me

        acts: List[Action] = []
        if to_call == 0:
            acts.append(("X", 0))
            seen = set()
            for pct in self.bet_sizes:
                amt = min(int(round(pot_now * pct)), remaining)
                if 0 < amt < remaining and amt not in seen:
                    seen.add(amt)
                    acts.append(("B", amt))
            if remaining > 0 and remaining not in seen:
                acts.append(("A", remaining))
        else:
            acts.append(("F", 0))
            acts.append(("C", to_call))
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

    @staticmethod
    def _terminal(history: str) -> Optional[str]:
        """终局类型: 'F' 一方弃牌 / 'S' 摊牌 / None 未结束。"""
        if not history:
            return None
        toks = history.split(";")
        last = toks[-1]
        if last.startswith("F"):
            return "F"
        if last.startswith("C"):
            return "S"
        if len(toks) >= 2 and toks[-1].startswith("X") and toks[-2].startswith("X"):
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
        pos_sum = 0.0
        for x in r:
            if x > 0:
                pos_sum += x
        if pos_sum <= 0:
            return [1.0 / n] * n
        return [(x / pos_sum if x > 0 else 0.0) for x in r]

    def _utility(self, term: str, c: List[int], folder: int, tp: int, hc: Combo, vc: Combo) -> float:
        final_pot = self.pot + c[0] + c[1]
        if term == "F":
            received = final_pot if folder != tp else 0
        else:
            rh, rv = self.rank[hc], self.rank[vc]
            if rh > rv:
                received = final_pot
            elif rh == rv:
                received = final_pot / 2
            else:
                received = 0
        return received - c[tp]

    def _walk(self, history: str, tp: int, hc: Combo, vc: Combo,
              reach_opp: float, reach_self: float) -> float:
        c_state = self._gen_actions(history)
        acts, c, n_raises = c_state

        term = self._terminal(history)
        if term is not None:
            folder = -1
            if term == "F":
                # 弃牌方 = 最后一个行动的玩家
                folder = (len(history.split(";")) - 1) % 2
            return self._utility(term, c, folder, tp, hc, vc)

        player = len([t for t in history.split(";") if t]) % 2
        key = (player, hc if player == tp else vc, history)
        sigma = self._strategy(key, len(acts))

        if player == tp:
            utils = []
            node_util = 0.0
            for i, (kind, amt) in enumerate(acts):
                token = f"{history};{kind}{amt}" if history else f"{kind}{amt}"
                u = self._walk(token, tp, hc, vc, reach_opp, reach_self * sigma[i])
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
            i = 0
            for k, p in enumerate(sigma):
                acc += p
                if r <= acc:
                    i = k
                    break
            else:
                i = len(acts) - 1
            kind, amt = acts[i]
            token = f"{history};{kind}{amt}" if history else f"{kind}{amt}"
            return self._walk(token, tp, hc, vc, reach_opp * sigma[i], reach_self)

    def solve(self, iterations: int = 200000,
              progress_cb: Optional[Callable[[int, int], None]] = None) -> None:
        """运行 MCCFR。

        每次迭代：交替选定遍历方 -> 等概率采样其一个组合（保证低频组合也被充分训练）
        -> 按权重采样对手组合 -> 一次外部采样树遍历。
        信息集策略按组合分别维护，组合权重只影响平均策略的累计权重。
        """
        for it in range(iterations):
            tp = it & 1
            ci = self.rng.randrange(len(self.combos[tp]))
            hc = self.combos[tp][ci]
            idxs, cum = self._opp_index[tp][ci]
            if not cum:
                continue
            j = bisect.bisect_left(cum, self.rng.random() * cum[-1])
            vc = self.combos[1 - tp][idxs[min(j, len(idxs) - 1)]]
            self._walk("", tp, hc, vc, 1.0, self.weights[tp][ci])
            self.iterations_done += 1
            if progress_cb and (it % 2000 == 0 or it == iterations - 1):
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

    @staticmethod
    def history_label(history: str) -> str:
        if not history:
            return "OOP 先行动"
        names = {"X": "过牌", "F": "弃牌", "C": "跟注"}
        parts = []
        for t in history.split(";"):
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
        return f"{actor} 行动（{' / '.join(parts)} 后）"

    def average_strategy(self) -> Dict:
        """导出所有信息集的平均策略。

        返回 {history_label: {"player": 0/1, "actions": [标签...],
                              "combos": {"AhKd": [p1, p2, ...]}}}
        """
        out: Dict = {}
        for (player, combo, history), strat in self._strat_sum.items():
            total = sum(strat)
            if total <= 0:
                continue
            acts, _, _ = self._gen_actions(history)
            probs = [x / total for x in strat]
            label = self.history_label(history)
            entry = out.setdefault(history, {
                "label": label,
                "player": player,
                "player_name": "OOP" if player == 0 else "IP",
                "actions": [self.action_label(k, a) for k, a in acts],
                "combos": {},
            })
            entry["combos"][combo_str(combo)] = [round(p, 4) for p in probs]
        return out

    def root_strategy_matrix(self, history: str = "") -> Dict[str, List[float]]:
        """便捷接口：取某个历史节点下各组合的平均策略。"""
        result = {}
        for (player, combo, h), strat in self._strat_sum.items():
            if h != history:
                continue
            total = sum(strat)
            if total > 0:
                result[combo_str(combo)] = [x / total for x in strat]
        return result
