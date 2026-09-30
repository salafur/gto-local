"""翻前模块：牌桌配置、行动线构建、参考范围图表。

支持 2/6/9 人桌，但**翻后只解 HU（单挑）**：行动线中其余玩家必须全部弃牌，
最终恰好两人进入翻牌圈（多人池不在本工具范围）。

为什么翻前不做完整求解：完整翻前游戏树在本地不可行
（GTO Wizard 的翻前解也是超算离线预计算的数据库）。本模块提供：

1. 牌桌配置（cash/mtt、桌型人数、盲注、前注、有效筹码）
2. 翻前行动线 -> 翻后场景换算（底池/后手/位置/双方参考范围）
3. 按位置的参考范围图表：基于公开资料的 GTO 近似范围，作为求解起点，
   在 UI 中可自由修改后再求解

位置约定：
- HU（2 人桌）：BTN 即小盲（SB），翻前先行动、翻后有位置（IP）
- 6max：UTG → HJ → CO → BTN → SB → BB
- 9max：UTG → UTG+1 → MP → LJ → HJ → CO → BTN → SB → BB
- 翻后行动顺序（OOP→IP）：SB, BB, UTG, UTG+1, MP, LJ, HJ, CO, BTN
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 桌型与位置
# ---------------------------------------------------------------------------

# 筹码单位：内部求解器用整数筹码，1bb = 100 筹码
BB_UNIT = 100

# 各桌型的翻前行动顺序
POSITIONS: Dict[int, Tuple[str, ...]] = {
    2: ("SB", "BB"),
    6: ("UTG", "HJ", "CO", "BTN", "SB", "BB"),
    9: ("UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN", "SB", "BB"),
}

def postflop_order(cfg: "GameConfig") -> Tuple[str, ...]:
    """翻后行动顺序（OOP→IP）：从按钮位左手边开始绕桌一圈，按钮位最后。

    HU 里 BTN=SB，所以翻后是 BB 先行动；6/9max 里 SB 最先行动。
    """
    pos = cfg.positions
    btn_idx = pos.index("BTN") if "BTN" in pos else pos.index("SB")
    return tuple(pos[(btn_idx + 1 + i) % len(pos)] for i in range(len(pos)))

# 位置紧度分层（用于挑选防守/3bet 图表）
_EARLY = ("UTG", "UTG+1", "MP")
_MID = ("LJ", "HJ", "CO")
_LATE = ("BTN", "SB")


def display_name(pos: str, table_size: int = 2) -> str:
    """UI 展示名：HU 里 SB 就是 BTN。"""
    if table_size == 2 and pos == "SB":
        return "BTN(SB)"
    return pos


# ---------------------------------------------------------------------------
# 牌桌配置
# ---------------------------------------------------------------------------

@dataclass
class GameConfig:
    game_type: str = "cash"      # "cash" | "mtt"
    table_size: int = 2          # 2 | 6 | 9（翻后仍只解 HU）
    stack_bb: float = 100.0      # 有效筹码（bb）
    sb: float = 0.5              # 小盲（bb）
    bb: float = 1.0              # 大盲（bb）
    ante: float = 0.0            # 前注（bb/人），MTT 常用

    def __post_init__(self):
        if self.table_size not in POSITIONS:
            raise ValueError(f"table_size 必须是 {sorted(POSITIONS)} 之一")
        if self.game_type not in ("cash", "mtt"):
            raise ValueError("game_type 必须是 cash 或 mtt")

    @property
    def positions(self) -> Tuple[str, ...]:
        return POSITIONS[self.table_size]

    @staticmethod
    def presets() -> Dict[str, dict]:
        """常用预设，供 UI 展示。"""
        return {
            "cash": {"stacks": [200, 100, 60, 40], "default_stack": 100,
                     "sb": 0.5, "bb": 1.0, "ante": 0.0},
            "mtt": {"stacks": [60, 40, 25, 20, 15, 12, 10, 8], "default_stack": 20,
                    "sb": 0.5, "bb": 1.0, "ante": 0.1},
            "table_sizes": [2, 6, 9],
            "positions": {str(k): list(v) for k, v in POSITIONS.items()},
        }


# ---------------------------------------------------------------------------
# 参考范围图表（GTO 近似，非精确解，可在 UI 中修改）
# ---------------------------------------------------------------------------

# --- HU 专用（保留） ---
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

# 4bet 范围（价值为主 + A5s bluff）
SB_4BET = "TT+,AKs,AKo,A5s"

# 面对 4bet 的跟注范围
BB_CALL_VS_4BET = "TT+,AKs,AKo,AQs"

# SB 跟注 BB 的 iso 加注
SB_CALL_VS_ISO = ("22+,A2s+,K2s+,Q5s+,J7s+,T7s+,97s+,87s,76s,65s,54s,"
                  "A2o+,K8o+,Q9o+,J9o+,T9o,98o")

# --- 6max/9max 各位置 RFI ---
RFI_UTG = "22+,A2s+,K9s+,Q9s+,J9s+,T9s,98s,87s,AJo+,KQo"                    # ~15%
RFI_UTG1 = "22+,A2s+,K8s+,Q9s+,J9s+,T8s+,98s,87s,AJo+,KQo"                  # ~17%
RFI_MP = "22+,A2s+,K8s+,Q8s+,J9s+,T8s+,98s,87s,76s,ATo+,KQo"                # ~19%
RFI_LJ = "22+,A2s+,K7s+,Q8s+,J8s+,T8s+,98s,87s,76s,65s,ATo+,KJo+"           # ~22%
RFI_HJ = "22+,A2s+,K6s+,Q8s+,J8s+,T8s+,98s,87s,76s,65s,ATo+,KJo+,QJo"       # ~25%
RFI_CO = ("22+,A2s+,K5s+,Q8s+,J8s+,T8s+,98s,87s,76s,65s,54s,"
          "A9o+,KTo+,QTo+,JTo")                                             # ~29%
RFI_BTN = ("22+,A2s+,K2s+,Q5s+,J7s+,T7s+,97s+,87s,76s,65s,54s,"
           "A2o+,K9o+,Q9o+,J9o+,T9o,98o")                                   # ~42%

RFI_CHARTS: Dict[str, str] = {
    "UTG": RFI_UTG, "UTG+1": RFI_UTG1, "MP": RFI_MP, "LJ": RFI_LJ,
    "HJ": RFI_HJ, "CO": RFI_CO, "BTN": RFI_BTN, "SB": SB_RFI,
}

# --- 防守图表 ---
# BB 防守 vs 前位开池（紧一些）
BB_DEFEND_VS_EARLY = ("22+,A2s+,K9s+,Q9s+,J9s+,T8s+,98s,87s,76s,"
                      "A9o+,KTo+,QTo+,JTo")                                 # ~30%
# BB 防守 vs 后位（BTN/SB）开池 = BB_CALL_VS_RAISE

# 有位置平跟开池（如 BTN vs CO），不含 3bet 手牌也可，用户可自行调整
FLAT_VS_RFI = "22,33,44,55,66,77,88,99,A7s+,KTs+,QTs+,JTs,T9s,98s,AQo+"     # ~10%

# 3bet：vs 前位开池收紧，vs 中后位放宽
THREEBET_VS_EARLY = "JJ+,AQs+,AKo,A5s"                                      # ~4%
THREEBET_STD = "77+,A9s+,KTs+,QTs+,JTs,T9s,AQo+,KQo,A5s"                    # ~8%

# 开池者跟注 3bet（通用）
CALL_VS_3BET = SB_CALL_VS_3BET

# 通用 limp 范围（非 SB 位置的 limp，宽而弱）
GENERIC_LIMP = ("22+,A2s+,K2s+,Q2s+,J4s+,T6s+,96s+,86s+,75s+,65s,54s,"
                "A2o+,K8o+,Q8o+,J8o+,T8o+,98o,87o")


def _minus(base: str, remove: str) -> str:
    """范围减法：base 中去掉 remove 的所有条目。"""
    return base + "," + ",".join("-" + t for t in remove.split(","))


# BB 对 limp 过牌 = 全部手牌去掉 iso 加注部分
BB_CHECK_VS_LIMP = _minus("random", BB_ISO_RAISE)


# ---------------------------------------------------------------------------
# 行动线构建
# ---------------------------------------------------------------------------

# 行动线中一条动作: (actor, action, amount_bb)
# actor: 位置名（"UTG"/"BTN"/"SB"/"BB" ...）
# action: "fold"|"call"|"raise"|"check"
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
    oop_pos: str = ""                 # OOP 位置（翻后先行动）
    ip_pos: str = ""                  # IP 位置
    oop_range: str = ""               # OOP 范围文本
    ip_range: str = ""                # IP 范围文本
    description: str = ""
    line: List[LineStep] = field(default_factory=list)


def _norm_step(step) -> LineStep:
    """允许 ("SB","call") 或 ("SB","raise",2.5) 两种写法，统一补全为三元组。"""
    if len(step) == 2:
        return (step[0], step[1], None)
    return (step[0], step[1], step[2])


@dataclass
class _State:
    """行动轮回放后的状态。"""
    invested: Dict[str, float]
    active: List[str]                 # 未弃牌玩家（翻前顺序）
    needs: List[str]                  # 仍需行动的玩家（翻前顺序）
    raises: int
    entered: set                      # 自愿入池（call/raise 过）的玩家
    ended_reason: Optional[str] = None


def _replay(cfg: GameConfig, line: List[LineStep]) -> _State:
    """回放行动线并校验每一步的合法性。"""
    order = cfg.positions
    S = cfg.stack_bb
    invested = {p: 0.0 for p in order}
    invested["SB"] = cfg.sb
    invested["BB"] = cfg.bb
    active = list(order)
    needs = list(order)
    raises = 0
    entered: set = set()
    ended_reason = None

    for actor, action, amt in line:
        if ended_reason is not None or not needs:
            raise ValueError("行动线已结束，存在多余的动作")
        if actor not in invested:
            raise ValueError(f"{cfg.table_size} 人桌没有位置: {actor}")
        if actor != needs[0]:
            raise ValueError(f"行动顺序错误：现在应由 {needs[0]} 行动，而不是 {actor}")
        cur_bet = max(invested[p] for p in active)

        if action == "fold":
            active.remove(actor)
            needs.pop(0)
            if len(active) == 1:
                winner = active[0]
                ended_reason = f"{actor} 弃牌，{winner} 收下底池"
                needs.clear()
        elif action == "check":
            if invested[actor] != cur_bet:
                raise ValueError(f"{actor} 当前无法过牌（需跟注 {cur_bet}bb）")
            needs.pop(0)
        elif action == "call":
            if len(entered) >= 2 and actor not in entered:
                raise ValueError("多人池不支持：已有两人入池，其他人只能弃牌")
            invested[actor] = min(cur_bet, S)
            entered.add(actor)
            needs.pop(0)
        elif action == "raise":
            if amt is None:
                raise ValueError("加注动作缺少金额")
            if len(entered) >= 2 and actor not in entered:
                raise ValueError("多人池不支持：已有两人入池，其他人只能弃牌")
            if raises >= 3:
                raise ValueError("最多支持到 4bet，不能再加注")
            min_to = max(cur_bet * 2, cfg.bb * 2) if raises else cfg.bb * 2
            if amt < min_to and amt < S:
                raise ValueError(f"加注额度过小：{amt}bb（最小 {min_to:g}bb）")
            if amt <= invested[actor]:
                raise ValueError(f"加注额度必须大于自己已投入的 {invested[actor]:g}bb")
            invested[actor] = min(amt, S)
            entered.add(actor)
            raises += 1
            # 其余未弃牌玩家全部需要重新行动，从加注者下家开始顺时针
            idx = order.index(actor)
            needs = [order[(idx + 1 + k) % len(order)]
                     for k in range(len(order))
                     if order[(idx + 1 + k) % len(order)] in active
                     and order[(idx + 1 + k) % len(order)] != actor]
        else:
            raise ValueError(f"未知动作: {action}")

    return _State(invested=invested, active=active, needs=needs,
                  raises=raises, entered=entered, ended_reason=ended_reason)


def next_actions(cfg: GameConfig, line: List[LineStep]) -> List[dict]:
    """给定已发生的行动线，返回下一个可选动作列表（供 UI 逐步构建）。

    返回 [{actor, action, label, amounts?}]，amounts 为加注可选额度（bb）。
    空列表表示行动线已完结。
    """
    line = [_norm_step(s) for s in line]
    st = _replay(cfg, line)
    if st.ended_reason is not None or not st.needs:
        return []

    S = cfg.stack_bb
    actor = st.needs[0]
    cur_bet = max(st.invested[p] for p in st.active)
    blocked = len(st.entered) >= 2 and actor not in st.entered

    opts: List[dict] = []
    # 免费过牌（仅当过牌不会造成多人池时才提供）；能过牌就不提供弃牌
    can_check = (st.invested[actor] == cur_bet and not blocked
                 and len(st.active) <= 2)
    if can_check:
        opts.append({"actor": actor, "action": "check", "label": "过牌"})
    else:
        opts.append({"actor": actor, "action": "fold", "label": "弃牌"})
        if st.invested[actor] != cur_bet and not blocked:
            to_call = min(cur_bet, S) - st.invested[actor]
            if st.raises == 0:
                label = (f"平跟（limp，{to_call:g}bb）" if actor != "BB"
                         else f"跟注 {to_call:g}bb")
            else:
                label = f"跟注 {to_call:g}bb" + ("（全下）" if cur_bet >= S else "")
            opts.append({"actor": actor, "action": "call", "label": label})

    # 加注选项：面对全下（或筹码不足以做最小加注）时不可加注
    min_to = (max(cur_bet * 2, cfg.bb * 2) if st.raises else cfg.bb * 2)
    can_raise = (not blocked and st.raises < 3 and S > cur_bet
                 and (min_to <= S))
    if can_raise:
        if st.raises == 0:
            rlabel = "加注"
            base = [2.0, 2.5, 3.0, 4.0] if cfg.table_size == 2 else [2.0, 2.2, 2.5, 3.0]
        elif st.raises == 1:
            rlabel = "3bet"
            base = [round(cur_bet * 2.2, 2), round(cur_bet * 2.5, 2),
                    round(cur_bet * 3, 2), round(cur_bet * 4, 2)]
        else:
            rlabel = "4bet"
            base = [round(cur_bet * 2.2, 2), round(cur_bet * 2.5, 2),
                    round(cur_bet * 3, 2)]
        amounts = sorted({a for a in base if min_to <= a < S})
        if S > cur_bet:
            amounts.append(S)  # 全下总是可选
        if amounts:
            opts.append({"actor": actor, "action": "raise",
                         "label": rlabel, "amounts": amounts})
    return opts


def build_spot(cfg: GameConfig, line: List[LineStep]) -> Spot:
    """把翻前行动线换算成翻后求解场景（必须恰好剩两人）。"""
    if not line:
        raise ValueError("行动线为空")
    line = [_norm_step(s) for s in line]
    st = _replay(cfg, line)

    if st.ended_reason is not None:
        return Spot(ended=True, reason=st.ended_reason, line=list(line))

    S = cfg.stack_bb
    pot_bb = sum(st.invested.values()) + cfg.ante * cfg.table_size

    # 翻前全下：有效投入达到筹码上限
    if max(st.invested.values()) >= S:
        reason = "翻前全下"
        if line[-1][1] == "call":
            reason += "被跟注，直接跑马"
        return Spot(ended=True, reason=reason, pot_bb=round(pot_bb, 2),
                    stack_bb=0.0, line=list(line))

    if st.needs:
        raise ValueError(f"行动轮尚未结束，等待 {st.needs[0]} 行动")
    if len(st.active) != 2:
        raise ValueError(f"多人池不支持：还剩 {len(st.active)} 人未弃牌，本工具只解 HU 翻后")

    p1, p2 = st.active
    pf_order = postflop_order(cfg)
    oop, ip = sorted((p1, p2), key=lambda p: pf_order.index(p))
    stack_bb = S - max(st.invested[p1], st.invested[p2]) - cfg.ante

    oop_range, ip_range = _ranges_for_line(cfg, line, oop, ip)

    labels = {"fold": "弃牌", "call": "跟注", "check": "过牌", "raise": "加注"}
    desc_parts = []
    for actor, action, amt in line:
        name = display_name(actor, cfg.table_size)
        if action == "raise":
            desc_parts.append(f"{name} 加注到 {amt:g}bb")
        else:
            desc_parts.append(f"{name} {labels[action]}")
    description = (" → ".join(desc_parts) +
                   f"（底池 {pot_bb:.1f}bb，后手 {stack_bb:.1f}bb，"
                   f"OOP={display_name(oop, cfg.table_size)} "
                   f"IP={display_name(ip, cfg.table_size)}）")

    return Spot(
        ended=False,
        pot_bb=round(pot_bb, 2),
        stack_bb=round(stack_bb, 2),
        pot=int(round(pot_bb * BB_UNIT)),
        stack=int(round(stack_bb * BB_UNIT)),
        oop_pos=oop, ip_pos=ip,
        oop_range=oop_range, ip_range=ip_range,
        description=description,
        line=list(line),
    )


def _ranges_for_line(cfg: GameConfig, line: List[LineStep],
                     oop: str, ip: str) -> Tuple[str, str]:
    """根据行动线给出 (OOP, IP) 参考范围。"""
    raises = [(a, amt) for a, act, amt in line if act == "raise"]

    # 首次加注前是否有非 BB 的跟注（limp）
    first_raise_idx = next((i for i, s in enumerate(line) if s[1] == "raise"),
                           len(line))
    limped_before = any(act == "call" and a != "BB"
                        for a, act, _ in line[:first_raise_idx])

    # ---- 无加注：limp 底池 ----
    if not raises:
        charts: Dict[str, str] = {"BB": BB_CHECK_VS_LIMP}
        for a, act, _ in line:
            if act == "call":
                charts[a] = SB_LIMP if a == "SB" else GENERIC_LIMP
        return charts.get(oop, GENERIC_LIMP), charts.get(ip, GENERIC_LIMP)

    first_raiser = raises[0][0]
    last_raiser = raises[-1][0]

    if len(raises) == 1:
        if limped_before:
            # limp -> iso 加注 -> 跟注
            caller = ip if ip != first_raiser else oop
            chart = {first_raiser: BB_ISO_RAISE, caller: SB_CALL_VS_ISO}
            return chart[oop], chart[ip]
        # 单加注底池（SRP）：开池者 RFI，跟注者防守图表
        caller = ip if ip != first_raiser else oop
        opener_chart = RFI_CHARTS.get(first_raiser, SB_RFI)
        if caller == "BB":
            caller_chart = (BB_DEFEND_VS_EARLY if first_raiser in _EARLY
                            else BB_CALL_VS_RAISE)
        else:
            caller_chart = FLAT_VS_RFI
        chart = {first_raiser: opener_chart, caller: caller_chart}
        return chart[oop], chart[ip]

    if len(raises) == 2:
        # 3bet 底池：第二加注者为 aggressor
        threebettor = last_raiser
        opener = first_raiser
        if threebettor == "BB" and opener == "SB":
            tb_chart = BB_3BET
        elif opener in _EARLY:
            tb_chart = THREEBET_VS_EARLY
        else:
            tb_chart = THREEBET_STD
        chart = {threebettor: tb_chart, opener: CALL_VS_3BET}
        return chart[oop], chart[ip]

    # 4bet+ 底池
    fourbettor = last_raiser
    caller = ip if ip != fourbettor else oop
    chart = {fourbettor: SB_4BET, caller: BB_CALL_VS_4BET}
    return chart[oop], chart[ip]
