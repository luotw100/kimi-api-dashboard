import json
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from models import RequestSummary, WSEvent


class WebSocketManager:
    """Simple in-memory WebSocket manager for dashboard clients."""

    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.connections:
            self.connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]):
        text = json.dumps(message, ensure_ascii=False, default=str)
        disconnected = []
        for conn in self.connections:
            try:
                await conn.send_text(text)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_request_finished(self, record: dict[str, Any]):
        parsed = record.get("parsed", {})
        summary = RequestSummary(
            id=record.get("id", ""),
            timestamp=record.get("timestamp", ""),
            model=record.get("model"),
            path=record.get("path", ""),
            status=record.get("response", {}).get("status", 0),
            duration_ms=parsed.get("duration_ms"),
            ttfb_ms=parsed.get("ttfb_ms"),
            input_tokens=parsed.get("input_tokens"),
            output_tokens=parsed.get("output_tokens"),
        )
        event = WSEvent(type="request_finished", payload=summary)
        await self.broadcast(event.model_dump())


ws_manager = WebSocketManager()


ws_app = FastAPI()


@ws_app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; clients may send pings or commands in the future.
            data = await websocket.receive_text()
            # Echo heartbeat if client sends one
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
