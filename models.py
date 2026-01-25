from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class POI:
    poi_id: str
    name: str
    lat: float
    lon: float
    source: str
    amenity: Optional[str] = None
    category: Optional[str] = None
    raw_tags: Dict[str, Any] = field(default_factory=dict)
    osm_type: Optional[str] = None
    osm_id: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def display_name(self) -> str:
        suffix = self.amenity or self.category
        return f"{self.name} ({suffix})" if suffix else self.name

    def text_blob(self) -> str:
        parts: List[str] = [self.name]
        for value in (self.amenity, self.category):
            if value:
                parts.append(value)
        for value in self.extra.values():
            if value:
                parts.append(str(value))
        for value in self.raw_tags.values():
            if value:
                parts.append(str(value))
        parts.extend(str(key) for key in self.raw_tags.keys() if key)
        return " ".join(parts)


@dataclass
class RouteResult:
    order: List[int]
    distance_cost: Optional[float]
    html_path: Optional[str]
    warnings: List[str] = field(default_factory=list)
    map_html: str = ""


__all__ = ["POI", "RouteResult"]
