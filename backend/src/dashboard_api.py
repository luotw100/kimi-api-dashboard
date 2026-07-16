import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from models import RequestRecord
from storage import shard_manager


dashboard_router = APIRouter()


def _to_summary(record: dict[str, Any]) -> dict[str, Any]:
    parsed = record.get("parsed", {})
    return {
        "id": record.get("id"),
        "timestamp": record.get("timestamp"),
        "model": record.get("model"),
        "path": record.get("path"),
        "method": record.get("method"),
        "status": record.get("response", {}).get("status"),
        "duration_ms": parsed.get("duration_ms"),
        "ttfb_ms": parsed.get("ttfb_ms"),
        "input_tokens": parsed.get("input_tokens"),
        "output_tokens": parsed.get("output_tokens"),
        "total_tokens": parsed.get("total_tokens"),
        "error": parsed.get("error"),
    }


@dashboard_router.get("/api/health")
async def health():
    return {"status": "ok"}


_ALLOWED_PAGE_SIZES = {10, 20, 50, 100}


def _validate_pagination(limit: int, offset: int) -> None:
    """Reject non-conventional pagination parameters."""
    if limit not in _ALLOWED_PAGE_SIZES:
        raise HTTPException(
            status_code=400,
            detail=f"limit must be one of {sorted(_ALLOWED_PAGE_SIZES)}",
        )
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative")
    if offset % limit != 0:
        raise HTTPException(status_code=400, detail="offset must be a multiple of limit")


def _filter_summary(summary: dict[str, Any], model: str | None, path: str | None, status: int | None) -> bool:
    if model is not None and summary.get("model") != model:
        return False
    if path is not None and summary.get("path") != path:
        return False
    if status is not None and summary.get("status") != status:
        return False
    return True


@dashboard_router.get("/api/requests")
async def list_requests(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    model: str | None = Query(None),
    path: str | None = Query(None),
    status: int | None = Query(None),
):
    _validate_pagination(limit, offset)
    records = await shard_manager.read_all_records(limit=None, offset=0)
    filtered = [
        summary
        for record in records
        if _filter_summary(summary := _to_summary(record), model, path, status)
    ]
    total = len(filtered)
    paginated = filtered[offset:offset + limit]
    return JSONResponse({"items": paginated, "limit": limit, "offset": offset, "total": total})


@dashboard_router.get("/api/requests/{request_id}")
async def get_request(request_id: str):
    record = await shard_manager.read_record_by_id(request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    return JSONResponse(record)


@dashboard_router.get("/api/metrics")
async def metrics(window: int = Query(60, ge=1, le=10080)):
    """Return aggregated metrics for the last  minutes."""
    now = datetime.now(timezone.utc)
    records = await shard_manager.read_all_records(limit=10000, offset=0)

    cutoff = now.timestamp() - window * 60
    filtered = []
    for r in records:
        ts_str = r.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            continue
        if ts.timestamp() >= cutoff:
            filtered.append(r)

    total = len(filtered)
    errors = [r for r in filtered if r.get("response", {}).get("status", 0) >= 400]
    durations = [r.get("parsed", {}).get("duration_ms", 0) for r in filtered if r.get("parsed", {}).get("duration_ms") is not None]
    input_tokens = [r.get("parsed", {}).get("input_tokens", 0) for r in filtered if r.get("parsed", {}).get("input_tokens") is not None]
    output_tokens = [r.get("parsed", {}).get("output_tokens", 0) for r in filtered if r.get("parsed", {}).get("output_tokens") is not None]

    model_counts = Counter(r.get("model", "unknown") for r in filtered)
    path_counts = Counter(r.get("path", "unknown") for r in filtered)

    def _percentile(values, pct):
        if not values:
            return None
        values = sorted(values)
        k = (len(values) - 1) * pct / 100
        f = int(k)
        c = min(f + 1, len(values) - 1)
        return round(values[f] + (k - f) * (values[c] - values[f]), 2)

    return JSONResponse({
        "window_minutes": window,
        "total_requests": total,
        "error_count": len(errors),
        "error_rate": round(len(errors) / total, 4) if total else 0,
        "total_input_tokens": sum(input_tokens),
        "total_output_tokens": sum(output_tokens),
        "total_tokens": sum(input_tokens) + sum(output_tokens),
        "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else None,
        "p50_duration_ms": _percentile(durations, 50),
        "p95_duration_ms": _percentile(durations, 95),
        "model_distribution": dict(model_counts),
        "path_distribution": dict(path_counts),
    })
