"""牌力评估器测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto.cards import parse_cards
from gto.evaluator import evaluate5, evaluate7, hand_category


def ev(s):
    return evaluate5(parse_cards(s))


class TestCategories:
    def test_royal_flush(self):
        assert hand_category(ev("AhKhQhJhTh")) == "同花顺"

    def test_category_ordering(self):
        assert ev("AhKhQhJhTh") > ev("AcAdAhAsKd")   # 同花顺 > 四条
        assert ev("AcAdAhAsKd") > ev("AcAdAhKsKd")   # 四条 > 葫芦
        assert ev("AcAdAhKsKd") > ev("AhKhQh2h3h")   # 葫芦 > 同花
        assert ev("AhKhQh2h3h") > ev("9c8d7h6s5c")   # 同花 > 顺子
        assert ev("9c8d7h6s5c") > ev("AcAdAhKsQd")   # 顺子 > 三条
        assert ev("AcAdAhKsQd") > ev("AcAdKhKsQd")   # 三条 > 两对
        assert ev("AcAdKhKsQd") > ev("AcAdKhQsJd")   # 两对 > 一对
        assert ev("AcAdKhQsJd") > ev("AcKhQsJd9h")   # 一对 > 高牌

    def test_wheel_straight(self):
        wheel = ev("Ac2d3h4s5c")
        six_high = ev("2c3d4h5s6c")
        assert hand_category(wheel) == "顺子"
        assert wheel < six_high  # A-5 是最小的顺子

    def test_kicker_matters(self):
        assert ev("AcAdKhQsJd") > ev("AcAdKhQsTd")  # 同为对 A，比踢脚

    def test_two_pair_ordering(self):
        assert ev("AcAdKhKs2d") > ev("KcKdQhQsAs")  # 高对优先

    def test_flush_by_high_cards(self):
        assert ev("AhKhQh2h3h") < ev("AhKhQhJh9h")


class TestSevenCard:
    def test_best_five_of_seven(self):
        # 7 张里能组成同花顺，即使散牌很多
        score = evaluate7(parse_cards("AhKhQhJhTh2c3d"))
        assert score == ev("AhKhQhJhTh")

    def test_board_plays(self):
        # 公共牌本身是同花顺时，所有人平分
        a = evaluate7(parse_cards("2c3dAhKhQhJhTh"))
        b = evaluate7(parse_cards("7s8dAhKhQhJhTh"))
        assert a == b

    def test_five_card_shortcut(self):
        cards = parse_cards("AcKcQcJcTc")
        assert evaluate7(cards) == evaluate5(cards)
