"""示例：用 Kuhn 扑克验证 CFR 引擎收敛到纳什均衡。

运行: python examples/kuhn_validation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto.kuhn import CARD_NAMES, KuhnCFR

cfr = KuhnCFR()
cfr.train(100_000)

print(f"博弈值: {cfr.game_value():.4f}（理论 -1/18 ≈ -0.0556）")
print(f"exploitability: {cfr.exploitability():.4f}（理论 0）\n")

print("平均策略（动作: 过牌/下注 或 弃牌/跟注）:")
for info, probs in sorted(cfr.average_strategy().items()):
    card, hist = info.split("|")
    ctx = {"": "先行动", "c": "对手过牌后", "b": "面对下注", "cb": "过牌后面对下注"}[hist]
    print(f"  拿 {card} {ctx:.<8} [{probs[0]:.2f}, {probs[1]:.2f}]")
