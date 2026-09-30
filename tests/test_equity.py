"""胜率计算测试（蒙特卡洛，容差校验）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto.equity import equity_from_strings


class TestKnownEquities:
    def test_aa_vs_kk(self):
        # 经典对局：AA vs KK 约 81%
        e = equity_from_strings("AhAc", "KhKc", trials=20000, seed=42)
        assert 0.77 < e < 0.85, f"AA vs KK 胜率异常: {e}"

    def test_ak_suited_vs_22(self):
        # 经典"抛硬币"：AKs vs 22 约 50%（22 略优）
        e = equity_from_strings("AhKh", "2c2d", trials=20000, seed=42)
        assert 0.45 < e < 0.55, f"AKs vs 22 胜率异常: {e}"

    def test_dominating_hand(self):
        # AK vs AQ 约 73%
        e = equity_from_strings("AhKd", "QcQs", trials=20000, seed=42)
        assert 0.40 < e < 0.50  # AKo vs QQ 约 43%

    def test_flush_draw_on_flop(self):
        # 翻牌圈同花听牌 vs 暗三条：听牌约 26%（三条有葫芦 redraw，听牌不是 35%）
        e = equity_from_strings("AhQh", "KdKc", board="Kh7h2c", trials=20000, seed=42)
        assert 0.20 < e < 0.35

    def test_made_hand_on_river(self):
        # 河牌已成型：葫芦 vs 高牌，接近 100%
        e = equity_from_strings("AhAc", "KdQc", board="AdKc7s2h3c", trials=5000, seed=42)
        assert e > 0.95
