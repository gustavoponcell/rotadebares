from __future__ import annotations

from typing import Dict, List, Optional, Protocol, Tuple

from loguru import logger

from config import DEFAULT_SETTINGS, Settings
from data_fetch import PoisFetchResult, batch_altitude, coletar_pois, osrm_table
from models import POI
from overture_fetch import fetch_overture_places


class PlacesProvider(Protocol):
    def fetch_places(
        self,
        bbox: Optional[Tuple[float, float, float, float]],
        filters: Dict[str, object],
    ) -> List[POI]:
        ...


class DistanceProvider(Protocol):
    def table(self, coords: List[Tuple[float, float]]) -> List[List[float]] | None:
        ...


class ElevationProvider(Protocol):
    def batch(self, coords: List[Tuple[float, float]]) -> List[float]:
        ...


class RouteGeometryProvider(Protocol):
    def route(self, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        ...


class OverpassPlacesProvider:
    def __init__(self, settings: Settings = DEFAULT_SETTINGS) -> None:
        self.settings = settings
        self.last_report: Optional[PoisFetchResult] = None

    def fetch_places(
        self,
        bbox: Optional[Tuple[float, float, float, float]],
        filters: Dict[str, object],
    ) -> List[POI]:
        city = str(filters.get("city", "")).strip()
        amenities = filters.get("amenities")
        amenities_list = list(amenities) if amenities else None
        result = coletar_pois(
            city,
            selected_amenities=amenities_list,
            max_tiles_total=int(filters.get("max_tiles_total", self.settings.max_tiles_total)),
            overlap_m=int(filters.get("overlap_m", self.settings.overlap_m)),
            max_workers=int(filters.get("max_workers", self.settings.max_workers)),
        )
        self.last_report = result
        return result.pois


class OverturePlacesProvider:
    def fetch_places(
        self,
        bbox: Optional[Tuple[float, float, float, float]],
        filters: Dict[str, object],
    ) -> List[POI]:
        if not bbox:
            return []
        try:
            return fetch_overture_places(
                (bbox[2], bbox[0], bbox[3], bbox[1]),
                limit=int(filters.get("limit", 300)),
            )
        except Exception as exc:
            logger.warning("Falha Overture: %s", exc)
            raise


class OSRMProvider:
    def __init__(self, settings: Settings = DEFAULT_SETTINGS) -> None:
        self.settings = settings

    def table(self, coords: List[Tuple[float, float]]) -> List[List[float]] | None:
        return osrm_table(coords, timeout=self.settings.osrm_timeout, profile=self.settings.osrm_profile)


class OpenElevationProvider:
    def __init__(self, settings: Settings = DEFAULT_SETTINGS) -> None:
        self.settings = settings

    def batch(self, coords: List[Tuple[float, float]]) -> List[float]:
        return batch_altitude(coords, timeout=self.settings.elevation_timeout)


__all__ = [
    "PlacesProvider",
    "DistanceProvider",
    "ElevationProvider",
    "RouteGeometryProvider",
    "OverpassPlacesProvider",
    "OverturePlacesProvider",
    "OSRMProvider",
    "OpenElevationProvider",
]
