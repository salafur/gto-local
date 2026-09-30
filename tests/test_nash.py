"""Nash 全下/弃牌表测试。

用合成胜率矩阵（牌力严格有序）验证结构性性质，避免依赖蒙特卡洛噪声：
- 筹码越深全下范围越窄（单调性）
- 最强牌永远全下/跟注，最弱牌深筹码时永远弃牌
- BB 跟注范围始终窄于 SB 全下范围
另有一个真实胜率矩阵的粗粒度冒烟测试。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from gto.nash import (HANDS, HAND_INDEX, equity_matrix, nash_push_fold,
                      push_call_summary)


def _ordered_matrix():
    """合成胜率矩阵：HANDS 列表顺序即强度（索引越小越强）。"""
    n = len(HANDS)
    E = [[0.5] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i < j:
                E[i][j] = 0.75  # 强对弱 75%
            elif i > j:
                E[i][j] = 0.25
    return E


def _frac(table, key):
    return sum(table[key].values()) / len(table[key])


class TestStructural:
    E = _ordered_matrix()

    def test_push_range_shrinks_with_stack(self):
        t2 = nash_push_fold(2, E=self.E)
        t5 = nash_push_fold(5, E=self.E)
        t10 = nash_push_fold(10, E=self.E)
        t20 = nash_push_fold(20, E=self.E)
        f = [_frac(t, "push") for t in (t2, t5, t10, t20)]
        assert f[0] >= f[1] >= f[2] >= f[3], f"全下比例应随筹码单调不增: {f}"
        assert f[0] > 0.6, "2bb 全下范围应显著宽于深筹码"
        assert f[3] < 0.5, "20bb 全下范围应显著收窄"

    def test_strongest_always_push_deep(self):
        t = nash_push_fold(15, E=self.E)
        strongest = HANDS[0]
        assert t["push"][strongest] == pytest.approx(1.0)
        # 注：合成矩阵中深筹码全下最弱牌也可能 +EV（纯靠弃牌率），
        # 因此"最弱牌深筹码弃牌"只在真实胜率矩阵测试中验证。

    def test_call_not_wider_than_push_shallow(self):
        # 浅筹码时 SB 全下很宽，BB 跟注范围应显著更窄
        t = nash_push_fold(20, E=self.E)
        assert _frac(t, "call") < _frac(t, "push"), \
            f"20bb 跟注({ _frac(t,'call'):.2f})应窄于全下({_frac(t,'push'):.2f})"

    def test_summary_percentages(self):
        t = nash_push_fold(2, E=self.E)
        s = push_call_summary(t)
        assert 0 <= s["call_pct"] <= 100
        assert 0 < s["push_pct"] <= 100


class TestRealMatrixSmoke:
    """真实胜率矩阵粗粒度验证（低 trials 快速跑）。"""

    @pytest.fixture(scope="class")
    def matrix(self):
        return equity_matrix(trials=100, use_cache=False)

    def test_aa_always_push_and_call(self, matrix):
        t = nash_push_fold(15, E=matrix)
        assert t["push"]["AA"] == pytest.approx(1.0)
        assert t["call"]["AA"] == pytest.approx(1.0)

    def test_72o_fold_deep(self, matrix):
        t = nash_push_fold(15, E=matrix)
        assert t["push"]["72o"] < 0.05

    def test_push_monotonic_real(self, matrix):
        f5 = _frac(nash_push_fold(5, E=matrix), "push")
        f15 = _frac(nash_push_fold(15, E=matrix), "push")
        assert f5 > f15, f"5bb 全下应显著宽于 15bb: {f5:.2f} vs {f15:.2f}"

    def test_push_any_two_at_1bb(self, matrix):
        # 1bb 时 SB 只需再投 0.5bb 去赢 1.5bb，任何牌全下都是 +EV
        t = nash_push_fold(1, E=matrix)
        assert _frac(t, "push") >= 0.98, f"1bb 应全范围全下: {_frac(t, 'push'):.2f}"
