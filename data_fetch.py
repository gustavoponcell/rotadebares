import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Tuple

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

OSM_AMENITY_TAGS = [
    "bar",
    "pub",
    "biergarten",
    "nightclub",
    "cafe",
    "restaurant",
    "fast_food",
]

PTBR_TEXT_TAGS = [
    "república",
    "lanchonete",
    "cervejaria",
    "boate",
    "choperia",
    "boteco",
    "petiscaria",
]

AMENITY_TAGS = [
    "bar",
    "pub",
    "biergarten",
    "nightclub",
    "cafe",
    "restaurant",
    "fast_food",
    "república",
    "lanchonete",
    "cervejaria",
    "boate",
    "choperia",
    "boteco",
    "petiscaria",
]

# Sessao HTTP com retries
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 504, 522, 524], allowed_methods=["GET", "POST"])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

OVERPASS_TIMEOUT = 60


@dataclass
class PoisFetchReport:
    tiles_total: int
    tiles_failed: int
    osm_total: int = 0
    overture_total: int = 0
    combined_total: int = 0
    trimmed_total: int = 0
    overture_enabled: bool = False
    overture_error: str | None = None


@dataclass
class PoisFetchResult:
    pois: List[dict]
    report: PoisFetchReport


def tile_bbox(
    bbox: Tuple[float, float, float, float],
    max_tiles_total: int = 16,
    overlap_m: int = 200,
) -> List[Tuple[float, float, float, float]]:
    """Divide uma bbox em tiles com overlap.

    Parameters
    ----------
    bbox:
        (min_lon, min_lat, max_lon, max_lat).
    max_tiles_total:
        Limite máximo de tiles (1, 4, 9, 16).
    overlap_m:
        Overlap em metros aplicado a cada tile.
    """

    min_lon, min_lat, max_lon, max_lat = bbox
    lat_span = max_lat - min_lat
    lon_span = max_lon - min_lon
    if lat_span <= 0 or lon_span <= 0:
        return [bbox]

    mid_lat = (min_lat + max_lat) / 2.0
    cos_lat = max(math.cos(math.radians(mid_lat)), 1e-6)
    lat_span_km = lat_span * 111.0
    lon_span_km = lon_span * 111.0 * cos_lat
    max_span_km = max(lat_span_km, lon_span_km)

    if max_span_km <= 5:
        grid = 1
    elif max_span_km <= 15:
        grid = 2
    elif max_span_km <= 30:
        grid = 3
    else:
        grid = 4

    while grid * grid > max_tiles_total and grid > 1:
        grid -= 1

    overlap_deg_lat = overlap_m / 111_000
    overlap_deg_lon = overlap_m / (111_000 * cos_lat)
    lat_step = lat_span / grid
    lon_step = lon_span / grid

    tiles: List[Tuple[float, float, float, float]] = []
    for i in range(grid):
        tile_min_lat = min_lat + i * lat_step - overlap_deg_lat
        tile_max_lat = min_lat + (i + 1) * lat_step + overlap_deg_lat
        for j in range(grid):
            tile_min_lon = min_lon + j * lon_step - overlap_deg_lon
            tile_max_lon = min_lon + (j + 1) * lon_step + overlap_deg_lon
            tiles.append((tile_min_lon, tile_min_lat, tile_max_lon, tile_max_lat))
    return tiles


def _build_overpass_query(
    cidade: str,
    area_id: int | None,
    bbox: Tuple[float, float, float, float] | None,
    amenities: List[str] | None,
    timeout: int = OVERPASS_TIMEOUT,
) -> str:
    amenities = amenities or OSM_AMENITY_TAGS
    amenity_filter = "|".join(amenities)
    if area_id:
        return f"""
        [out:json][timeout:{timeout}];
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
        [out:json][timeout:{timeout}];
        (
          node[\"amenity\"~\"^({amenity_filter})$\"]({s},{w},{n},{e});
          way[\"amenity\"~\"^({amenity_filter})$\"]({s},{w},{n},{e});
          relation[\"amenity\"~\"^({amenity_filter})$\"]({s},{w},{n},{e});
        );
        out center tags;
        """
    return f"""
    [out:json][timeout:{timeout}];
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
    name = tags.get("name")
    if not name or not name.strip():
        return None
    poi = {
        "poi_id": f"osm:{osm_type}:{osm_id}",
        "osm_type": osm_type,
        "osm_id": osm_id,
        "name": name,
        "amenity": tags.get("amenity"),
        "category": tags.get("amenity"),
        "lat": float(lat),
        "lon": float(lon),
        "source": "osm",
        "raw_tags": tags,
    }
    extra_tags = {
        key: value
        for key, value in tags.items()
        if key.startswith("addr:") or key in {"opening_hours", "cuisine"}
    }
    poi.update(extra_tags)
    return poi


def _fetch_overpass_elements(
    query: str,
    max_retries: int,
    backoff_factor: float,
    timeout: int,
) -> List[dict] | None:
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post("http://overpass-api.de/api/interpreter", data={"data": query}, timeout=timeout)
            status = resp.status_code
            if status == 429 or status >= 500:
                raise requests.HTTPError(f"Overpass status {status}", response=resp)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except (requests.RequestException, ValueError) as exc:
            if attempt == max_retries:
                log.warning("Overpass falhou após %s tentativas: %s", max_retries, exc)
                break
            sleep_s = backoff_factor * (2 ** (attempt - 1))
            log.warning("Overpass falhou (tentativa %s/%s). Retentando em %.1fs...", attempt, max_retries, sleep_s)
            time.sleep(sleep_s)
    return None


def coletar_pois(
    cidade: str,
    selected_amenities: List[str] | None = None,
    max_tiles_total: int = 16,
    overlap_m: int = 200,
    max_workers: int = 4,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    overpass_timeout: int = OVERPASS_TIMEOUT,
) -> PoisFetchResult:
    """Busca bares e restaurantes via Overpass."""
    bbox = get_city_bbox(cidade)
    area_id = get_city_area_id(cidade)
    poly = get_city_polygon(cidade)
    use_bbox_tiles = bbox is not None
    if use_bbox_tiles:
        bbox_tiles = tile_bbox((bbox[2], bbox[0], bbox[3], bbox[1]), max_tiles_total, overlap_m)
    else:
        bbox_tiles = [None]

    def fetch_tile(
        tile: Tuple[float, float, float, float] | None,
    ) -> Tuple[Tuple[float, float, float, float] | None, List[dict] | None]:
        if tile:
            tile_bbox_overpass = (tile[1], tile[3], tile[0], tile[2])
            query = _build_overpass_query(
                cidade,
                None,
                tile_bbox_overpass,
                selected_amenities,
                timeout=overpass_timeout,
            )
        else:
            query = _build_overpass_query(
                cidade,
                area_id,
                None,
                selected_amenities,
                timeout=overpass_timeout,
            )
        elements = _fetch_overpass_elements(query, max_retries, backoff_factor, overpass_timeout)
        return tile, elements

    tiles_failed = 0
    pois_by_id: Dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(bbox_tiles))) as executor:
        futures = [executor.submit(fetch_tile, tile) for tile in bbox_tiles]
        for fut in as_completed(futures):
            tile, elements = fut.result()
            if elements is None:
                tiles_failed += 1
                log.warning("Tile Overpass falhou: %s", tile)
                continue
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
                poi_id = poi["poi_id"]
                if poi_id not in pois_by_id:
                    pois_by_id[poi_id] = poi

    pois = list(pois_by_id.values())
    if bbox:
        pois = [poi for poi in pois if dentro_da_cidade(poi["lat"], poi["lon"], bbox)]

    report = PoisFetchReport(tiles_total=len(bbox_tiles), tiles_failed=tiles_failed)
    if tiles_failed:
        log.warning("Overpass retornou dados parciais: %s tiles falharam.", tiles_failed)
    return PoisFetchResult(pois=pois, report=report)


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

__all__ = [
    "AMENITY_TAGS",
    "OSM_AMENITY_TAGS",
    "PTBR_TEXT_TAGS",
    "PoisFetchReport",
    "PoisFetchResult",
    "tile_bbox",
    "coletar_pois",
    "batch_altitude",
    "osrm_table",
    "session",
]
