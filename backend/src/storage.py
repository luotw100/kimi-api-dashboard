import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiofiles

from config import config


class ShardManager:
    """Manages JSONL shard files for API request logs."""

    def __init__(self):
        self.data_dir = config.DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.active_file = self.data_dir / "requests-active.jsonl"
        self.shard_size = config.SHARD_SIZE_BYTES
        self.max_size = config.MAX_DATA_SIZE_BYTES
        self._write_lock = asyncio.Lock()

    def _new_shard_name(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        seq = 1
        while True:
            name = f"requests-{ts}-{seq:06d}.jsonl"
            path = self.data_dir / name
            if not path.exists() and name != self.active_file.name:
                return name
            seq += 1

    async def _rotate_if_needed(self) -> None:
        if self.active_file.exists():
            size = self.active_file.stat().st_size
            if size >= self.shard_size:
                new_name = self._new_shard_name()
                new_path = self.data_dir / new_name
                self.active_file.rename(new_path)
                # active file will be created on next append

    async def append(self, record: dict) -> None:
        async with self._write_lock:
            await self._rotate_if_needed()
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            async with aiofiles.open(self.active_file, "a", encoding="utf-8") as f:
                await f.write(line)
                await f.flush()

    def list_shards(self, newest_first: bool = True) -> list[Path]:
        """Return all completed shards plus active file (last)."""
        shards = sorted(
            [p for p in self.data_dir.iterdir() if p.is_file() and p.name.endswith(".jsonl")],
            key=lambda p: p.stat().st_mtime,
        )
        if newest_first:
            shards.reverse()
        return shards

    def _get_total_size(self) -> int:
        total = 0
        for p in self.data_dir.iterdir():
            if p.is_file() and p.name.endswith(".jsonl"):
                total += p.stat().st_size
        return total

    async def cleanup(self) -> None:
        """Delete oldest shards until total size is below max."""
        async with self._write_lock:
            while True:
                total = self._get_total_size()
                if total <= self.max_size:
                    break

                # Find oldest shard, excluding active file
                shards = [
                    p for p in self.data_dir.iterdir()
                    if p.is_file() and p.name.endswith(".jsonl") and p.name != self.active_file.name
                ]
                if not shards:
                    break
                oldest = min(shards, key=lambda p: p.stat().st_mtime)
                try:
                    oldest.unlink()
                except OSError:
                    break

    async def read_all_records(self, limit: int | None = None, offset: int = 0) -> list[dict]:
        """Read records from newest to oldest, with limit/offset."""
        records = []
        skipped = 0
        shards = self.list_shards(newest_first=True)
        for shard in shards:
            try:
                async with aiofiles.open(shard, "r", encoding="utf-8") as f:
                    lines = await f.readlines()
            except OSError:
                continue
            # Each shard is chronologically ordered; reading newest first means reverse each shard
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if limit is not None and len(records) >= limit:
                    return records
        return records

    async def read_record_by_id(self, request_id: str) -> dict | None:
        shards = self.list_shards(newest_first=True)
        for shard in shards:
            try:
                async with aiofiles.open(shard, "r", encoding="utf-8") as f:
                    lines = await f.readlines()
            except OSError:
                continue
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("id") == request_id:
                        return record
                except json.JSONDecodeError:
                    continue
        return None


shard_manager = ShardManager()
