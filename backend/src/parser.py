import json
from typing import Any


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_nested(data: Any, key: str) -> Any | None:
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            found = _find_nested(v, key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_nested(item, key)
            if found is not None:
                return found
    return None


def _find_all_nested(data: Any, key: str) -> list[Any]:
    results = []
    if isinstance(data, dict):
        if key in data:
            results.append(data[key])
        for v in data.values():
            results.extend(_find_all_nested(v, key))
    elif isinstance(data, list):
        for item in data:
            results.extend(_find_all_nested(item, key))
    return results


def _parse_sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload == "[DONE]":
                continue
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
    return events


def parse_request_body(body: bytes | str) -> dict[str, Any]:
    if isinstance(body, bytes):
        try:
            body = body.decode("utf-8")
        except UnicodeDecodeError:
            return {}
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def extract_model(request_body: dict[str, Any]) -> str | None:
    return request_body.get("model") or request_body.get("model_name")


def _calc_input_tokens(usage: dict) -> int | None:
    base = _safe_int(usage.get("input_tokens"))
    cache_creation = _safe_int(usage.get("cache_creation_input_tokens"))
    cache_read = _safe_int(usage.get("cache_read_input_tokens"))
    total = 0
    has_any = False
    for v in (base, cache_creation, cache_read):
        if v is not None:
            total += v
            has_any = True
    return total if has_any else None


def parse_response_for_usage(
    status_code: int,
    response_body: str | bytes,
    is_streaming: bool,
) -> dict[str, Any]:
    result = {
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "stop_reason": None,
        "error": None,
    }

    if status_code >= 400:
        result["error"] = f"HTTP {status_code}"
        return result

    if isinstance(response_body, bytes):
        try:
            response_body = response_body.decode("utf-8")
        except UnicodeDecodeError:
            return result

    if not response_body:
        return result

    if is_streaming:
        events = _parse_sse_events(response_body)
        input_tokens = None
        output_tokens = None
        stop_reason = None

        for event in events:
            event_type = event.get("type", "")
            usage = event.get("usage")
            if usage and isinstance(usage, dict):
                if input_tokens is None:
                    input_tokens = _calc_input_tokens(usage)
                if "output_tokens" in usage:
                    output_tokens = _safe_int(usage.get("output_tokens"))

            if input_tokens is None:
                input_tokens = _safe_int(_find_nested(event, "input_tokens"))
            if output_tokens is None:
                output_tokens = _safe_int(_find_nested(event, "output_tokens"))
            else:
                last_output = _safe_int(_find_nested(event, "output_tokens"))
                if last_output is not None:
                    output_tokens = last_output

            if event_type in ("message_delta", "message_stop", "content_block_stop"):
                sr = event.get("delta", {}).get("stop_reason") if isinstance(event.get("delta"), dict) else None
                if sr:
                    stop_reason = sr
                if not stop_reason and "stop_reason" in event:
                    stop_reason = event.get("stop_reason")

        if output_tokens is None:
            all_output = [_safe_int(v) for v in _find_all_nested(events, "output_tokens") if _safe_int(v) is not None]
            if all_output:
                output_tokens = all_output[-1]
        if input_tokens is None:
            all_input = [_safe_int(v) for v in _find_all_nested(events, "input_tokens") if _safe_int(v) is not None]
            if all_input:
                input_tokens = all_input[0]

        result["input_tokens"] = input_tokens
        result["output_tokens"] = output_tokens
        result["stop_reason"] = stop_reason

    else:
        try:
            data = json.loads(response_body)
        except json.JSONDecodeError:
            return result

        usage = data.get("usage") if isinstance(data, dict) else None
        if usage and isinstance(usage, dict):
            result["input_tokens"] = _calc_input_tokens(usage)
            result["output_tokens"] = _safe_int(usage.get("output_tokens"))

        if isinstance(data, dict):
            result["stop_reason"] = data.get("stop_reason")

    if result["input_tokens"] is not None or result["output_tokens"] is not None:
        result["total_tokens"] = (result["input_tokens"] or 0) + (result["output_tokens"] or 0)

    return result


def is_streaming_request(request_body: dict[str, Any]) -> bool:
    return request_body.get("stream") is True
