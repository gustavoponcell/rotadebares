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


async def coletar_pois_async(cidade: str) -> List[dict]:
    """Busca bares e restaurantes via Overpass de forma assíncrona."""
    bbox = get_city_bbox(cidade)
    area_id = get_city_area_id(cidade)
    poly = get_city_polygon(cidade)
    if area_id:
        q = f"""
        [out:json][timeout:60];
        area({area_id})->.a;
        (
          node[\"amenity\"=\"bar\"](area.a);
          way[\"amenity\"=\"bar\"](area.a);
          rel[\"amenity\"=\"bar\"](area.a);
          node[\"bar\"=\"yes\"](area.a);
          node[\"craft\"=\"brewery\"](area.a);
          node[\"shop\"=\"alcohol\"](area.a);
          node[\"amenity\"=\"pub\"](area.a);
          node[\"amenity\"=\"cafe\"](area.a);
          node[\"amenity\"=\"fast_food\"](area.a);
          node[\"amenity\"=\"nightclub\"](area.a);
        );
        out center tags;
        """
    elif bbox:
        s, n, w, e = bbox
        q = f"""
        [out:json][timeout:60];
        (
          node[\"amenity\"=\"bar\"]({s},{w},{n},{e});
          node[\"bar\"=\"yes\"]({s},{w},{n},{e});
          node[\"craft\"=\"brewery\"]({s},{w},{n},{e});
          node[\"shop\"=\"alcohol\"]({s},{w},{n},{e});
          node[\"amenity\"=\"pub\"]({s},{w},{n},{e});
          node[\"amenity\"=\"cafe\"]({s},{w},{n},{e});
          node[\"amenity\"=\"fast_food\"]({s},{w},{n},{e});
          node[\"amenity\"=\"nightclub\"]({s},{w},{n},{e});
        );
        out center tags;
        """
    else:
        q = f"""
        [out:json][timeout:60];
        area[\"name\"=\"{cidade}\"][boundary=\"administrative\"][admin_level=\"8\"]->.a;
        (
          node[\"amenity\"=\"bar\"](area.a);
          way[\"amenity\"=\"bar\"](area.a);
          rel[\"amenity\"=\"bar\"](area.a);
        );
        out center tags;
        """

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

    pois = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not (name and lat and lon):
            continue
        city_tag = tags.get("addr:city")
        if city_tag and city_tag.lower() != cidade.lower():
            continue
        if poly and not point_in_polygon(float(lat), float(lon), poly):
            continue
        if bbox and not poly and not dentro_da_cidade(lat, lon, bbox):
            continue
        pois.append({"name": name, "lat": float(lat), "lon": float(lon)})
    return pois


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
