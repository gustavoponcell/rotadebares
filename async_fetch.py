import asyncio
import logging
from typing import List, Tuple

import aiohttp

from geocoding import (
    get_city_bbox,
    dentro_da_cidade,
    get_city_area_id,
    get_city_polygon,
    point_in_polygon,
)

log = logging.getLogger(__name__)

AMENITY_TAGS = [
    "bar",
    "pub",
    "biergarten",
    "nightclub",
    "cafe",
    "restaurant",
    "fast_food",
]

_session: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession:
    """Retorna uma sessão ``aiohttp`` reutilizável."""
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session


async def close_session() -> None:
    """Encerra a sessão HTTP assíncrona."""
    global _session
    if _session and not _session.closed:
        await _session.close()
    _session = None


def _build_overpass_query(cidade: str, area_id: int | None, bbox: Tuple[float, float, float, float] | None) -> str:
    amenity_filter = "|".join(AMENITY_TAGS)
    if area_id:
        return f"""
        [out:json][timeout:60];
        area({area_id})->.a;
        (
          node[\"amenity\"~\"^({amenity_filter})$\"](area.a);
          way[\"amenity\"~\"^({amenity_filter})$\"](area.a);
          relation[\"amenity\"~\"^({amenity_filter})$\"](area.a);
        );
        out center tags;
        """
    if bbox:
        s, n, w, e = bbox
        return f"""
        [out:json][timeout:60];
        (
          node[\"amenity\"~\"^({amenity_filter})$\"]({s},{w},{n},{e});
          way[\"amenity\"~\"^({amenity_filter})$\"]({s},{w},{n},{e});
          relation[\"amenity\"~\"^({amenity_filter})$\"]({s},{w},{n},{e});
        );
        out center tags;
        """
    return f"""
    [out:json][timeout:60];
    area[\"name\"=\"{cidade}\"][boundary=\"administrative\"][admin_level=\"8\"]->.a;
    (
      node[\"amenity\"~\"^({amenity_filter})$\"](area.a);
      way[\"amenity\"~\"^({amenity_filter})$\"](area.a);
      relation[\"amenity\"~\"^({amenity_filter})$\"](area.a);
    );
    out center tags;
    """


def _normalize_poi(el: dict) -> dict | None:
    osm_type = el.get("type")
    osm_id = el.get("id")
    if not osm_type or osm_id is None:
        return None
    if osm_type == "node":
        lat = el.get("lat")
        lon = el.get("lon")
    else:
        center = el.get("center", {})
        lat = center.get("lat")
        lon = center.get("lon")
    if lat is None or lon is None:
        return None
    tags = el.get("tags", {})
    poi = {
        "poi_id": f"osm:{osm_type}:{osm_id}",
        "osm_type": osm_type,
        "osm_id": osm_id,
        "name": tags.get("name"),
        "amenity": tags.get("amenity"),
        "lat": float(lat),
        "lon": float(lon),
    }
    extra_tags = {
        key: value
        for key, value in tags.items()
        if key.startswith("addr:") or key in {"opening_hours", "cuisine"}
    }
    poi.update(extra_tags)
    return poi


async def coletar_pois_async(cidade: str) -> List[dict]:
    """Busca bares e restaurantes via Overpass de forma assíncrona."""
    bbox = get_city_bbox(cidade)
    area_id = get_city_area_id(cidade)
    poly = get_city_polygon(cidade)
    q = _build_overpass_query(cidade, area_id, bbox)

    session = get_session()
    try:
        async with session.post(
            "http://overpass-api.de/api/interpreter", data={"data": q}, timeout=60
        ) as resp:
            resp.raise_for_status()
            elements = (await resp.json()).get("elements", [])
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.error(f"Erro Overpass: {e}")
        return []
    except Exception as e:
        log.error(f"Erro ao decodificar resposta Overpass: {e}")
        return []

    pois_by_id = {}
    for el in elements:
        poi = _normalize_poi(el)
        if not poi:
            continue
        tags = el.get("tags", {})
        city_tag = tags.get("addr:city")
        if city_tag and city_tag.lower() != cidade.lower():
            continue
        if poly and not point_in_polygon(poi["lat"], poi["lon"], poly):
            continue
        if bbox and not poly and not dentro_da_cidade(poi["lat"], poi["lon"], bbox):
            continue
        poi_id = poi["poi_id"]
        if poi_id not in pois_by_id:
            pois_by_id[poi_id] = poi
    return list(pois_by_id.values())


async def batch_altitude_async(latlons: List[Tuple[float, float]]) -> List[float]:
    """Obtém altitudes via Open-Elevation de forma assíncrona."""
    locs = [{"latitude": lat, "longitude": lon} for lat, lon in latlons]
    session = get_session()
    try:
        async with session.post(
            "https://api.open-elevation.com/api/v1/lookup",
            json={"locations": locs},
            timeout=30,
        ) as resp:
            resp.raise_for_status()
            data = (await resp.json()).get("results", [])
            return [r.get("elevation", 0) for r in data]
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.error(f"Erro Open-Elevation: {e}")
    except Exception as e:
        log.error(f"Erro ao processar resposta Open-Elevation: {e}")
    return [0] * len(locs)


async def osrm_table_async(
    latlons: List[Tuple[float, float]], timeout: int = 30
) -> List[List[float]]:
    """Retorna matriz de distâncias usando OSRM de forma assíncrona."""
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in latlons)
    url = f"http://router.project-osrm.org/table/v1/foot/{coord_str}"
    params = {"annotations": "distance"}
    session = get_session()
    try:
        async with session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            return (await resp.json()).get("distances", [])
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning(f"OSRM Table falhou, tentando linha a linha: {e}")

        async def fetch_row(i: int) -> Tuple[int, List[float] | None]:
            try:
                async with session.get(
                    url,
                    params={"annotations": "distance", "sources": i},
                    timeout=timeout,
                ) as r:
                    r.raise_for_status()
                    row = (await r.json()).get("distances", [[0] * len(latlons)])[0]
                    return i, row
            except Exception as exc:
                log.error(f"OSRM Table linha {i} falhou: {exc}")
                return i, None

        tasks = [fetch_row(i) for i in range(len(latlons))]
        results = [None] * len(latlons)
        for idx, row in await asyncio.gather(*tasks):
            if row is None:
                return [[0] * len(latlons) for _ in latlons]
            results[idx] = row
        return results
    except Exception as e:
        log.error(f"Erro ao processar resposta OSRM: {e}")
        return [[0] * len(latlons) for _ in latlons]


async def fetch_route_geometry_async(
    a: Tuple[float, float], b: Tuple[float, float]
) -> List[Tuple[float, float]]:
    """Busca linha de caminho entre dois pontos via OSRM de forma assíncrona."""
    url = f"http://router.project-osrm.org/route/v1/foot/{a[1]},{a[0]};{b[1]},{b[0]}"
    session = get_session()
    try:
        async with session.get(
            url, params={"overview": "full", "geometries": "geojson"}, timeout=30
        ) as resp:
            resp.raise_for_status()
            coords = (await resp.json())["routes"][0]["geometry"]["coordinates"]
            return [(lat, lng) for lng, lat in coords]
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.error(f"Erro OSRM Route: {e}")
    except Exception as e:
        log.error(f"Erro ao processar resposta OSRM Route: {e}")
    return []


async def fetch_route_geometry_multi_async(
    points: List[Tuple[float, float]]
) -> List[Tuple[float, float]]:
    """Obtém a geometria de uma rota que passa por ``points`` de forma assíncrona."""
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in points)
    url = f"http://router.project-osrm.org/route/v1/foot/{coord_str}"
    session = get_session()
    try:
        async with session.get(
            url, params={"overview": "full", "geometries": "geojson"}, timeout=30
        ) as resp:
            resp.raise_for_status()
            coords = (await resp.json())["routes"][0]["geometry"]["coordinates"]
            return [(lat, lng) for lng, lat in coords]
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.error(f"Erro OSRM Route múltiplo: {e}")
    except Exception as e:
        log.error(f"Erro ao processar resposta OSRM Route múltiplo: {e}")
    return []


__all__ = [
    "coletar_pois_async",
    "batch_altitude_async",
    "osrm_table_async",
    "fetch_route_geometry_async",
    "fetch_route_geometry_multi_async",
    "close_session",
    "get_session",
]
