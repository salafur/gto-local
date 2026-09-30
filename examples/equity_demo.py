"""示例：胜率计算。

运行: python examples/equity_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto import equity_from_strings

CASES = [
    ("AhAc", "KK", "", "AA vs KK（翻前）"),
    ("AhKh", "2c2d", "", "AKs vs 22（经典抛硬币）"),
    ("AhQh", "KdKc", "Kh7h2c", "同花听牌 vs 暗三条（翻牌圈）"),
    ("AcAd", "random", "Kd7c2s", "AA vs 随机牌（翻牌圈）"),
]

for hand, villain, board, desc in CASES:
    e = equity_from_strings(hand, villain, board, trials=20000, seed=42)
    print(f"{desc:.<40} {e:.1%}")
