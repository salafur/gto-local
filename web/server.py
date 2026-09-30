"""Web 服务：本地 GTO 求解器的后端。

启动: python -m web.server  然后浏览器打开 http://127.0.0.1:8000

接口：
  POST /api/equity         手牌 vs 范围胜率
  POST /api/solve          提交翻后求解任务（3~5 张公共牌，后台 MCCFR）
  POST /api/nash           提交 HU 短码 Nash 全下表计算任务
  GET  /api/job/{id}       查询任务进度/结果
  GET  /api/preflop/presets 牌桌预设
  POST /api/preflop/next   翻前行动线下一步可选动作
  POST /api/preflop/spot   翻前行动线 -> 翻后场景
"""
from __future__ import annotations

import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from gto.cards import parse_cards, parse_combo
from gto.equity import equity_vs_range
from gto.nash import equity_matrix, nash_push_fold, push_call_summary
from gto.postflop import PostflopSolver
from gto.preflop import GameConfig, build_spot, next_actions
from gto.ranges import filter_blocked, parse_range

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="GTO Local", version="2.1.0")

JOBS: dict = {}

_NASH_MATRIX = None
_NASH_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class EquityRequest(BaseModel):
    hand: str = Field(..., description='手牌，如 "AhKh"')
    villain: str = Field("random", description='对手范围，如 "KK" 或 "ATs+,KQo"')
    board: str = Field("", description="公共牌（0~5 张）")
    trials: int = Field(20000, ge=1000, le=200000)


class SolveRequest(BaseModel):
    board: str = Field(..., description="3~5 张公共牌，如 AhKd7c(3s2h)")
    pot: int = Field(500, gt=0, description="底池（筹码，1bb=100）")
    stack: int = Field(9750, gt=0, description="翻后有效后手（筹码）")
    oop_range: str = Field(..., description="OOP（BB）范围")
    ip_range: str = Field(..., description="IP（BTN/SB）范围")
    bet_sizes: str = Field("33,75,150", description="下注尺度（底池%）")
    raise_sizes: str = Field("75", description="加注尺度")
    iterations: int = Field(200000, ge=1000, le=5000000)


class PreflopConfigModel(BaseModel):
    game_type: str = "cash"
    table_size: int = 2          # 2 | 6 | 9（翻后仍只解 HU）
    stack_bb: float = 100.0
    sb: float = 0.5
    bb: float = 1.0
    ante: float = 0.0


class PreflopRequest(BaseModel):
    config: PreflopConfigModel = PreflopConfigModel()
    line: list = Field(default_factory=list,
                       description='行动线，如 [["SB","raise",2.5],["BB","call"]] 或 '
                                   '[["UTG","raise",2.2],...,["BB","call"]]')


class NashRequest(BaseModel):
    stack_bb: float = Field(10.0, gt=0, le=25)


def _to_config(m: PreflopConfigModel) -> GameConfig:
    try:
        return GameConfig(game_type=m.game_type, table_size=m.table_size,
                          stack_bb=m.stack_bb, sb=m.sb, bb=m.bb, ante=m.ante)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _parse_sizes(text: str) -> tuple:
    sizes = [float(p.strip()) / 100.0 for p in text.split(",") if p.strip()]
    if not sizes:
        raise ValueError("至少需要一个下注尺度")
    return tuple(sizes)


def _run_job(job_id: str, fn):
    def worker():
        try:
            JOBS[job_id].update(fn())
            JOBS[job_id]["status"] = "done"
            JOBS[job_id]["elapsed"] = round(time.time() - JOBS[job_id]["started"], 1)
        except Exception as e:
            JOBS[job_id].update({"status": "error", "error": str(e)})
    threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Equity
# ---------------------------------------------------------------------------

@app.post("/api/equity")
def api_equity(req: EquityRequest):
    try:
        hand = parse_combo(req.hand)
        board = parse_cards(req.board) if req.board.strip() else ()
        villain_range = parse_range(req.villain)
        eq = equity_vs_range(hand, villain_range, board, trials=req.trials)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"equity": round(eq, 4)}


# ---------------------------------------------------------------------------
# 翻前
# ---------------------------------------------------------------------------

@app.get("/api/preflop/presets")
def api_preflop_presets():
    return GameConfig.presets()


@app.post("/api/preflop/next")
def api_preflop_next(req: PreflopRequest):
    try:
        cfg = _to_config(req.config)
        line = [tuple(s) for s in req.line]
        return {"options": next_actions(cfg, line)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/preflop/spot")
def api_preflop_spot(req: PreflopRequest):
    try:
        cfg = _to_config(req.config)
        line = [tuple(s) for s in req.line]
        spot = build_spot(cfg, line)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "ended": spot.ended,
        "reason": spot.reason,
        "pot_bb": spot.pot_bb,
        "stack_bb": spot.stack_bb,
        "pot": spot.pot,
        "stack": spot.stack,
        "oop_pos": spot.oop_pos,
        "ip_pos": spot.ip_pos,
        "oop_range": spot.oop_range,
        "ip_range": spot.ip_range,
        "description": spot.description,
    }


# ---------------------------------------------------------------------------
# 求解任务
# ---------------------------------------------------------------------------

@app.post("/api/solve")
def api_solve(req: SolveRequest):
    try:
        board = parse_cards(req.board)
        if len(board) not in (3, 4, 5):
            raise ValueError(f"公共牌必须是 3/4/5 张，当前 {len(board)} 张")
        oop = filter_blocked(parse_range(req.oop_range), board)
        ip = filter_blocked(parse_range(req.ip_range), board)
        bet_sizes = _parse_sizes(req.bet_sizes)
        raise_sizes = _parse_sizes(req.raise_sizes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "running", "progress": 0, "total": req.iterations,
                    "started": time.time(), "kind": "solve"}

    def work():
        solver = PostflopSolver(
            board=board, pot=req.pot, stack=req.stack,
            oop_range=oop, ip_range=ip,
            bet_sizes=bet_sizes, raise_sizes=raise_sizes,
        )
        solver.solve(iterations=req.iterations,
                     progress_cb=lambda d, t: JOBS[job_id].update({"progress": d}))
        return {
            "progress": req.iterations,
            "result": {
                "config": req.model_dump(),
                "street": len(board),
                "iterations": solver.iterations_done,
                "nodes": solver.average_strategy(),
            },
        }

    _run_job(job_id, work)
    return {"job_id": job_id}


@app.post("/api/nash")
def api_nash(req: NashRequest):
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "running", "progress": 0, "total": 1,
                    "started": time.time(), "kind": "nash"}

    def work():
        global _NASH_MATRIX
        with _NASH_LOCK:
            if _NASH_MATRIX is None:
                JOBS[job_id]["stage"] = "首次运行：计算 169x169 胜率矩阵（约 1 分钟，之后永久缓存）"
                _NASH_MATRIX = equity_matrix(trials=200)
        JOBS[job_id]["stage"] = "求解纳什均衡"
        table = nash_push_fold(req.stack_bb, E=_NASH_MATRIX)
        summary = push_call_summary(table)
        return {
            "progress": 1,
            "result": {"stack_bb": req.stack_bb, "table": table, "summary": summary},
        }

    _run_job(job_id, work)
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def api_job(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


# ---------------------------------------------------------------------------
# 静态页面
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main():
    import uvicorn
    print("=" * 50)
    print("  GTO Local v2 已启动:  http://127.0.0.1:8000")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
