"""HU（单挑）翻前模块：牌桌配置、行动线构建、参考范围图表。

为什么翻前不做完整求解：6-max/HU 完整翻前游戏树在本地不可行
（GTO Wizard 的翻前解也是超算离线预计算的数据库）。本模块提供：

1. 牌桌配置（cash/mtt、盲注、前注、有效筹码）
2. HU 翻前行动线 -> 翻后场景换算（底池/后手/位置/双方参考范围）
3. HU 参考范围图表：基于公开资料的 GTO 近似范围，作为求解起点，
   在 UI 中可自由修改后再求解

HU 位置约定：BTN 即小盲（SB），翻前先行动、翻后始终有位置（IP）；
BB 翻后始终先行动（OOP）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 牌桌配置
# ---------------------------------------------------------------------------

# 筹码单位：内部求解器用整数筹码，1bb = 100 筹码
BB_UNIT = 100


@dataclass
class GameConfig:
    game_type: str = "cash"      # "cash" | "mtt"
    stack_bb: float = 100.0      # 有效筹码（bb）
    sb: float = 0.5              # 小盲（bb）
    bb: float = 1.0              # 大盲（bb）
    ante: float = 0.0            # 前注（bb/人），MTT 常用

    @staticmethod
    def presets() -> Dict[str, dict]:
        """常用预设，供 UI 展示。"""
        return {
            "cash": {"stacks": [200, 100, 60, 40], "default_stack": 100,
                     "sb": 0.5, "bb": 1.0, "ante": 0.0},
            "mtt": {"stacks": [60, 40, 25, 20, 15, 12, 10, 8], "default_stack": 20,
                    "sb": 0.5, "bb": 1.0, "ante": 0.1},
        }


# ---------------------------------------------------------------------------
# HU 参考范围图表（GTO 近似，非精确解，可在 UI 中修改）
# ---------------------------------------------------------------------------

# BTN(SB) 开池：简化 raise-or-fold 策略（真实 GTO 混入大量 limp，可手动加入）
SB_RFI = ("22+,A2s+,K2s+,Q2s+,J2s+,T6s+,96s+,86s+,75s+,65s,54s,"
          "A2o+,K2o+,Q5o+,J7o+,T7o+,98o,87o,76o")

# BTN(SB) limp 参考范围（不在 RFI 中但仍有一定可玩性的牌）
SB_LIMP = ("T2s,T3s,T4s,T5s,92s,93s,94s,95s,82s,83s,84s,85s,"
           "72s,73s,74s,62s,63s,64s,52s,53s,42s,43s,"
           "Q2o,Q3o,Q4o,J5o,J6o,T6o,96o,97o")

# BB vs SB 加注：跟注范围（宽防守）
BB_CALL_VS_RAISE = ("22+,A2s+,K2s+,Q4s+,J6s+,T7s+,97s+,86s+,76s,65s,54s,"
                    "A2o+,K7o+,Q8o+,J8o+,T8o+,98o,87o")

# BB vs SB 加注：3bet 范围（价值 + 部分阻断 bluff）
BB_3BET = "77+,A9s+,KTs+,QTs+,J9s+,T9s,AJo+,KQo,A5s"

# BB vs SB limp：加注（iso）范围
BB_ISO_RAISE = ("22+,A2s+,K6s+,Q8s+,J8s+,T8s+,98s,87s,"
                "A2o+,K9o+,Q9o+,J9o+,T9o,98o")

# SB vs BB 3bet：跟注范围
SB_CALL_VS_3BET = ("22+,A2s+,K9s+,Q9s+,J9s+,T9s,98s,87s,76s,65s,"
                   "A9o+,KTo+,QTo+,JTo")

# SB vs BB 3bet：4bet 范围（价值为主 + A5s bluff）
SB_4BET = "TT+,AKs,AKo,A5s"

# BB vs SB 4bet：跟注范围
BB_CALL_VS_4BET = "TT+,AKs,AKo,AQs"

# SB 跟注 BB 的 iso 加注
SB_CALL_VS_ISO = ("22+,A2s+,K2s+,Q5s+,J7s+,T7s+,97s+,87s,76s,65s,54s,"
                  "A2o+,K8o+,Q9o+,J9o+,T9o,98o")


def _minus(base: str, remove: str) -> str:
    """范围减法：base 中去掉 remove 的所有条目。"""
    return base + "," + ",".join("-" + t for t in remove.split(","))


# BB 对 limp 过牌 = 全部手牌去掉 iso 加注部分
BB_CHECK_VS_LIMP = _minus("random", BB_ISO_RAISE)


# ---------------------------------------------------------------------------
# 行动线构建
# ---------------------------------------------------------------------------

# 行动线中一条动作: (actor, action, amount_bb)
# actor: "SB" | "BB"; action: "fold"|"call"|"raise"|"check"
# amount: raise 时为"加注到的总投入(bb)"，其余为 None
LineStep = Tuple[str, str, Optional[float]]


@dataclass
class Spot:
    """翻前行动线换算出的翻后场景。"""
    ended: bool                       # 是否翻前已结束（弃牌/全下跟注）
    reason: str = ""                  # 结束原因描述
    pot_bb: float = 0.0
    stack_bb: float = 0.0             # 翻后双方后手（相等的有效筹码）
    pot: int = 0                      # 筹码单位（×BB_UNIT）
    stack: int = 0
    oop_range: str = ""               # BB（OOP）范围文本
    ip_range: str = ""                # BTN/SB（IP）范围文本
    description: str = ""
    line: List[LineStep] = field(default_factory=list)


def _norm_step(step) -> LineStep:
    """允许 ("SB","call") 或 ("SB","raise",2.5) 两种写法，统一补全为三元组。"""
    if len(step) == 2:
        return (step[0], step[1], None)
    return (step[0], step[1], step[2])


def next_actions(cfg: GameConfig, line: List[LineStep]) -> List[dict]:
    """给定已发生的行动线，返回下一个可选动作列表（供 UI 逐步构建）。

    返回 [{actor, action, label, amounts?}]，amounts 为加注可选额度（bb）。
    空列表表示行动线已完结。
    """
    S = cfg.stack_bb
    if not line:
        return [
            {"actor": "SB", "action": "fold", "label": "弃牌"},
            {"actor": "SB", "action": "call", "label": f"平跟（limp）"},
            {"actor": "SB", "action": "raise", "label": "加注",
             "amounts": [2.0, 2.5, 3.0, 4.0, S]},
        ]

    last_actor, last_action, last_amt = _norm_step(line[-1])
    actor = "BB" if last_actor == "SB" else "SB"

    if last_action in ("fold",):
        return []
    if last_action == "call":
        # SB limp 后 BB 的选项；或 SB 跟注 3bet / BB 跟注 4bet → 行动线结束（进入翻后）
        if last_actor == "SB" and len(line) == 1:
            return [
                {"actor": "BB", "action": "check", "label": "过牌"},
                {"actor": "BB", "action": "raise", "label": "加注（iso）",
                 "amounts": [3.0, 4.0, 5.0, S]},
            ]
        return []
    if last_action == "check":
        return []  # limp-check 结束
    if last_action == "raise":
        if last_amt is not None and last_amt >= S:
            # 全下：只能跟注或弃牌，且跟注后无翻后
            return [
                {"actor": actor, "action": "fold", "label": "弃牌"},
                {"actor": actor, "action": "call", "label": "跟注全下（翻前打光）"},
            ]
        # 普通加注：fold/call/re-raise
        min_rr = round(last_amt * 2, 2) if last_amt else 2.0
        amounts = sorted({min_rr, round(last_amt * 2.5, 2), round(last_amt * 3, 2), S})
        amounts = [a for a in amounts if a < S or a == S]
        if len(line) >= 3:
            # 已经 3bet 过，再 raise 就是 4bet；4bet 后只允许 call/fold
            if len(line) >= 4:
                return [
                    {"actor": actor, "action": "fold", "label": "弃牌"},
                    {"actor": actor, "action": "call", "label": "跟注"},
                ]
            return [
                {"actor": actor, "action": "fold", "label": "弃牌"},
                {"actor": actor, "action": "call", "label": "跟注"},
                {"actor": actor, "action": "raise", "label": "4bet",
                 "amounts": amounts},
            ]
        return [
            {"actor": actor, "action": "fold", "label": "弃牌"},
            {"actor": actor, "action": "call", "label": "跟注"},
            {"actor": actor, "action": "raise", "label": "3bet",
             "amounts": amounts},
        ]
    return []


def build_spot(cfg: GameConfig, line: List[LineStep]) -> Spot:
    """把 HU 翻前行动线换算成翻后求解场景。"""
    if not line:
        raise ValueError("行动线为空")
    line = [_norm_step(s) for s in line]

    S = cfg.stack_bb
    # invested 只记盲注/加注投入；前注在锅底统一加 2×ante
    invested = {"SB": cfg.sb, "BB": cfg.bb}

    # 逐条重放并校验
    for i, (actor, action, amt) in enumerate(line):
        opp = "BB" if actor == "SB" else "SB"
        if action == "fold":
            if i != len(line) - 1:
                raise ValueError("弃牌后行动线必须结束")
            return Spot(ended=True, reason=f"{actor} 弃牌，{opp} 收下底池", line=list(line))
        if action == "check":
            invested[actor] = invested[actor]  # 不追加投入
        elif action == "call":
            target = max(invested["SB"], invested["BB"])
            if target <= invested[actor] and actor == "SB" and i == 0:
                target = cfg.bb  # SB limp：补齐到大盲
            invested[actor] = target
        elif action == "raise":
            if amt is None:
                raise ValueError("加注动作缺少金额")
            prev_max = max(invested["SB"], invested["BB"])
            min_to = max(prev_max * 2, cfg.bb * 2)
            if amt < min_to and amt < S:
                raise ValueError(f"加注额度过小：{amt}bb（最小 {min_to}bb）")
            invested[actor] = min(amt, S)
        else:
            raise ValueError(f"未知动作: {action}")

    pot_bb = invested["SB"] + invested["BB"] + 2 * cfg.ante
    stack_bb = S - max(invested["SB"], invested["BB"]) - cfg.ante

    allin = invested["SB"] >= S or invested["BB"] >= S
    last_action = line[-1][1]
    if allin:
        return Spot(ended=True, reason="翻前全下" + ("被跟注，直接跑马" if last_action == "call" else ""),
                    pot_bb=pot_bb, stack_bb=0.0, line=list(line))

    # 根据行动线推导双方参考范围
    oop_range, ip_range = _ranges_for_line(line)

    desc_parts = []
    names = {"SB": "BTN(SB)", "BB": "BB"}
    labels = {"fold": "弃牌", "call": "跟注", "check": "过牌", "raise": "加注"}
    for actor, action, amt in line:
        if action == "raise":
            desc_parts.append(f"{names[actor]} 加注到 {amt}bb")
        else:
            desc_parts.append(f"{names[actor]} {labels[action]}")

    return Spot(
        ended=False,
        pot_bb=round(pot_bb, 2),
        stack_bb=round(stack_bb, 2),
        pot=int(round(pot_bb * BB_UNIT)),
        stack=int(round(stack_bb * BB_UNIT)),
        oop_range=oop_range,
        ip_range=ip_range,
        description=" → ".join(desc_parts) +
                    f"（底池 {pot_bb:.1f}bb，后手 {stack_bb:.1f}bb）",
        line=list(line),
    )


def _ranges_for_line(line: List[LineStep]) -> Tuple[str, str]:
    """根据行动线给出 (OOP=BB, IP=SB) 参考范围。"""
    actions = [(a, act) for a, act, _ in line]

    # SB raise, BB call → 单加注底池（SRP），SB 为 IP
    if actions == [("SB", "raise"), ("BB", "call")]:
        return BB_CALL_VS_RAISE, SB_RFI
    # SB limp, BB check → limp 底池
    if actions == [("SB", "call"), ("BB", "check")]:
        return BB_CHECK_VS_LIMP, SB_LIMP
    # SB limp, BB raise, SB call → iso 底池，BB 是翻前 aggressor 但仍 OOP
    if actions == [("SB", "call"), ("BB", "raise"), ("SB", "call")]:
        return BB_ISO_RAISE, SB_CALL_VS_ISO
    # SB raise, BB 3bet, SB call → 3bet 底池
    if actions == [("SB", "raise"), ("BB", "raise"), ("SB", "call")]:
        return BB_3BET, SB_CALL_VS_3BET
    # SB raise, BB 3bet, SB 4bet, BB call → 4bet 底池
    if actions == [("SB", "raise"), ("BB", "raise"),
                   ("SB", "raise"), ("BB", "call")]:
        return BB_CALL_VS_4BET, SB_4BET
    # 兜底：给宽范围，让用户自己改
    return "random", "random"
