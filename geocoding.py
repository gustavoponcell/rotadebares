import logging
from functools import lru_cache
from typing import Optional, Tuple, Any

try:  # Shapely é opcional
    from shapely.geometry import Polygon, Point
except Exception:  # pragma: no cover - biblioteca ausente
    Polygon = None  # type: ignore
    Point = None  # type: ignore

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
def get_city_area_id(city_name: str) -> Optional[int]:
    """Retorna o ``area id`` da cidade no Overpass."""
    q = f"""
    [out:json][timeout:25];
    rel["name"="{city_name}"]["boundary"="administrative"]["admin_level"="8"];out ids;
    """
    try:
        resp = requests.post(
            "http://overpass-api.de/api/interpreter", data={"data": q}, timeout=25
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        if elements:
            rel_id = elements[0]["id"]
            return 3600000000 + rel_id
    except Exception as e:  # pragma: no cover - log apenas
        log.error(f"Erro ao obter area id: {e}")
    return None


@lru_cache(maxsize=64)
def get_city_polygon(city_name: str) -> Optional[Any]:
    """Obtém o polígono da cidade como ``Polygon`` do Shapely."""
    if Polygon is None:
        return None
    area_id = get_city_area_id(city_name)
    if not area_id:
        return None
    q = f"""
    [out:json][timeout:25];
    area({area_id})->.a;
    rel(area.a)[boundary="administrative"][admin_level="8"];out geom;
    """
    try:
        resp = requests.post(
            "http://overpass-api.de/api/interpreter", data={"data": q}, timeout=25
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
        if not elements:
            return None
        coords = [(p["lon"], p["lat"]) for p in elements[0].get("geometry", [])]
        if coords:
            return Polygon(coords)
    except Exception as e:  # pragma: no cover - log apenas
        log.error(f"Erro ao obter polígono: {e}")
    return None


def point_in_polygon(lat: float, lon: float, poly: Any) -> bool:
    """Valida se a coordenada está dentro do polígono usando Shapely."""
    if not poly or Point is None:
        return True
    try:
        return bool(poly.contains(Point(lon, lat)))
    except Exception:  # pragma: no cover - errors ignorados
        return True


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
    """Verifica se a coordenada esta dentro dos limites da ``bbox``.

    Parameters
    ----------
    lat, lon:
        Coordenadas a validar.
    bbox:
        Limites da cidade (sul, norte, oeste, leste).

    Returns
    -------
    bool
        ``True`` se a coordenada estiver dentro da ``bbox``.
    """

    s, n, w, e = bbox
    return s <= lat <= n and w <= lon <= e


def geocode_strict_single(address: str, city: str) -> Optional[Tuple[float, float]]:
    """Geocoding restrito à cidade usando viewbox."""
    key = f"strict|{address}|{city}"
    if key in _cache_geo:
        return _cache_geo[key]
    bbox = get_city_bbox(city)
    poly = get_city_polygon(city)
    params = {"street": address, "city": city, "state": "Minas Gerais", "country": "Brazil"}
    try:
        if bbox:
            sb, nb, wb, eb = bbox
            viewbox = [(sb, wb), (nb, eb)]
            loc = geocode_rl(params, exactly_one=True, viewbox=viewbox, bounded=True)
        else:
            loc = geocode_rl(params, exactly_one=True)
        if loc and (not bbox or dentro_da_cidade(loc.latitude, loc.longitude, bbox)):
            addr = loc.raw.get("address", {})
            ctag = addr.get("city") or addr.get("town") or addr.get("village")
            if ctag and ctag.lower() != city.lower():
                return None
            if not point_in_polygon(loc.latitude, loc.longitude, poly):
                return None
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
    poly = get_city_polygon(city)
    try:
        loc = geocode_rl(
            {"street": address, "city": city, "state": "Minas Gerais", "country": "Brazil"},
            exactly_one=True,
        )
        if loc and (not bbox or dentro_da_cidade(loc.latitude, loc.longitude, bbox)):
            addr = loc.raw.get("address", {})
            ctag = addr.get("city") or addr.get("town") or addr.get("village")
            if ctag and ctag.lower() != city.lower():
                return None
            if not point_in_polygon(loc.latitude, loc.longitude, poly):
                return None
            return _cache_geo.setdefault(key, (loc.latitude, loc.longitude))
    except Exception:
        pass
    try:
        loc2 = photon_geocode_rl(f"{address}, {city}, MG, Brazil", exactly_one=True)
        if loc2 and (not bbox or dentro_da_cidade(loc2.latitude, loc2.longitude, bbox)):
            addr = loc2.raw.get("address", {})
            ctag = addr.get("city") or addr.get("town") or addr.get("village")
            if ctag and ctag.lower() != city.lower():
                return None
            if not point_in_polygon(loc2.latitude, loc2.longitude, poly):
                return None
            return _cache_geo.setdefault(key, (loc2.latitude, loc2.longitude))
    except Exception:
        pass
    return None

__all__ = [
    "get_city_area_id",
    "get_city_polygon",
    "point_in_polygon",
    "get_city_bbox",
    "dentro_da_cidade",
    "geocode_strict_single",
    "geocode_fallback_single",
]
