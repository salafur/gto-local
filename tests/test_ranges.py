"""范围解析测试。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto.cards import parse_cards
from gto.ranges import filter_blocked, parse_range, range_size


class TestParse:
    def test_pair(self):
        assert len(parse_range("AA")) == 6

    def test_pair_plus(self):
        assert len(parse_range("77+")) == 8 * 6  # 77..AA 共 8 个对子

    def test_suited(self):
        assert len(parse_range("AKs")) == 4

    def test_offsuit(self):
        assert len(parse_range("KQo")) == 12

    def test_both(self):
        assert len(parse_range("AK")) == 16

    def test_suited_plus_ace(self):
        assert len(parse_range("ATs+")) == 4 * 4  # ATs AJs AQs AKs

    def test_suited_connector_ladder(self):
        assert len(parse_range("76s+")) == 7 * 4  # 76s..KQs 共 7 档

    def test_union(self):
        r = parse_range("AA,AKs")
        assert len(r) == 6 + 4

    def test_random(self):
        assert len(parse_range("random")) == 1326

    def test_weight(self):
        r = parse_range("AKs:0.5")
        assert len(r) == 4
        assert all(w == 0.5 for w in r.values())
        assert range_size(r) == 2.0

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            parse_range("")

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_range("XYZ")


class TestFilterBlocked:
    def test_board_removes_conflicts(self):
        r = parse_range("AA")
        board = parse_cards("AhKd7c3s2h")
        remaining = filter_blocked(r, board)
        assert len(remaining) == 3  # AA 有 6 个组合，含 Ah 的 3 个被移除

    def test_all_blocked(self):
        r = parse_range("AhKh")
        board = parse_cards("AhKd7c3s2h")
        assert filter_blocked(r, board) == {}


def test_subtraction_syntax():
    # 减法语法：random 去掉 AA 和 KK
    r = parse_range("random,-AA,-KK")
    assert len(r) == 1326 - 12
    from gto.cards import parse_combo
    assert parse_combo("AhAc") not in r
    assert parse_combo("KsKd") not in r
    assert parse_combo("QhQc") in r


def test_subtraction_after_weighted():
    # 减法在加权并集之后应用
    r = parse_range("AA:0.5,KK,-AA")
    from gto.cards import parse_combo
    assert parse_combo("AhAc") not in r
    assert r[parse_combo("KhKc")] == 1.0
