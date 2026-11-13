"""API để n8n gọi agent.

Chạy:
    .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000

Luồng:
    POST /runs                      -> agent phân tích và dừng chờ duyệt (status = awaiting_review)
    POST /runs/{run_id}/decision    -> approve hoặc reject, trả về báo cáo nếu được duyệt
    GET  /runs/{run_id}             -> xem trạng thái và báo cáo
    GET  /runs                      -> danh sách các run gần đây

Mọi endpoint trừ /health đều yêu cầu header X-API-Key.
"""

from __future__ import annotations

import hmac
import uuid
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from api.config import get_api_settings
from api.service import RunNotFoundError, RunService, RunStateError

service: RunService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global service
    service = RunService()
    yield
    service.close()


app = FastAPI(title="Olist AI BI", version="0.1.0", lifespan=lifespan)


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_api_settings().api_key
    if not x_api_key or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="API key không hợp lệ")


class StartRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


class RunOut(BaseModel):
    run_id: str
    question: str
    status: str
    findings: str | None = None
    warnings: list[str] = []
    report: str | None = None
    error: str | None = None
    created_at: str


def _to_out(row: dict[str, Any]) -> RunOut:
    return RunOut(**{**row, "warnings": row.get("warnings") or []})


def _parse_run_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as err:
        raise HTTPException(status_code=404, detail="run_id không hợp lệ") from err


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", response_model=RunOut, dependencies=[Depends(require_api_key)])
def start_run(body: StartRequest) -> RunOut:
    try:
        row = service.start(body.question)
    except Exception as err:
        raise HTTPException(status_code=502, detail=f"Agent gặp lỗi: {err}") from err
    return _to_out(row)


@app.post(
    "/runs/{run_id}/decision",
    response_model=RunOut,
    dependencies=[Depends(require_api_key)],
)
def decide_run(run_id: str, body: DecisionRequest) -> RunOut:
    try:
        row = service.decide(_parse_run_id(run_id), body.decision)
    except RunNotFoundError as err:
        raise HTTPException(status_code=404, detail="Không tìm thấy run") from err
    except RunStateError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    return _to_out(row)


@app.get("/runs/{run_id}", response_model=RunOut, dependencies=[Depends(require_api_key)])
def get_run(run_id: str) -> RunOut:
    row = service.get(_parse_run_id(run_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy run")
    return _to_out(row)


@app.get("/runs", dependencies=[Depends(require_api_key)])
def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    return service.list_recent(min(max(limit, 1), 100))
