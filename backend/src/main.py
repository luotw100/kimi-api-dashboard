import asyncio
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from config import config
from dashboard_api import dashboard_router
from dashboard_ws import ws_manager
from proxy import proxy_app
from storage import shard_manager


async def cleanup_task():
    """Background task to enforce data size limits."""
    while True:
        await asyncio.sleep(config.CLEANUP_INTERVAL_SECONDS)
        try:
            await shard_manager.cleanup()
        except Exception as e:
            print(f"Cleanup error: {e}")


@asynccontextmanager
async def dashboard_lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_task())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def make_dashboard_server_app():
    """Combine dashboard API, WebSocket, and static files into one ASGI app."""
    app = FastAPI(lifespan=dashboard_lifespan)

    # Include API routes
    app.include_router(dashboard_router)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
                else:
                    await websocket.send_text(f"echo: {data}")
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            ws_manager.disconnect(websocket)
            try:
                await websocket.close()
            except Exception:
                pass

    # Static files from frontend/dist (must be last, acts as catch-all fallback)
    dist_dir = config.FRONTEND_DIST_DIR
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")

    return app


def run_proxy():
    uvicorn.run(proxy_app, host="0.0.0.0", port=config.PROXY_PORT, log_level=config.LOG_LEVEL)


def run_dashboard():
    app = make_dashboard_server_app()
    uvicorn.run(app, host="0.0.0.0", port=config.DASHBOARD_PORT, log_level=config.LOG_LEVEL)


if __name__ == "__main__":
    print(f"Starting proxy server on port {config.PROXY_PORT}")
    print(f"Starting dashboard server on port {config.DASHBOARD_PORT}")

    proxy_thread = threading.Thread(target=run_proxy, daemon=True)
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)

    proxy_thread.start()
    dashboard_thread.start()

    proxy_thread.join()
    dashboard_thread.join()
