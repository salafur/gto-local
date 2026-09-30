"""示例：从翻前行动线到翻牌圈求解（完整 GTO Wizard 式流程）。

场景：MTT 20bb 有效，BTN 开池 2.2bb，BB 跟注。
翻牌 Kc7d2s，求解 CBet 策略。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto import GameConfig, PostflopSolver, build_spot, parse_cards, parse_range
from gto.ranges import filter_blocked

# 1. 牌桌 + 翻前行动线
cfg = GameConfig(game_type="mtt", stack_bb=20, ante=0.1)
spot = build_spot(cfg, [("SB", "raise", 2.2), ("BB", "call")])
print(spot.description)

# 2. 翻牌圈求解
board = parse_cards("Kc7d2s")
solver = PostflopSolver(
    board=board, pot=spot.pot, stack=spot.stack,
    oop_range=filter_blocked(parse_range(spot.oop_range), board),
    ip_range=filter_blocked(parse_range(spot.ip_range), board),
    bet_sizes=(0.33, 0.75),
    seed=1,
)
print("求解中（30 万迭代，翻牌场景建议 100 万+）...")
solver.solve(iterations=300000,
             progress_cb=lambda d, t: print(f"\r{d}/{t}", end="") if d % 50000 == 0 else None)
print()

# 3. 根节点（BB 先行动）策略
root = solver.root_strategy_matrix("")
acts, _, _ = solver._gen_actions("")
labels = [solver.action_label(k, a) for k, a in acts]
print("\nBB（OOP）翻牌根节点策略（前 10 个组合）：")
for combo, probs in list(root.items())[:10]:
    top = max(range(len(probs)), key=lambda i: probs[i])
    print(f"  {combo}: {labels[top]} {probs[top]*100:.0f}%")
