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


# ===========================================================================
# 6max / 9max：多位置桌型（翻后仍为 HU）
# ===========================================================================

from gto.preflop import (BB_DEFEND_VS_EARLY, CALL_VS_3BET, FLAT_VS_RFI,
                         GENERIC_LIMP, RFI_BTN, RFI_UTG, THREEBET_STD,
                         THREEBET_VS_EARLY, postflop_order)


class TestTableSizes:
    def test_positions(self):
        assert GameConfig(table_size=2).positions == ("SB", "BB")
        assert GameConfig(table_size=6).positions == ("UTG", "HJ", "CO", "BTN", "SB", "BB")
        assert len(GameConfig(table_size=9).positions) == 9

    def test_invalid_table_size(self):
        with pytest.raises(ValueError):
            GameConfig(table_size=5)

    def test_postflop_order_hu(self):
        # HU：BTN=SB，翻后 BB 先行动
        assert postflop_order(GameConfig(table_size=2)) == ("BB", "SB")

    def test_postflop_order_6max(self):
        assert postflop_order(GameConfig(table_size=6)) == ("SB", "BB", "UTG", "HJ", "CO", "BTN")


class TestSixMaxSpots:
    def test_utg_open_btn_call(self):
        cfg = GameConfig(table_size=6, stack_bb=100)
        line = [("UTG", "raise", 2.2), ("HJ", "fold"), ("CO", "fold"),
                ("BTN", "call"), ("SB", "fold"), ("BB", "fold")]
        spot = build_spot(cfg, line)
        assert not spot.ended
        # 底池 = 2.2*2 + 0.5(SB) + 1(BB)
        assert spot.pot_bb == pytest.approx(5.9)
        assert spot.stack_bb == pytest.approx(97.8)
        assert spot.oop_pos == "UTG" and spot.ip_pos == "BTN"
        assert spot.oop_range == RFI_UTG
        assert spot.ip_range == FLAT_VS_RFI

    def test_btn_open_bb_call(self):
        cfg = GameConfig(table_size=6, stack_bb=100)
        line = [("UTG", "fold"), ("HJ", "fold"), ("CO", "fold"),
                ("BTN", "raise", 2.5), ("SB", "fold"), ("BB", "call")]
        spot = build_spot(cfg, line)
        assert not spot.ended
        assert spot.pot_bb == pytest.approx(5.5)
        assert spot.oop_pos == "BB" and spot.ip_pos == "BTN"
        assert spot.ip_range == RFI_BTN
        assert spot.oop_range == BB_CALL_VS_RAISE  # vs 后位宽防守

    def test_early_open_bb_defends_tighter(self):
        cfg = GameConfig(table_size=6, stack_bb=100)
        line = [("UTG", "raise", 2.2), ("HJ", "fold"), ("CO", "fold"),
                ("BTN", "fold"), ("SB", "fold"), ("BB", "call")]
        spot = build_spot(cfg, line)
        assert spot.oop_range == BB_DEFEND_VS_EARLY

    def test_3bet_pot_wraparound(self):
        # UTG 开池，BB 3bet，行动绕回 UTG 跟注
        cfg = GameConfig(table_size=6, stack_bb=100)
        line = [("UTG", "raise", 2.2), ("HJ", "fold"), ("CO", "fold"),
                ("BTN", "fold"), ("SB", "fold"), ("BB", "raise", 9.0),
                ("UTG", "call")]
        spot = build_spot(cfg, line)
        assert not spot.ended
        assert spot.pot_bb == pytest.approx(9 + 9 + 0.5)
        assert spot.oop_pos == "BB" and spot.ip_pos == "UTG"
        assert spot.oop_range == THREEBET_VS_EARLY  # BB vs UTG 紧 3bet
        assert spot.ip_range == CALL_VS_3BET

    def test_co_open_btn_3bet(self):
        cfg = GameConfig(table_size=6, stack_bb=100)
        line = [("UTG", "fold"), ("HJ", "fold"), ("CO", "raise", 2.5),
                ("BTN", "raise", 8.0), ("SB", "fold"), ("BB", "fold"),
                ("CO", "call")]
        spot = build_spot(cfg, line)
        assert spot.oop_pos == "CO" and spot.ip_pos == "BTN"
        assert spot.ip_range == THREEBET_STD

    def test_ante_all_players_in_pot(self):
        cfg = GameConfig(game_type="mtt", table_size=6, stack_bb=20, ante=0.1)
        line = [("UTG", "fold"), ("HJ", "fold"), ("CO", "fold"),
                ("BTN", "raise", 2.0), ("SB", "fold"), ("BB", "call")]
        spot = build_spot(cfg, line)
        # 底池 = 2+2+0.5 + 0.1*6
        assert spot.pot_bb == pytest.approx(5.1)
        assert spot.stack_bb == pytest.approx(17.9)


class TestMultiwayBlocking:
    def test_third_entrant_only_fold(self):
        cfg = GameConfig(table_size=6, stack_bb=100)
        line = [("UTG", "raise", 2.2), ("HJ", "call")]
        opts = next_actions(cfg, line)
        assert [(o["actor"], o["action"]) for o in opts] == [("CO", "fold")]

    def test_build_spot_rejects_multiway(self):
        cfg = GameConfig(table_size=6, stack_bb=100)
        # 构造三人都在的线：UTG limp, HJ limp, 其余弃牌到 BB —— BB 只能 fold
        line = [("UTG", "call"), ("HJ", "call"), ("CO", "fold"),
                ("BTN", "fold"), ("SB", "fold")]
        opts = next_actions(cfg, line)
        # BB 过牌会造成 3 人池，所以只给 fold
        assert [(o["actor"], o["action"]) for o in opts] == [("BB", "fold")]
        line.append(("BB", "fold"))
        spot = build_spot(cfg, line)  # 剩下 UTG vs HJ 的 HU limp 池
        assert not spot.ended
        assert spot.oop_pos == "UTG" and spot.ip_pos == "HJ"
        assert spot.oop_range == GENERIC_LIMP and spot.ip_range == GENERIC_LIMP

    def test_out_of_turn_rejected(self):
        cfg = GameConfig(table_size=6, stack_bb=100)
        with pytest.raises(ValueError, match="行动顺序错误"):
            build_spot(cfg, [("CO", "raise", 2.5)])  # UTG 必须先行动

    def test_line_incomplete_rejected(self):
        cfg = GameConfig(table_size=6, stack_bb=100)
        with pytest.raises(ValueError, match="尚未结束"):
            build_spot(cfg, [("UTG", "raise", 2.2), ("HJ", "fold")])


class TestNineMax:
    def test_full_ring_srp(self):
        cfg = GameConfig(table_size=9, stack_bb=100)
        line = [("UTG", "fold"), ("UTG+1", "fold"), ("MP", "raise", 2.5),
                ("LJ", "fold"), ("HJ", "fold"), ("CO", "call"),
                ("BTN", "fold"), ("SB", "fold"), ("BB", "fold")]
        spot = build_spot(cfg, line)
        assert not spot.ended
        assert spot.oop_pos == "MP" and spot.ip_pos == "CO"
        assert spot.pot_bb == pytest.approx(2.5 * 2 + 1.5)

    def test_opening_actor_is_utg(self):
        opts = next_actions(GameConfig(table_size=9, stack_bb=100), [])
        actors = {o["actor"] for o in opts}
        assert actors == {"UTG"}
