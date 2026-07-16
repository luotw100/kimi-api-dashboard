from typing import Any

from pydantic import BaseModel, Field


class RequestRecord(BaseModel):
    id: str
    timestamp: str
    method: str
    path: str
    model: str | None = None
    request: dict[str, Any]
    response: dict[str, Any]
    parsed: dict[str, Any]


class RequestSummary(BaseModel):
    id: str
    timestamp: str
    model: str | None
    path: str
    status: int
    duration_ms: float | None
    ttfb_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    prefill_tps: float | None
    decode_tps: float | None


class WSEvent(BaseModel):
    type: str
    payload: RequestSummary | dict[str, Any]
