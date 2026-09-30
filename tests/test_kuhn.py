"""Kuhn 扑克：CFR 引擎正确性验证。

CFR 收敛后必须逼近已知纳什均衡：
- 博弈值 ≈ -1/18 ≈ -0.0556（P0 视角）
- exploitability ≈ 0
- 关键策略不变量：P1 拿 K 面对下注总是跟注、拿 J 总是弃牌
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto.kuhn import KuhnCFR


def test_cfr_converges_to_nash():
    cfr = KuhnCFR()
    cfr.train(100_000)

    value = cfr.game_value()
    expl = cfr.exploitability()

    assert abs(value - (-1 / 18)) < 0.01, f"博弈值偏离纳什: {value}"
    assert expl < 0.025, f"exploitability 过大: {expl}"


def test_nash_strategy_invariants():
    cfr = KuhnCFR()
    cfr.train(100_000)
    sigma = cfr.average_strategy()

    # P1 拿 K 面对下注：跟注频率 ≈ 1（infoset "K|b"，动作 [f, c]）
    assert sigma["K|b"][1] > 0.95, f"P1 K 面对下注应总是跟注: {sigma['K|b']}"

    # P1 拿 J 面对下注：弃牌频率 ≈ 1
    assert sigma["J|b"][0] > 0.95, f"P1 J 面对下注应总是弃牌: {sigma['J|b']}"

    # P1 拿 Q 面对下注：跟注 ≈ 1/3
    call_q = sigma["Q|b"][1]
    assert abs(call_q - 1 / 3) < 0.08, f"P1 Q 跟注频率应≈1/3: {call_q}"

    # P0 先行动：纳什均衡中 K 下注频率 = 3α、J 下注频率 = α（α∈[0,1/3] 不唯一），
    # 不变量是"K 的下注频率显著高于 J，且比例约为 3 倍"
    bet_k = sigma["K|"][1]
    bet_j = sigma["J|"][1]
    assert bet_k > bet_j + 0.1, f"K 下注频率应显著高于 J: K={bet_k}, J={bet_j}"
    assert bet_j < 0.4, f"J 下注频率应较低(α≤1/3): {bet_j}"
