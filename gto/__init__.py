"""GTO Local —— 本地德州扑克 GTO 求解器。

核心模块：
- cards      牌的表示与解析
- evaluator  牌力评估（7选5）
- ranges     范围解析（AA / ATs+ / KQo / 22+ / 权重）
- equity     蒙特卡洛胜率计算
- river      河牌场景 MCCFR 求解器
- kuhn       Kuhn 扑克纳什验证（求解器正确性基准）
"""

from .cards import parse_card, parse_cards, parse_combo, card_str, cards_str, combo_str
from .evaluator import evaluate5, evaluate7, hand_category
from .ranges import parse_range, filter_blocked, all_combos
from .equity import equity_vs_range, equity_vs_hand, equity_from_strings
from .river import RiverSolver
from .kuhn import KuhnCFR

__version__ = "1.0.0"
