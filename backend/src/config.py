import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


class Config:
    # Ports
    PROXY_PORT: int = int(os.getenv("PROXY_PORT", "8787"))
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8788"))

    # Upstream API
    UPSTREAM_BASE_URL: str = os.getenv("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")

    # Data storage: env var may be relative to project root or absolute
    DATA_DIR: Path = PROJECT_ROOT / os.getenv("DATA_DIR", "./data")
    SHARD_SIZE_BYTES: int = int(os.getenv("SHARD_SIZE_BYTES", str(256 * 1024 * 1024)))
    MAX_DATA_SIZE_BYTES: int = int(os.getenv("MAX_DATA_SIZE_BYTES", str(20 * 1024 * 1024 * 1024)))
    CLEANUP_INTERVAL_SECONDS: int = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "600"))

    # Frontend static files
    FRONTEND_DIST_DIR: Path = PROJECT_ROOT / "frontend" / "dist"

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")


config = Config()
