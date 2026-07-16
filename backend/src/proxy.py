import asyncio
import gzip
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from config import config
from dashboard_ws import ws_manager
from parser import (
    extract_model,
    is_streaming_request,
    parse_request_body,
    parse_response_for_usage,
)
from storage import shard_manager


proxy_app = FastAPI()


async def _read_request_body(request: Request) -> bytes:
    chunks = []
    async for chunk in request.stream():
        chunks.append(chunk)
    return b"".join(chunks)


def _build_upstream_url(path: str, query: str) -> str:
    base = config.UPSTREAM_BASE_URL.rstrip("/")
    url = f"{base}{path}"
    if query:
        url = f"{url}?{query}"
    return url


def _fastapi_headers_to_dict(headers) -> dict[str, str]:
    return {k: v for k, v in headers.items()}


def _httpx_headers_to_dict(headers: httpx.Headers) -> dict[str, str]:
    return dict(headers)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _log_record(
    request_id: str,
    start_iso: str,
    request: Request,
    body: bytes,
    request_body_json: dict,
    model: str | None,
    is_streaming: bool,
    response_status: int,
    response_headers: dict[str, str],
    response_body_parts: list[bytes],
    start_time: float,
    ttfb_ms: float | None,
) -> None:
    duration_ms = round((time.time() - start_time) * 1000, 2)
    response_body = b"".join(response_body_parts)
    if response_headers.get("content-encoding") == "gzip":
        try:
            response_body = gzip.decompress(response_body)
        except Exception:
            pass
    try:
        response_body_text = response_body.decode("utf-8")
    except UnicodeDecodeError:
        response_body_text = response_body.decode("utf-8", errors="replace")

    parsed = parse_response_for_usage(response_status, response_body_text, is_streaming)
    parsed["duration_ms"] = duration_ms
    parsed["ttfb_ms"] = ttfb_ms
    parsed["is_streaming"] = is_streaming

    # Compute prefill / decode throughput for LLM calls.
    # Prefill: input tokens processed before first output byte (approximated by TTFB).
    # Decode: output tokens generated after first byte until response ends.
    input_tokens = parsed.get("input_tokens")
    output_tokens = parsed.get("output_tokens")
    if ttfb_ms and ttfb_ms > 0 and input_tokens is not None:
        parsed["prefill_tps"] = round(input_tokens / (ttfb_ms / 1000), 2)
    else:
        parsed["prefill_tps"] = None
    if (
        duration_ms is not None
        and ttfb_ms is not None
        and duration_ms > ttfb_ms
        and output_tokens is not None
    ):
        decode_ms = duration_ms - ttfb_ms
        if decode_ms > 0:
            parsed["decode_tps"] = round(output_tokens / (decode_ms / 1000), 2)
        else:
            parsed["decode_tps"] = None
    else:
        parsed["decode_tps"] = None

    record = {
        "id": request_id,
        "timestamp": start_iso,
        "method": request.method,
        "path": request.url.path,
        "model": model,
        "request": {
            "headers": _fastapi_headers_to_dict(request.headers),
            "body": request_body_json,
        },
        "response": {
            "status": response_status,
            "headers": response_headers,
            "body": response_body_text,
        },
        "parsed": parsed,
    }

    await shard_manager.append(record)
    await ws_manager.broadcast_request_finished(record)


@proxy_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_all(request: Request, path: str = ""):
    return await _proxy_request(request, f"/{path}")


async def _proxy_request(request: Request, path: str) -> StreamingResponse:
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    start_time = time.time()
    start_iso = _now_iso()

    body = await _read_request_body(request)
    request_body_json = parse_request_body(body)
    model = extract_model(request_body_json)
    is_streaming = is_streaming_request(request_body_json)

    upstream_url = _build_upstream_url(path, request.url.query)
    headers = _fastapi_headers_to_dict(request.headers)
    headers.pop("host", None)
    headers.pop("connection", None)
    headers.pop("accept-encoding", None)

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=None, write=10.0, pool=5.0),
        follow_redirects=False,
    )

    try:
        upstream_response = await client.send(
            client.build_request(
                method=request.method,
                url=upstream_url,
                headers=headers,
                content=body,
            ),
            stream=True,
        )
    except Exception as e:
        await client.aclose()
        msg = f"Proxy error: {e}".encode("utf-8")
        error_status = 502
        error_headers = {"content-type": "text/plain"}
        error_body_parts = [msg]
        error_ttfb_ms = round((time.time() - start_time) * 1000, 2)
        asyncio.create_task(
            _log_record(
                request_id,
                start_iso,
                request,
                body,
                request_body_json,
                model,
                is_streaming,
                error_status,
                error_headers,
                error_body_parts,
                start_time,
                error_ttfb_ms,
            )
        )
        return StreamingResponse(
            iter([msg]),
            status_code=error_status,
            headers=error_headers,
            media_type="text/plain",
        )

    response_status = upstream_response.status_code
    response_headers = _httpx_headers_to_dict(upstream_response.headers)
    ttfb_ms = round((time.time() - start_time) * 1000, 2)
    response_body_parts: list[bytes] = []

    async def stream_response():
        try:
            async for chunk in upstream_response.aiter_raw():
                response_body_parts.append(chunk)
                yield chunk
        finally:
            await upstream_response.aclose()
            await client.aclose()
            asyncio.create_task(
                _log_record(
                    request_id,
                    start_iso,
                    request,
                    body,
                    request_body_json,
                    model,
                    is_streaming,
                    response_status,
                    response_headers,
                    response_body_parts,
                    start_time,
                    ttfb_ms,
                )
            )

    return StreamingResponse(
        stream_response(),
        status_code=response_status,
        headers=response_headers,
        media_type=response_headers.get("content-type", "application/octet-stream"),
    )
