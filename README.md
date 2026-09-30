# GTO Local 🂡

本地德州扑克 GTO 求解器 —— 输入具体场景，用 **MCCFR（蒙特卡洛反事实遗憾最小化）** 算法实时求解纳什均衡策略，在 13×13 手牌矩阵上展示每个组合的 GTO 动作频率（GTO Wizard 风格）。纯本地运行，数据不出本机。

## 功能

- ✅ **河牌场景精确求解**：自定义公共牌、底池、筹码、双方范围、下注/加注尺度，逐组合（无抽象）求解
- ✅ **13×13 策略矩阵**：动作频率堆叠着色（过牌/下注/加注/跟注/弃牌），点击格子看每个组合的精确频率
- ✅ **范围选择器**：GTO Wizard 同款 13×13 点选矩阵，也支持文本语法（`AA` / `ATs+` / `KQo` / `22+` / `76s+` / `random` / `:0.5` 权重）
- ✅ **Equity 计算器**：手牌 vs 范围蒙特卡洛胜率（可带公共牌）
- ✅ **求解器正确性验证**：内置 Kuhn 扑克基准（有解析纳什均衡），证明 CFR 引擎收敛正确
- ✅ 求解速度 ~50,000 迭代/秒，20 万迭代约 4 秒

## 快速开始

```bash
pip install -r requirements.txt
python -m web.server
# 浏览器打开 http://127.0.0.1:8000
```

命令行玩法：

```bash
python examples/kuhn_validation.py   # 看 CFR 收敛到理论纳什均衡
python examples/equity_demo.py       # 经典对局胜率
python examples/solve_river.py       # 命令行求解河牌场景
pytest tests/ -v                     # 32 个测试（含纳什收敛验证）
```

代码调用：

```python
from gto import RiverSolver, parse_cards, parse_range

solver = RiverSolver(
    board=parse_cards("AhKd7c3s2h"),
    pot=60, stack=140,
    oop_range=parse_range("22+,ATs+,KTs+,AKo,AQo"),
    ip_range=parse_range("22+,A9s+,KTs+,AKo"),
    bet_sizes=(0.33, 0.75, 1.5),   # 底池百分比
)
solver.solve(iterations=200_000)
print(solver.root_strategy_matrix(""))       # OOP 首轮策略
print(solver.root_strategy_matrix("X0"))     # OOP 过牌后 IP 的策略
```

## 算法原理

### CFR 是什么

GTO 的本质是求两人零和博弈的**纳什均衡**。CFR（Counterfactual Regret Minimization）通过反复自我对弈逼近均衡：

1. 每个**信息集**（自己的手牌 + 行动历史）维护一组**累计遗憾值**：过去每次没选某个动作，少赢了多少
2. 当前策略由遗憾值正比产生（Regret Matching）：越后悔没选的动作，越多选它
3. 对所有信息集的平均策略随迭代收敛到纳什均衡（二人零和博弈下有理论保证）

本项目使用 **外部采样 MCCFR**：每次迭代采样一个我方组合 + 按范围权重采样一个对手组合，我方节点展开全部动作、对手节点采样一个动作，比 vanilla CFR 快几个数量级。

### 怎么验证求解器是对的

用 **Kuhn 扑克**（3 张牌的最小扑克博弈，有解析纳什均衡）做基准：

```
$ python examples/kuhn_validation.py
博弈值: -0.0554（理论 -1/18 ≈ -0.0556）
exploitability: 0.0034（理论 0）
```

CFR 收敛后博弈值与 exploitability 都逼近理论值，且策略满足全部纳什不变量（如拿 K 面对下注 100% 跟注、拿 Q 跟注 1/3）——这是扑克 AI 领域验证求解器的标准做法。

## 与 GTO Wizard 的差异（诚实说明）

| | GTO Wizard | GTO Local |
|---|---|---|
| 求解范围 | 翻前到河牌全游戏树，GPU 集群预计算 | 单条街（河牌）精确求解 |
| 手牌抽象 | 有（聚类降维） | 无抽象，逐组合求解 |
| 场景覆盖 | 数千万预存场景 | 你输什么场景解什么场景 |
| 速度 | 秒开（查表） | 数秒~数十秒（实时求解） |
| 数据 | 云端 | 完全本地 |

**Roadmap**：转牌/翻牌（equity-leaf 近似）→ HU 短码 push/fold 纳什表 → 手牌聚类抽象 → 多底池类型预设。

## 项目结构

```
gto-local/
├── gto/
│   ├── cards.py       # 牌的表示与解析（"AhKd" <-> 整数）
│   ├── evaluator.py   # 牌力评估（7选5，整数可比较）
│   ├── ranges.py      # 范围解析（AA / ATs+ / KQo / 22+ / 权重）
│   ├── equity.py      # 蒙特卡洛胜率
│   ├── river.py       # ★ 河牌 MCCFR 求解器（外部采样）
│   └── kuhn.py        # ★ Kuhn 扑克纳什验证基准
├── web/
│   ├── server.py      # FastAPI 后端（求解任务后台线程 + 进度轮询）
│   └── static/index.html  # 13x13 策略矩阵 UI（GTO Wizard 风格）
├── examples/          # 命令行示例
└── tests/             # 32 个测试：评估器/范围/胜率/Kuhn收敛/河牌策略
```

## 免责声明

本项目仅供学习博弈论与算法使用。GTO 策略是特定抽象（下注尺度、范围假设）下的均衡解，实战价值取决于输入假设的质量。

## License

MIT
