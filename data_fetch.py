import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

# Sessao HTTP com retries
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[502,504,522,524], allowed_methods=["GET","POST"])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)


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


def coletar_pois(cidade: str) -> List[dict]:
    """Busca bares e restaurantes via Overpass."""
    bbox = get_city_bbox(cidade)
    area_id = get_city_area_id(cidade)
    poly = get_city_polygon(cidade)
    q = _build_overpass_query(cidade, area_id, bbox)
    try:
        resp = session.post("http://overpass-api.de/api/interpreter", data={"data": q}, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Erro Overpass: {e}")
        return []

    try:
        elements = resp.json().get("elements", [])
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


def batch_altitude(latlons: List[Tuple[float, float]]) -> List[float]:
    """Obtém altitudes via Open-Elevation."""
    locs = [{"latitude": lat, "longitude": lon} for lat, lon in latlons]
    try:
        resp = session.post("https://api.open-elevation.com/api/v1/lookup", json={"locations": locs}, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("results", [])
        return [r.get("elevation", 0) for r in data]
    except requests.RequestException as e:
        log.error(f"Erro Open-Elevation: {e}")
    except Exception as e:
        log.error(f"Erro ao processar resposta Open-Elevation: {e}")
    return [0] * len(locs)


def osrm_table(latlons: List[Tuple[float, float]], timeout: int = 30) -> List[List[float]] | None:
    """Retorna matriz de distâncias usando OSRM."""
    if not latlons:
        log.error("OSRM Table chamado com lista vazia.")
        return None
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in latlons)
    url = f"http://router.project-osrm.org/table/v1/foot/{coord_str}"
    params = {"annotations": "distance"}
    try:
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("distances", [])
    except requests.RequestException as e:
        log.warning(f"OSRM Table falhou, tentando linha a linha: {e}")

        def fetch_row(i: int):
            try:
                r = session.get(url, params={"annotations": "distance", "sources": i}, timeout=timeout)
                r.raise_for_status()
                return i, r.json().get("distances", [[0] * len(latlons)])[0]
            except Exception as exc:
                log.error(f"OSRM Table linha {i} falhou: {exc}")
                return i, None

        results = [None] * len(latlons)
        with ThreadPoolExecutor(max_workers=min(4, len(latlons))) as ex:
            futures = [ex.submit(fetch_row, i) for i in range(len(latlons))]
            for fut in as_completed(futures):
                idx, row = fut.result()
                if row is None:
                    log.error("Falha ao recuperar tabela OSRM linha a linha.")
                    return None
                results[idx] = row
        return results
    except Exception as e:
        log.error(f"Erro ao processar resposta OSRM: {e}")
        return None

__all__ = ["coletar_pois", "batch_altitude", "osrm_table", "session"]
