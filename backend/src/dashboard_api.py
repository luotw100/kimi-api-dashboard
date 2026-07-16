import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from models import RequestRecord
from parser import parse_sse_events
from storage import shard_manager


dashboard_router = APIRouter()

SENSITIVE_HEADERS = {
    "authorization",
    "x-api-key",
    "cookie",
    "x-auth-token",
}

# Placeholder pricing for cost estimation. Replace with real Kimi model prices if available.
COST_PER_1M_TOKENS = {
    "claude-opus-4-8": {"input": 15.0, "output": 75.0},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0},
    "default": {"input": 0.0, "output": 0.0},
}


def _mask_sensitive_headers(headers: dict[str, str]) -> dict[str, str]:
    masked = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            masked[key] = "***"
        else:
            masked[key] = value
    return masked


def _to_summary(record: dict[str, Any]) -> dict[str, Any]:
    parsed = record.get("parsed", {})
    duration_ms = parsed.get("duration_ms")
    ttfb_ms = parsed.get("ttfb_ms")
    input_tokens = parsed.get("input_tokens")
    output_tokens = parsed.get("output_tokens")

    # Backfill prefill/decode TPS for older records that don't store them.
    prefill_tps = parsed.get("prefill_tps")
    if prefill_tps is None and ttfb_ms and ttfb_ms > 0 and input_tokens is not None:
        prefill_tps = round(input_tokens / (ttfb_ms / 1000), 2)
    decode_tps = parsed.get("decode_tps")
    if (
        decode_tps is None
        and duration_ms is not None
        and ttfb_ms is not None
        and duration_ms > ttfb_ms
        and output_tokens is not None
    ):
        decode_ms = duration_ms - ttfb_ms
        if decode_ms > 0:
            decode_tps = round(output_tokens / (decode_ms / 1000), 2)

    return {
        "id": record.get("id"),
        "timestamp": record.get("timestamp"),
        "model": record.get("model"),
        "path": record.get("path"),
        "method": record.get("method"),
        "status": record.get("response", {}).get("status"),
        "duration_ms": duration_ms,
        "ttfb_ms": ttfb_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": parsed.get("total_tokens"),
        "error": parsed.get("error"),
        "prefill_tps": prefill_tps,
        "decode_tps": decode_tps,
    }


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * pct / 100
    f = int(k)
    c = min(f + 1, len(values) - 1)
    return round(values[f] + (k - f) * (values[c] - values[f]), 2)


def _floor_minute(ts_str: str) -> str:
    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return ts.replace(second=0, microsecond=0).isoformat()


def _latency_histogram(values: list[float]) -> list[dict[str, Any]]:
    buckets = [500, 1000, 2000, 5000, 10000]
    labels = ["≤500ms", "501-1000ms", "1001-2000ms", "2001-5000ms", "5001-10000ms", ">10000ms"]
    counts = [0] * len(labels)
    for v in values:
        if v is None:
            continue
        for i, upper in enumerate(buckets):
            if v <= upper:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    return [{"bucket": label, "count": count} for label, count in zip(labels, counts)]


def _range_bucket(values: list[int], buckets: list[int]) -> dict[str, int]:
    counts = [0] * (len(buckets) + 1)
    for v in values:
        for i, upper in enumerate(buckets):
            if v <= upper:
                counts[i] += 1
                break
        else:
            counts[-1] += 1
    labels = []
    for i, upper in enumerate(buckets):
        if i == 0:
            labels.append(f"≤{upper}")
        else:
            labels.append(f"{buckets[i - 1] + 1}-{upper}")
    labels.append(f">{buckets[-1]}")
    return {label: count for label, count in zip(labels, counts)}


def _model_price(model: str | None) -> dict[str, float]:
    return COST_PER_1M_TOKENS.get(model or "default", COST_PER_1M_TOKENS["default"])


def _within_window(records: list[dict], window: int) -> list[dict]:
    now = datetime.now(timezone.utc)
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
    return filtered


def _compute_insights(records: list[dict], window: int) -> dict[str, Any]:
    filtered = _within_window(records, window)
    total = len(filtered)

    # Time series grouped by minute
    minute_groups: dict[str, list[dict]] = defaultdict(list)
    for r in filtered:
        minute_groups[_floor_minute(r.get("timestamp", ""))].append(r)

    time_series = []
    for minute in sorted(minute_groups.keys()):
        group = minute_groups[minute]
        reqs = len(group)
        errs = sum(1 for r in group if r.get("response", {}).get("status", 0) >= 400)
        durations = [r["parsed"]["duration_ms"] for r in group if r.get("parsed", {}).get("duration_ms") is not None]
        ttfbs = [r["parsed"]["ttfb_ms"] for r in group if r.get("parsed", {}).get("ttfb_ms") is not None]
        inputs = [r["parsed"]["input_tokens"] for r in group if r.get("parsed", {}).get("input_tokens") is not None]
        outputs = [r["parsed"]["output_tokens"] for r in group if r.get("parsed", {}).get("output_tokens") is not None]
        time_series.append(
            {
                "minute": minute,
                "total_requests": reqs,
                "error_count": errs,
                "total_input_tokens": sum(inputs),
                "total_output_tokens": sum(outputs),
                "total_tokens": sum(inputs) + sum(outputs),
                "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else None,
                "avg_ttfb_ms": round(sum(ttfbs) / len(ttfbs), 2) if ttfbs else None,
            }
        )

    # Latency
    durations = [r["parsed"]["duration_ms"] for r in filtered if r.get("parsed", {}).get("duration_ms") is not None]
    ttfbs = [r["parsed"]["ttfb_ms"] for r in filtered if r.get("parsed", {}).get("ttfb_ms") is not None]
    slowest = sorted(
        [r for r in filtered if r.get("parsed", {}).get("duration_ms") is not None],
        key=lambda r: r["parsed"]["duration_ms"],
        reverse=True,
    )[:5]

    # Model breakdown
    model_groups: dict[str, list[dict]] = defaultdict(list)
    for r in filtered:
        model_groups[r.get("model") or "unknown"].append(r)

    model_breakdown = []
    for model, group in sorted(model_groups.items(), key=lambda x: -len(x[1])):
        durations_m = [r["parsed"]["duration_ms"] for r in group if r.get("parsed", {}).get("duration_ms") is not None]
        ttfbs_m = [r["parsed"]["ttfb_ms"] for r in group if r.get("parsed", {}).get("ttfb_ms") is not None]
        inputs_m = [r["parsed"]["input_tokens"] for r in group if r.get("parsed", {}).get("input_tokens") is not None]
        outputs_m = [r["parsed"]["output_tokens"] for r in group if r.get("parsed", {}).get("output_tokens") is not None]
        errs_m = sum(1 for r in group if r.get("response", {}).get("status", 0) >= 400)
        model_breakdown.append(
            {
                "model": model,
                "count": len(group),
                "total_input_tokens": sum(inputs_m),
                "total_output_tokens": sum(outputs_m),
                "total_tokens": sum(inputs_m) + sum(outputs_m),
                "avg_duration_ms": round(sum(durations_m) / len(durations_m), 2) if durations_m else None,
                "avg_ttfb_ms": round(sum(ttfbs_m) / len(ttfbs_m), 2) if ttfbs_m else None,
                "error_count": errs_m,
            }
        )

    # Path breakdown
    path_groups: dict[str, list[dict]] = defaultdict(list)
    for r in filtered:
        path_groups[r.get("path") or "unknown"].append(r)
    path_breakdown = []
    for path, group in sorted(path_groups.items(), key=lambda x: -len(x[1])):
        errs_p = sum(1 for r in group if r.get("response", {}).get("status", 0) >= 400)
        path_breakdown.append(
            {
                "path": path,
                "count": len(group),
                "error_count": errs_p,
                "error_rate": round(errs_p / len(group), 4) if group else 0,
            }
        )

    # Stop reason / streaming
    stop_reasons = Counter(r.get("parsed", {}).get("stop_reason") or "unknown" for r in filtered)
    streaming_counts = Counter(
        "streaming" if r.get("parsed", {}).get("is_streaming") else "non-streaming" for r in filtered
    )

    # Token efficiency (only meaningful for chat completions)
    message_records = [r for r in filtered if r.get("path") == "/v1/messages"]
    inputs = [r["parsed"]["input_tokens"] for r in message_records if r.get("parsed", {}).get("input_tokens") is not None]
    outputs = [r["parsed"]["output_tokens"] for r in message_records if r.get("parsed", {}).get("output_tokens") is not None]
    cache_creations = [r["parsed"]["cache_creation_input_tokens"] for r in message_records if r.get("parsed", {}).get("cache_creation_input_tokens") is not None]
    cache_reads = [r["parsed"]["cache_read_input_tokens"] for r in message_records if r.get("parsed", {}).get("cache_read_input_tokens") is not None]
    total_input = sum(inputs)
    total_output = sum(outputs)
    total_duration_seconds = sum(r["parsed"]["duration_ms"] or 0 for r in message_records) / 1000
    output_input_ratio = round(total_output / total_input, 4) if total_input else None
    tokens_per_second = round(total_output / total_duration_seconds, 2) if total_duration_seconds else None
    cache_total = sum(cache_creations) + sum(cache_reads)
    cache_hit_rate = round(sum(cache_reads) / cache_total, 4) if cache_total else 0

    # Cost estimate
    by_model: dict[str, dict[str, float]] = {}
    total_input_cost = 0.0
    total_output_cost = 0.0
    for model, group in model_groups.items():
        price = _model_price(model)
        model_inputs = sum(r["parsed"]["input_tokens"] or 0 for r in group if r.get("parsed", {}).get("input_tokens") is not None)
        model_outputs = sum(r["parsed"]["output_tokens"] or 0 for r in group if r.get("parsed", {}).get("output_tokens") is not None)
        input_cost = model_inputs * price["input"] / 1_000_000
        output_cost = model_outputs * price["output"] / 1_000_000
        by_model[model] = {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6),
        }
        total_input_cost += input_cost
        total_output_cost += output_cost

    # Request body stats for /v1/messages
    msg_counts: list[int] = []
    system_lens: list[int] = []
    user_lens: list[int] = []
    tool_counts: list[int] = []
    max_tokens_values: list[int] = []
    streaming_flags: list[bool] = []
    thinking_flags: list[bool] = []
    for r in message_records:
        body = r.get("request", {}).get("body", {}) or {}
        msgs = body.get("messages") or []
        msg_counts.append(len(msgs))
        system = body.get("system")
        system_lens.append(len(str(system)) if system is not None else 0)
        user_lens.append(sum(len(str(m.get("content"))) for m in msgs if m.get("role") == "user"))
        tool_counts.append(len(body.get("tools") or []))
        mt = body.get("max_tokens")
        if mt is not None:
            max_tokens_values.append(int(mt))
        streaming_flags.append(body.get("stream") is True)
        thinking_flags.append(body.get("thinking") is not None)

    max_tokens_dist = _range_bucket(max_tokens_values, [1000, 4000, 16000, 32000, 64000])
    tool_count_dist = Counter(str(c) for c in tool_counts)

    request_body_stats = {
        "total_messages_records": len(message_records),
        "avg_messages_count": round(statistics.mean(msg_counts), 2) if msg_counts else 0,
        "max_messages_count": max(msg_counts) if msg_counts else 0,
        "avg_system_length": round(statistics.mean(system_lens), 2) if system_lens else 0,
        "max_system_length": max(system_lens) if system_lens else 0,
        "avg_user_content_length": round(statistics.mean(user_lens), 2) if user_lens else 0,
        "max_user_content_length": max(user_lens) if user_lens else 0,
        "tool_count_distribution": dict(tool_count_dist),
        "max_tokens_distribution": max_tokens_dist,
        "streaming_ratio": {
            "streaming": sum(1 for f in streaming_flags if f),
            "non_streaming": len(streaming_flags) - sum(1 for f in streaming_flags if f),
        },
        "thinking_ratio": {
            "thinking": sum(1 for f in thinking_flags if f),
            "non_thinking": len(thinking_flags) - sum(1 for f in thinking_flags if f),
        },
    }

    return {
        "window_minutes": window,
        "total_requests": total,
        "time_series": time_series,
        "latency": {
            "p50_duration_ms": _percentile(durations, 50),
            "p95_duration_ms": _percentile(durations, 95),
            "p99_duration_ms": _percentile(durations, 99),
            "p50_ttfb_ms": _percentile(ttfbs, 50),
            "p95_ttfb_ms": _percentile(ttfbs, 95),
            "p99_ttfb_ms": _percentile(ttfbs, 99),
            "histogram": _latency_histogram(durations),
            "top_slow": [_to_summary(r) for r in slowest],
        },
        "model_breakdown": model_breakdown,
        "path_breakdown": path_breakdown,
        "stop_reason_distribution": dict(stop_reasons),
        "streaming_ratio": dict(streaming_counts),
        "token_efficiency": {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output,
            "output_input_ratio": output_input_ratio,
            "tokens_per_second": tokens_per_second,
            "cache_creation_input_tokens": sum(cache_creations),
            "cache_read_input_tokens": sum(cache_reads),
            "cache_hit_rate": cache_hit_rate,
        },
        "request_body_stats": request_body_stats,
        "cost_estimate": {
            "total_input_cost": round(total_input_cost, 6),
            "total_output_cost": round(total_output_cost, 6),
            "total_cost": round(total_input_cost + total_output_cost, 6),
            "by_model": by_model,
        },
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

    # Mask sensitive headers before returning to UI
    record["request"]["headers"] = _mask_sensitive_headers(record.get("request", {}).get("headers", {}))

    # Parse SSE events for streaming responses so the UI can render them nicely
    body = record.get("response", {}).get("body", "")
    content_type = record.get("response", {}).get("headers", {}).get("content-type", "")
    if "text/event-stream" in content_type or body.startswith("event:"):
        record["events"] = parse_sse_events(body)

    return JSONResponse(record)


@dashboard_router.get("/api/metrics")
async def metrics(window: int = Query(60, ge=1, le=10080)):
    """Return aggregated metrics for the last N minutes."""
    records = await shard_manager.read_all_records(limit=10000, offset=0)
    filtered = _within_window(records, window)

    total = len(filtered)
    errors = [r for r in filtered if r.get("response", {}).get("status", 0) >= 400]
    durations = [r["parsed"]["duration_ms"] for r in filtered if r.get("parsed", {}).get("duration_ms") is not None]
    ttfbs = [r["parsed"]["ttfb_ms"] for r in filtered if r.get("parsed", {}).get("ttfb_ms") is not None]
    input_tokens = [r["parsed"]["input_tokens"] for r in filtered if r.get("parsed", {}).get("input_tokens") is not None]
    output_tokens = [r["parsed"]["output_tokens"] for r in filtered if r.get("parsed", {}).get("output_tokens") is not None]

    model_counts = Counter(r.get("model") or "unknown" for r in filtered)
    path_counts = Counter(r.get("path") or "unknown" for r in filtered)

    return JSONResponse(
        {
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
            "p99_duration_ms": _percentile(durations, 99),
            "p50_ttfb_ms": _percentile(ttfbs, 50),
            "p95_ttfb_ms": _percentile(ttfbs, 95),
            "p99_ttfb_ms": _percentile(ttfbs, 99),
            "model_distribution": dict(model_counts),
            "path_distribution": dict(path_counts),
        }
    )


@dashboard_router.get("/api/insights")
async def insights(window: int = Query(60, ge=1, le=10080)):
    """Return deep insights for the last N minutes."""
    records = await shard_manager.read_all_records(limit=10000, offset=0)
    return JSONResponse(_compute_insights(records, window))
