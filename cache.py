from __future__ import annotations

import hashlib
import json
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from loguru import logger

from config import DEFAULT_SETTINGS, Settings


@dataclass
class CacheEntry:
    timestamp: float
    value: Any


class CacheManager:
    def __init__(self, settings: Settings = DEFAULT_SETTINGS) -> None:
        self.settings = settings
        self._memory: Dict[str, CacheEntry] = {}
        self._dir = settings.cache_path
        if settings.cache_persist:
            self._dir.mkdir(parents=True, exist_ok=True)

    def _is_fresh(self, entry: CacheEntry) -> bool:
        ttl = self.settings.cache_ttl_seconds
        if ttl <= 0:
            return False
        return (time.time() - entry.timestamp) <= ttl

    def _disk_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{digest}.pkl"

    def get(self, key: str) -> Optional[Any]:
        if not self.settings.cache_enabled:
            return None
        entry = self._memory.get(key)
        if entry:
            if self._is_fresh(entry):
                logger.debug("Cache HIT (mem): %s", key)
                return entry.value
            logger.debug("Cache STALE (mem): %s", key)
            self._memory.pop(key, None)
        if self.settings.cache_persist:
            path = self._disk_path(key)
            if path.exists():
                try:
                    with path.open("rb") as handle:
                        entry = pickle.load(handle)
                    if isinstance(entry, CacheEntry) and self._is_fresh(entry):
                        logger.debug("Cache HIT (disk): %s", key)
                        self._memory[key] = entry
                        return entry.value
                    logger.debug("Cache STALE (disk): %s", key)
                    path.unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning("Cache read error (%s): %s", key, exc)
        logger.debug("Cache MISS: %s", key)
        return None

    def set(self, key: str, value: Any) -> None:
        if not self.settings.cache_enabled:
            return
        entry = CacheEntry(timestamp=time.time(), value=value)
        self._memory[key] = entry
        if self.settings.cache_persist:
            try:
                with self._disk_path(key).open("wb") as handle:
                    pickle.dump(entry, handle)
            except Exception as exc:
                logger.warning("Cache write error (%s): %s", key, exc)

    def clear(self) -> None:
        self._memory.clear()
        if self.settings.cache_persist and self._dir.exists():
            for file in self._dir.glob("*.pkl"):
                file.unlink(missing_ok=True)
        logger.info("Cache limpo.")


DEFAULT_CACHE = CacheManager()


def make_cache_key(prefix: str, payload: Dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def stable_coords(coords: Iterable[Iterable[float]], precision: int = 6) -> list[list[float]]:
    rounded: list[list[float]] = []
    for coord in coords:
        lat, lon = coord
        rounded.append([round(float(lat), precision), round(float(lon), precision)])
    return rounded


__all__ = ["CacheManager", "DEFAULT_CACHE", "make_cache_key", "stable_coords"]
