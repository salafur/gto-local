"""GTO Local —— 本地德州扑克 GTO 求解器。

核心模块：
- cards      牌的表示与解析
- evaluator  牌力评估（7选5）
- ranges     范围解析（AA / ATs+ / KQo / 22+ / 权重 / 减法）
- equity     蒙特卡洛胜率计算
- postflop   翻/转/河通用 MCCFR 求解器（机会节点采样）
- river      河牌求解器（PostflopSolver 的兼容封装）
- preflop    翻前配置 / 行动线 / 参考范围图表（2/6/9 人桌，翻后 HU）
- nash       HU 短码全下/弃牌纳什表
- kuhn       Kuhn 扑克纳什验证（求解器正确性基准）
"""

from .cards import parse_card, parse_cards, parse_combo, card_str, cards_str, combo_str
from .evaluator import evaluate5, evaluate7, hand_category
from .ranges import parse_range, filter_blocked, all_combos
from .equity import equity_vs_range, equity_vs_hand, equity_from_strings
from .postflop import PostflopSolver
from .river import RiverSolver
from .preflop import (GameConfig, Spot, build_spot, next_actions,
                      postflop_order, display_name, POSITIONS)
from .nash import nash_push_fold, equity_matrix, HANDS, push_call_summary
from .kuhn import KuhnCFR

__version__ = "2.1.0"
