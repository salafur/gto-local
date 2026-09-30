"""河牌求解器测试：极化玩具场景。

场景：公共牌 Ah Kh Qh Jh 2c。
- IP 只有 Th9h（凑成皇家同花顺，绝对坚果）
- OOP 只有 8c8d（纯 bluff catcher，永远赢不了）

GTO 结论（直观可验证）：
1. OOP 应该以极高频率过牌（领先下注只会输更多）
2. IP 过牌后应该以极高频率下注（坚果必下注拿价值/逼弃牌）
3. OOP 面对下注应该以极高频率弃牌（跟注/加注必输）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto.cards import parse_cards
from gto.ranges import parse_range
from gto.river import RiverSolver


def _make_solver(seed=7):
    return RiverSolver(
        board=parse_cards("AhKhQhJh2c"),
        pot=100,
        stack=200,
        oop_range=parse_range("8c8d"),
        ip_range=parse_range("Th9h"),
        seed=seed,
    )


def test_nuts_bets_and_bluffcatcher_folds():
    solver = _make_solver()
    solver.solve(iterations=30000)

    # 1. OOP 首轮：过牌频率高
    root = solver.root_strategy_matrix("")
    oop_probs = root["8c8d"]  # 动作: [X, B..., A]
    assert oop_probs[0] > 0.6, f"OOP 应高频过牌: {oop_probs}"

    # 2. IP（OOP 过牌后）：下注频率 > 0.9
    ip_node = solver.root_strategy_matrix("X0")
    ip_probs = ip_node["Th9h"]
    bet_freq = 1.0 - ip_probs[0]
    assert bet_freq > 0.9, f"IP 坚果应高频下注: {ip_probs}"

    # 3. OOP 面对下注：弃牌频率高
    #    找到面对下注的历史节点（X0;B33 之类）
    fold_checked = False
    for history in list(solver._action_cache):
        if history.startswith("X0;B"):
            facing = solver.root_strategy_matrix(history)
            if "8c8d" in facing:
                fold_freq = facing["8c8d"][0]  # 第一个动作是弃牌
                assert fold_freq > 0.7, f"OOP 面对下注应高频弃牌 [{history}]: {facing['8c8d']}"
                fold_checked = True
    assert fold_checked, "没有找到 OOP 面对下注的节点"


def test_solver_deterministic_with_seed():
    s1, s2 = _make_solver(99), _make_solver(99)
    s1.solve(iterations=5000)
    s2.solve(iterations=5000)
    assert s1.root_strategy_matrix("") == s2.root_strategy_matrix("")
