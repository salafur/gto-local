"""河牌场景求解器（向后兼容接口）。

RiverSolver 现在是 PostflopSolver 的特化（5 张公共牌）。
完整的翻/转/河通用求解器见 gto/postflop.py。
"""
from __future__ import annotations

from typing import Optional, Sequence

from .postflop import PostflopSolver
from .ranges import WeightedRange


class RiverSolver(PostflopSolver):
    """河牌（5 张公共牌）场景求解器，保持 v1.0 的接口与行为。"""

    def __init__(
        self,
        board: Sequence[int],
        pot: int,
        stack: int,
        oop_range: WeightedRange,
        ip_range: WeightedRange,
        bet_sizes: Sequence[float] = (0.33, 0.75, 1.5),
        raise_sizes: Sequence[float] = (0.75,),
        max_raises: int = 1,
        seed: Optional[int] = None,
    ):
        if len(board) != 5:
            raise ValueError("河牌场景需要 5 张公共牌")
        super().__init__(
            board=board, pot=pot, stack=stack,
            oop_range=oop_range, ip_range=ip_range,
            bet_sizes=bet_sizes, raise_sizes=raise_sizes,
            max_raises=max_raises, seed=seed,
        )
        # v1.0 兼容：暴露固定公共牌
        self.board = self.base_board
