"""Kuhn 扑克：CFR 引擎正确性验证器。

Kuhn 扑克是最小的扑克博弈：3 张牌（J/Q/K），每人 1 张，底池 2（各下 1 ante），
一轮下注。它有解析形式的纳什均衡（以 α∈[0,1/3] 参数化）：
  P1: J 以 α 下注, K 以 3α 下注, Q 总是过牌
  P2(面对下注): J 弃牌, Q 以 1/3 跟注, K 总是跟注
  P2(P1过牌后): J 以 1/3 下注, Q 过牌, K 总是下注
  P1(过牌后面对下注): J 弃牌, Q 以 α+1/3 跟注, K 跟注
博弈值 = -1/18 ≈ -0.0556（P1 期望收益）

如果我们的 vanilla CFR 收敛后博弈值 ≈ -1/18 且 exploitability ≈ 0，
说明 CFR 引擎实现正确 —— 这是所有扑克 AI 论文验证求解器的标准做法。
"""
from __future__ import annotations

from itertools import permutations
from typing import Dict, List, Tuple

CARDS = [0, 1, 2]  # J, Q, K
CARD_NAMES = ["J", "Q", "K"]


def _terminal_utility(history: str, cards: Tuple[int, int], pot_contrib=(1, 1)) -> float:
    """返回 P0 的净收益。history 由 'c'(过牌/跟注) 和 'b'(下注) 组成。"""
    c0, c1 = pot_contrib
    if history in ("cc", "cbc", "bc"):  # 摊牌
        # bc: P0 下注 P1 跟注；cbc: P0 过牌 P1 下注 P0 跟注；cc: 双过牌
        if history == "bc":
            c0, c1 = 2, 2
        elif history == "cbc":
            c0, c1 = 2, 2
        win = 1 if cards[0] > cards[1] else -1
        return win * (c1)  # P0 净赢对手投入的部分
    if history == "bf":   # P0 下注，P1 弃牌
        return 1.0
    if history == "cbf":  # P0 过牌，P1 下注，P0 弃牌
        return -1.0
    raise ValueError(f"非终局历史: {history}")


def _is_terminal(history: str) -> bool:
    return history in ("cc", "cbc", "bc", "bf", "cbf")


def _actions(history: str) -> List[str]:
    if history.endswith("b"):
        return ["f", "c"]  # 面对下注：弃牌/跟注
    return ["c", "b"]      # 无下注：过牌/下注


class KuhnCFR:
    """标准 vanilla CFR（全树遍历），用于 Kuhn 扑克。"""

    def __init__(self):
        self.regret: Dict[str, List[float]] = {}
        self.strategy_sum: Dict[str, List[float]] = {}
        self.deals = list(permutations(CARDS, 2))  # 6 种发牌

    def _infoset(self, card: int, history: str) -> str:
        return f"{CARD_NAMES[card]}|{history}"

    def _strategy(self, info: str, n_actions: int) -> List[float]:
        r = self.regret.get(info)
        if r is None:
            r = [0.0] * n_actions
            self.regret[info] = r
            self.strategy_sum[info] = [0.0] * n_actions
        pos = [max(x, 0.0) for x in r]
        s = sum(pos)
        return [x / s for x in pos] if s > 0 else [1.0 / n_actions] * n_actions

    def cfr(self, history: str, cards: Tuple[int, int], p0: float, p1: float) -> float:
        """返回 P0 在当前节点的期望收益。p0/p1 为双方到达概率。"""
        if _is_terminal(history):
            return _terminal_utility(history, cards)

        player = len(history) % 2
        info = self._infoset(cards[player], history)
        acts = _actions(history)
        sigma = self._strategy(info, len(acts))

        utils, node_util = [], 0.0
        for i, a in enumerate(acts):
            if player == 0:
                u = self.cfr(history + a, cards, p0 * sigma[i], p1)
            else:
                u = self.cfr(history + a, cards, p0, p1 * sigma[i])
            utils.append(u)
            node_util += sigma[i] * u

        # 遗憾值更新：对行动方而言的"反事实价值"
        for i in range(len(acts)):
            if player == 0:
                self.regret[info][i] += (utils[i] - node_util) * p1
                self.strategy_sum[info][i] += sigma[i] * p0
            else:
                # P1 的收益 = -P0 收益
                self.regret[info][i] += (node_util - utils[i]) * p0
                self.strategy_sum[info][i] += sigma[i] * p1
        return node_util

    def train(self, iterations: int) -> None:
        for _ in range(iterations):
            for cards in self.deals:
                self.cfr("", cards, 1.0, 1.0)

    def average_strategy(self) -> Dict[str, List[float]]:
        result = {}
        for info, s in self.strategy_sum.items():
            total = sum(s)
            n = len(s)
            result[info] = [x / total for x in s] if total > 0 else [1.0 / n] * n
        return result

    def game_value(self, strategy: Dict[str, List[float]] = None) -> float:
        """平均策略下 P0 的期望收益（纳什均衡时应为 -1/18）。"""
        sigma = strategy or self.average_strategy()

        def walk(history, cards):
            if _is_terminal(history):
                return _terminal_utility(history, cards)
            player = len(history) % 2
            info = self._infoset(cards[player], history)
            acts = _actions(history)
            probs = sigma.get(info) or [1.0 / len(acts)] * len(acts)
            return sum(p * walk(history + a, cards) for p, a in zip(probs, acts))

        return sum(walk("", cards) for cards in self.deals) / len(self.deals)

    def exploitability(self) -> float:
        """纳什利用度：双方各自换最优应对能多赢多少之和的一半。0 = 完美均衡。

        最优应对（Best Response）通过在 BR 方的所有纯策略上枚举求得，
        保证 BR 在同一信息集（自己的牌+历史）上只能选择同一个动作，
        不能"透视"对手的牌。
        """
        from itertools import product

        sigma = self.average_strategy()

        def best_response_value(br_player: int) -> float:
            # 收集 BR 方的所有信息集
            def collect(history, infosets):
                if _is_terminal(history):
                    return
                player = len(history) % 2
                if player == br_player:
                    infosets.add(history)
                    for a in _actions(history):
                        collect(history + a, infosets)
                else:
                    for a in _actions(history):
                        collect(history + a, infosets)

            histories: set = set()
            collect("", histories)
            histories = sorted(histories)

            def eval_pure(assignment) -> float:
                def walk(history, cards):
                    if _is_terminal(history):
                        u = _terminal_utility(history, cards)
                        return u if br_player == 0 else -u
                    player = len(history) % 2
                    acts = _actions(history)
                    if player == br_player:
                        card = cards[br_player]
                        key = self._infoset(card, history)
                        a = acts[assignment[(card, history)]]
                        return walk(history + a, cards)
                    info = self._infoset(cards[player], history)
                    probs = sigma.get(info) or [1.0 / len(acts)] * len(acts)
                    return sum(p * walk(history + a, cards) for p, a in zip(probs, acts))

                return sum(walk("", cards) for cards in self.deals) / len(self.deals)

            # 信息集 = (牌, 历史)；枚举所有纯策略
            keys = [(c, h) for c in CARDS for h in histories]
            best = float("-inf")
            for bits in product([0, 1], repeat=len(keys)):
                assignment = dict(zip(keys, bits))
                best = max(best, eval_pure(assignment))
            return best

        v = self.game_value()
        br0 = best_response_value(0)
        br1 = best_response_value(1)
        return ((br0 - v) + (br1 - (-v))) / 2
