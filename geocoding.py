import logging
from functools import lru_cache
from typing import Optional, Tuple

from geopy.geocoders import Nominatim, Photon
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderTimedOut

log = logging.getLogger(__name__)

# Inicializa geocoders e cache
geolocator = Nominatim(user_agent="tsp_app", timeout=10)
photon = Photon(user_agent="tsp_app", timeout=10)
_city_geolocator = Nominatim(user_agent="tsp_app_bbox", timeout=10)

geocode_rl = RateLimiter(geolocator.geocode, min_delay_seconds=1)
photon_geocode_rl = RateLimiter(photon.geocode, min_delay_seconds=1)

_cache_geo = {}


@lru_cache(maxsize=64)
def get_city_bbox(city_name: str) -> Optional[Tuple[float, float, float, float]]:
    """Retorna a bounding box (sul, norte, oeste, leste) da cidade."""
    loc = _city_geolocator.geocode(
        {"city": city_name, "state": "Minas Gerais", "country": "Brazil"},
        exactly_one=True,
    )
    if not loc or "boundingbox" not in loc.raw:
        return None
    sb, nb, wb, eb = loc.raw["boundingbox"]
    return float(sb), float(nb), float(wb), float(eb)


def dentro_da_cidade(lat: float, lon: float, bbox: Tuple[float, float, float, float]) -> bool:
    s, n, w, e = bbox
    return s <= lat <= n and w <= lon <= e


def geocode_strict_single(address: str, city: str) -> Optional[Tuple[float, float]]:
    """Geocoding restrito à cidade usando viewbox."""
    key = f"strict|{address}|{city}"
    if key in _cache_geo:
        return _cache_geo[key]
    bbox = get_city_bbox(city)
    params = {"street": address, "city": city, "state": "Minas Gerais", "country": "Brazil"}
    try:
        if bbox:
            sb, nb, wb, eb = bbox
            viewbox = [(sb, wb), (nb, eb)]
            loc = geocode_rl(params, exactly_one=True, viewbox=viewbox, bounded=True)
        else:
            loc = geocode_rl(params, exactly_one=True)
        if loc and (not bbox or dentro_da_cidade(loc.latitude, loc.longitude, bbox)):
            return _cache_geo.setdefault(key, (loc.latitude, loc.longitude))
    except GeocoderTimedOut:
        pass
    return None


def geocode_fallback_single(address: str, city: str) -> Optional[Tuple[float, float]]:
    """Geocoding de fallback usando Nominatim e Photon."""
    key = f"fallback|{address}|{city}"
    if key in _cache_geo:
        return _cache_geo[key]
    bbox = get_city_bbox(city)
    try:
        loc = geocode_rl(
            {"street": address, "city": city, "state": "Minas Gerais", "country": "Brazil"},
            exactly_one=True,
        )
        if loc and (not bbox or dentro_da_cidade(loc.latitude, loc.longitude, bbox)):
            return _cache_geo.setdefault(key, (loc.latitude, loc.longitude))
    except Exception:
        pass
    try:
        loc2 = photon_geocode_rl(f"{address}, {city}, MG, Brazil", exactly_one=True)
        if loc2 and (not bbox or dentro_da_cidade(loc2.latitude, loc2.longitude, bbox)):
            return _cache_geo.setdefault(key, (loc2.latitude, loc2.longitude))
    except Exception:
        pass
    return None

__all__ = [
    "get_city_bbox",
    "dentro_da_cidade",
    "geocode_strict_single",
    "geocode_fallback_single",
]
