"""示例：命令行求解一个河牌场景并打印策略摘要。

运行: python examples/solve_river.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto import RiverSolver, parse_cards, parse_range


def main():
    solver = RiverSolver(
        board=parse_cards("AhKd7c3s2h"),
        pot=60,
        stack=140,
        oop_range=parse_range("22+,ATs+,KTs+,QTs+,JTs,T9s,98s,87s,AKo,AQo"),
        ip_range=parse_range("22+,A9s+,KTs+,QTs+,JTs,T9s,98s,AKo,AQo,AJo"),
        bet_sizes=(0.33, 0.75, 1.5),
        seed=1,
    )
    print("求解中（20 万次 MCCFR 迭代）...")
    solver.solve(iterations=200_000)

    nodes = solver.average_strategy()
    print(f"完成，共 {len(nodes)} 个决策节点\n")

    for history, node in sorted(nodes.items(), key=lambda kv: (len(kv[0]), kv[0])):
        print(f"== {node['label']} ==")
        print(f"   动作: {' | '.join(node['actions'])}")
        # 展示部分组合的策略
        items = sorted(node["combos"].items())[:8]
        for combo, probs in items:
            top = max(range(len(probs)), key=lambda i: probs[i])
            print(f"   {combo}: 主策略[{node['actions'][top]}] {probs[top]:.0%}  "
                  f"分布 {' '.join(f'{p:.0%}' for p in probs)}")
        if len(node["combos"]) > 8:
            print(f"   ... 其余 {len(node['combos']) - 8} 个组合省略")
        print()


if __name__ == "__main__":
    main()
