"""HU 翻前模块测试：配置、行动线换算、参考范围图表。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from gto.preflop import (BB_3BET, BB_CALL_VS_RAISE, BB_CHECK_VS_LIMP,
                         SB_LIMP, SB_RFI, GameConfig, build_spot,
                         next_actions)
from gto.ranges import parse_range, range_size


class TestCharts:
    """参考范围图表必须是合法的范围语法，且大小在合理区间。"""

    def test_sb_rfi_size(self):
        r = parse_range(SB_RFI)
        pct = range_size(r) / 1326 * 100
        assert 45 < pct < 75, f"SB RFI 约 50-70% 合理，当前 {pct:.1f}%"

    def test_bb_defend_vs_raise(self):
        call = parse_range(BB_CALL_VS_RAISE)
        threebet = parse_range(BB_3BET)
        # 3bet 应显著窄于跟注，且两者有大量重叠设计（3bet 手牌也在继续范围内）
        assert range_size(threebet) < range_size(call) * 0.5

    def test_bb_check_vs_limp(self):
        check = parse_range(BB_CHECK_VS_LIMP)
        # 过牌范围应明显宽于 iso 加注范围
        assert range_size(check) > 600

    def test_sb_limp_no_overlap_with_rfi(self):
        limp = parse_range(SB_LIMP)
        rfi = parse_range(SB_RFI)
        overlap = set(limp) & set(rfi)
        assert not overlap, f"limp 与 RFI 范围不应重叠: {overlap}"


class TestBuildSpot:
    def test_srp_line(self):
        cfg = GameConfig(game_type="cash", stack_bb=100)
        spot = build_spot(cfg, [("SB", "raise", 2.5), ("BB", "call")])
        assert not spot.ended
        assert spot.pot_bb == pytest.approx(5.0)
        assert spot.stack_bb == pytest.approx(97.5)
        assert spot.pot == 500
        assert spot.stack == 9750
        assert "BTN(SB) 加注" in spot.description
        # 范围自动带出
        assert spot.ip_range == SB_RFI
        assert spot.oop_range == BB_CALL_VS_RAISE

    def test_limp_pot(self):
        cfg = GameConfig(game_type="cash", stack_bb=100)
        spot = build_spot(cfg, [("SB", "call"), ("BB", "check")])
        assert not spot.ended
        assert spot.pot_bb == pytest.approx(2.0)
        assert spot.stack_bb == pytest.approx(99.0)

    def test_three_bet_pot(self):
        cfg = GameConfig(game_type="cash", stack_bb=100)
        spot = build_spot(cfg, [("SB", "raise", 2.5),
                                ("BB", "raise", 10.0),
                                ("SB", "call")])
        assert not spot.ended
        assert spot.pot_bb == pytest.approx(20.0)
        assert spot.stack_bb == pytest.approx(90.0)
        assert spot.oop_range == BB_3BET

    def test_mtt_ante_in_pot(self):
        cfg = GameConfig(game_type="mtt", stack_bb=20, ante=0.1)
        spot = build_spot(cfg, [("SB", "raise", 2.2), ("BB", "call")])
        assert not spot.ended
        # 底池 = 2.2 + 2.2 + 0.2(前注)
        assert spot.pot_bb == pytest.approx(4.6)
        assert spot.stack_bb == pytest.approx(17.7)

    def test_fold_ends_preflop(self):
        cfg = GameConfig(stack_bb=100)
        spot = build_spot(cfg, [("SB", "raise", 3), ("BB", "fold")])
        assert spot.ended
        assert "弃牌" in spot.reason

    def test_allin_ends_preflop(self):
        cfg = GameConfig(game_type="mtt", stack_bb=10)
        spot = build_spot(cfg, [("SB", "raise", 10), ("BB", "call")])
        assert spot.ended
        assert "全下" in spot.reason

    def test_invalid_min_raise(self):
        cfg = GameConfig(stack_bb=100)
        with pytest.raises(ValueError):
            # SB 开池加注到 1.5bb < 2bb 最小加注
            build_spot(cfg, [("SB", "raise", 1.5), ("BB", "call")])


class TestNextActions:
    def test_opening_options(self):
        cfg = GameConfig(stack_bb=100)
        opts = next_actions(cfg, [])
        actions = {(o["actor"], o["action"]) for o in opts}
        assert ("SB", "fold") in actions
        assert ("SB", "call") in actions
        assert ("SB", "raise") in actions

    def test_facing_raise_options(self):
        cfg = GameConfig(stack_bb=100)
        opts = next_actions(cfg, [("SB", "raise", 2.5)])
        actions = {(o["actor"], o["action"]) for o in opts}
        assert actions == {("BB", "fold"), ("BB", "call"), ("BB", "raise")}

    def test_after_call_line_ends(self):
        cfg = GameConfig(stack_bb=100)
        opts = next_actions(cfg, [("SB", "raise", 2.5), ("BB", "call")])
        assert opts == []

    def test_facing_allin(self):
        cfg = GameConfig(game_type="mtt", stack_bb=10)
        opts = next_actions(cfg, [("SB", "raise", 10)])
        actions = {(o["actor"], o["action"]) for o in opts}
        assert actions == {("BB", "fold"), ("BB", "call")}

    def test_limp_then_bb_options(self):
        cfg = GameConfig(stack_bb=100)
        opts = next_actions(cfg, [("SB", "call", None)])
        actions = {(o["actor"], o["action"]) for o in opts}
        assert actions == {("BB", "check"), ("BB", "raise")}
