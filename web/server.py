"""Web 服务：本地 GTO 求解器的后端。

启动: python -m web.server  然后浏览器打开 http://127.0.0.1:8000

接口：
  POST /api/equity   手牌 vs 范围胜率
  POST /api/solve    提交河牌求解任务（后台线程跑 MCCFR）
  GET  /api/job/{id} 查询求解进度/结果
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
from gto.ranges import filter_blocked, parse_range
from gto.river import RiverSolver

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="GTO Local", version="1.0.0")

JOBS: dict = {}


class EquityRequest(BaseModel):
    hand: str = Field(..., description='手牌，如 "AhKh"')
    villain: str = Field("random", description='对手范围，如 "KK" 或 "ATs+,KQo"')
    board: str = Field("", description="公共牌（0~5 张），如 AhKd7c")
    trials: int = Field(20000, ge=1000, le=200000)


class SolveRequest(BaseModel):
    board: str = Field(..., description="5 张公共牌，如 AhKd7c3s2h")
    pot: int = Field(60, gt=0)
    stack: int = Field(140, gt=0)
    oop_range: str = Field(..., description="OOP（不利位置）范围")
    ip_range: str = Field(..., description="IP（有利位置）范围")
    bet_sizes: str = Field("33,75,150", description="下注尺度（底池%%），逗号分隔")
    raise_sizes: str = Field("75", description="加注尺度，逗号分隔")
    iterations: int = Field(200000, ge=1000, le=2000000)


def _parse_sizes(text: str) -> tuple:
    sizes = []
    for part in text.split(","):
        part = part.strip()
        if part:
            sizes.append(float(part) / 100.0)
    if not sizes:
        raise ValueError("至少需要一个下注尺度")
    return tuple(sizes)


@app.post("/api/equity")
def api_equity(req: EquityRequest):
    try:
        hand = parse_combo(req.hand)
        board = parse_cards(req.board) if req.board.strip() else ()
        villain_range = parse_range(req.villain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        eq = equity_vs_range(hand, villain_range, board, trials=req.trials)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"equity": round(eq, 4)}


@app.post("/api/solve")
def api_solve(req: SolveRequest):
    try:
        board = parse_cards(req.board)
        if len(board) != 5:
            raise ValueError(f"河牌场景需要恰好 5 张公共牌，当前 {len(board)} 张")
        oop = filter_blocked(parse_range(req.oop_range), board)
        ip = filter_blocked(parse_range(req.ip_range), board)
        bet_sizes = _parse_sizes(req.bet_sizes)
        raise_sizes = _parse_sizes(req.raise_sizes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "running", "progress": 0, "total": req.iterations,
                    "started": time.time()}

    def worker():
        try:
            solver = RiverSolver(
                board=board, pot=req.pot, stack=req.stack,
                oop_range=oop, ip_range=ip,
                bet_sizes=bet_sizes, raise_sizes=raise_sizes,
            )

            def on_progress(done, total):
                JOBS[job_id]["progress"] = done

            solver.solve(iterations=req.iterations, progress_cb=on_progress)
            result = solver.average_strategy()
            JOBS[job_id].update({
                "status": "done",
                "progress": req.iterations,
                "elapsed": round(time.time() - JOBS[job_id]["started"], 1),
                "result": {
                    "config": req.model_dump(),
                    "iterations": solver.iterations_done,
                    "nodes": result,
                },
            })
        except Exception as e:
            JOBS[job_id].update({"status": "error", "error": str(e)})

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def api_job(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main():
    import uvicorn
    print("=" * 50)
    print("  GTO Local 已启动:  http://127.0.0.1:8000")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
