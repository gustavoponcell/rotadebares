from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Tuple


@dataclass(frozen=True)
class Settings:
    user_agent: str = "rota-de-bares"
    request_timeout: int = 30
    overpass_timeout: int = 60
    osrm_timeout: int = 30
    elevation_timeout: int = 30
    retries: int = 5
    backoff_factor: float = 1.0
    retry_statuses: Tuple[int, ...] = (429, 502, 503, 504, 522, 524)
    max_tiles_total: int = 16
    overlap_m: int = 200
    max_workers: int = 4
    max_pois: int = 300
    cache_ttl_seconds: int = 3600
    cache_dir: str = ".cache"
    cache_enabled: bool = True
    cache_persist: bool = True
    osrm_profile: str = "foot"
    osrm_min_auto_reduce: int = 50

    @property
    def cache_path(self) -> Path:
        return Path(self.cache_dir)


DEFAULT_SETTINGS = Settings(
    cache_dir=os.getenv("ROTADEBARES_CACHE_DIR", ".cache"),
    cache_ttl_seconds=int(os.getenv("ROTADEBARES_CACHE_TTL", "3600")),
    cache_enabled=os.getenv("ROTADEBARES_CACHE_ENABLED", "true").lower() in {"1", "true", "yes", "on"},
    cache_persist=os.getenv("ROTADEBARES_CACHE_PERSIST", "true").lower() in {"1", "true", "yes", "on"},
)
