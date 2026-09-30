"""示例：HU 短码 Nash 全下表。

首次运行会构建 169x169 胜率矩阵（约 40 秒，缓存到 ~/.gto-local/）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gto import nash_push_fold, push_call_summary

for stack in (5, 10, 15):
    table = nash_push_fold(stack)
    s = push_call_summary(table)
    print(f"{stack:>4}bb  BTN 全下 {s['push_pct']:>5}%   BB 跟注 {s['call_pct']:>5}%")
    # 打印几手关键牌的频率
    for h in ("AA", "AKs", "A5s", "KQo", "JTs", "72o"):
        print(f"       {h:>4}: push {table['push'][h]*100:5.1f}%  call {table['call'][h]*100:5.1f}%")
