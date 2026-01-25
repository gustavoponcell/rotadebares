import logging
import math
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from data_fetch import (
    AMENITY_TAGS,
    OSM_AMENITY_TAGS,
    PTBR_TEXT_TAGS,
    PoisFetchReport,
    PoisFetchResult,
    batch_altitude,
    coletar_pois,
    osrm_table,
)
from geocoding import geocode_fallback_single, geocode_strict_single, get_city_bbox
from mapping import build_map
from optimization import apply_elevation_penalty, solve_tsp
from overture_fetch import fetch_overture_places, is_overture_enabled

log = logging.getLogger(__name__)


@dataclass
class RouteResult:
    route: List[int]
    map_html: str


def _trim_pois_by_bbox_center(
    pois: List[dict],
    bbox: Optional[Tuple[float, float, float, float]],
    limit: int,
) -> List[dict]:
    if limit <= 0 or len(pois) <= limit:
        return pois
    if not bbox:
        return pois[:limit]
    south, north, west, east = bbox
    center_lat = (south + north) / 2.0
    center_lon = (west + east) / 2.0

    def dist_sq(poi: dict) -> float:
        lat = float(poi.get("lat", 0.0))
        lon = float(poi.get("lon", 0.0))
        cos_lat = math.cos(math.radians(center_lat))
        dx = (lon - center_lon) * cos_lat
        dy = lat - center_lat
        return dx * dx + dy * dy

    return sorted(pois, key=dist_sq)[:limit]


def _trim_pois_by_reference(
    pois: List[dict],
    reference: Optional[Tuple[float, float]],
    limit: int,
) -> List[dict]:
    if limit <= 0 or len(pois) <= limit:
        return pois
    if not reference:
        return pois[:limit]
    ref_lat, ref_lon = reference
    cos_lat = math.cos(math.radians(ref_lat))

    def dist_sq(poi: dict) -> float:
        lat = float(poi.get("lat", 0.0))
        lon = float(poi.get("lon", 0.0))
        dx = (lon - ref_lon) * cos_lat
        dy = lat - ref_lat
        return dx * dx + dy * dy

    return sorted(pois, key=dist_sq)[:limit]


def approximate_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Retorna distância aproximada em km usando Haversine."""

    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


def build_poi_text_blob(poi: dict) -> str:
    parts: List[str] = []
    for key in ("name", "amenity", "category", "operator", "brand", "description", "cuisine"):
        value = poi.get(key)
        if value:
            parts.append(str(value))
    raw_tags = poi.get("raw_tags")
    if isinstance(raw_tags, dict):
        parts.extend(str(value) for value in raw_tags.values() if value)
        parts.extend(str(key) for key in raw_tags.keys() if key)
    elif raw_tags:
        parts.append(str(raw_tags))
    return " ".join(parts)


def filter_pois_by_text(pois: Iterable[dict], text_tags: Iterable[str]) -> List[dict]:
    text_tags = [tag.lower() for tag in text_tags if tag]
    if not text_tags:
        return list(pois)
    filtered: List[dict] = []
    for poi in pois:
        blob = build_poi_text_blob(poi).lower()
        if any(tag in blob for tag in text_tags):
            filtered.append(poi)
    return filtered


def fetch_osm_pois(city: str, selected_osm_amenities: Optional[List[str]]) -> PoisFetchResult:
    selected_osm_amenities = selected_osm_amenities or OSM_AMENITY_TAGS
    return coletar_pois(city, selected_amenities=selected_osm_amenities)


def trim_pois_for_osrm(
    pois: List[dict],
    start_coords: Optional[Tuple[float, float]],
    bbox: Optional[Tuple[float, float, float, float]],
    limit: int,
) -> Tuple[List[dict], int]:
    if limit <= 0 or len(pois) <= limit:
        return pois, 0
    if start_coords:
        trimmed = _trim_pois_by_reference(pois, start_coords, limit)
    else:
        trimmed = _trim_pois_by_bbox_center(pois, bbox, limit)
    return trimmed, max(0, len(pois) - len(trimmed))


def fetch_places(
    city: str,
    bbox: Optional[Tuple[float, float, float, float]],
    selected_tags: List[str],
    include_overture: bool,
    overture_limit: int = 300,
    combined_limit: int = 300,
) -> PoisFetchResult:
    city = city.strip()
    if not city or not selected_tags:
        report = PoisFetchReport(tiles_total=0, tiles_failed=0)
        return PoisFetchResult(pois=[], report=report)

    selected_osm = [tag for tag in selected_tags if tag in OSM_AMENITY_TAGS]
    selected_text = [tag for tag in selected_tags if tag in PTBR_TEXT_TAGS]
    text_only_filter = False
    if not selected_osm and selected_text:
        selected_osm = list(OSM_AMENITY_TAGS)
        text_only_filter = True

    osm_result = fetch_osm_pois(city, selected_osm)
    report = osm_result.report
    report.osm_total = len(osm_result.pois)
    log.info("OSM total=%s", report.osm_total)

    overture_enabled = bool(include_overture or is_overture_enabled())
    overture_pois: List[dict] = []
    if overture_enabled:
        if bbox:
            try:
                overture_pois = fetch_overture_places(
                    (bbox[2], bbox[0], bbox[3], bbox[1]),
                    limit=overture_limit,
                )
            except Exception as exc:
                report.overture_error = str(exc)
                log.warning("Falha ao buscar Overture Places: %s", exc)
        else:
            report.overture_error = "bbox não encontrada"

    report.overture_enabled = overture_enabled and report.overture_error is None
    report.overture_total = len(overture_pois)

    combined = list(osm_result.pois) + list(overture_pois)
    if selected_text:
        selected_text_lower = [tag.lower() for tag in selected_text if tag]
        if selected_osm and not text_only_filter:
            selected_osm_lower = {tag.lower() for tag in selected_osm if tag}
            combined = [
                poi
                for poi in combined
                if (poi.get("amenity") or poi.get("category") or "").lower() in selected_osm_lower
                or any(tag in build_poi_text_blob(poi).lower() for tag in selected_text_lower)
            ]
        else:
            combined = filter_pois_by_text(combined, selected_text_lower)
        report.text_filtered_total = len(combined)
        log.info("Filtro texto aplicado: %s", report.text_filtered_total)

    report.combined_total = len(combined)

    trimmed = _trim_pois_by_bbox_center(combined, bbox, combined_limit)
    report.trimmed_total = max(0, report.combined_total - len(trimmed))
    report.limit_total = len(trimmed)
    log.info("Combined=%s trimmed=%s", report.combined_total, report.limit_total)

    if len(trimmed) <= 1:
        report.sample_pois = report.sample_pois or [
            {
                "poi_id": poi.get("poi_id"),
                "name": poi.get("name"),
                "source": poi.get("source"),
                "amenity": poi.get("amenity") or poi.get("category"),
                "lat": poi.get("lat"),
                "lon": poi.get("lon"),
                "raw_tags": poi.get("raw_tags"),
            }
            for poi in trimmed[:5]
        ]
        log.warning("Poucos POIs após merge/filtros (%s). Amostra: %s", len(trimmed), report.sample_pois)

    return PoisFetchResult(pois=trimmed, report=report)


def load_pois(
    city: str,
    include_overture: Optional[bool] = None,
    overture_limit: int = 300,
    combined_limit: int = 300,
) -> PoisFetchResult:
    """Carrega POIs para um município usando o Overpass e, opcionalmente, Overture."""

    city = city.strip()
    if not city:
        return PoisFetchResult(pois=[], report=PoisFetchReport(tiles_total=0, tiles_failed=0))
    selected_tags = list(AMENITY_TAGS)
    bbox = get_city_bbox(city)
    include_overture = is_overture_enabled() if include_overture is None else include_overture
    result = fetch_places(
        city=city,
        bbox=bbox,
        selected_tags=selected_tags,
        include_overture=include_overture,
        overture_limit=overture_limit,
        combined_limit=combined_limit,
    )
    report = result.report
    log.info(
        "load_pois: bbox=%s osm=%s combined=%s text=%s trimmed=%s",
        bbox,
        report.osm_total,
        report.combined_total,
        report.text_filtered_total,
        report.limit_total or len(result.pois),
    )
    if len(result.pois) <= 1:
        report.sample_pois = report.sample_pois or [
            {
                "poi_id": poi.get("poi_id"),
                "name": poi.get("name"),
                "source": poi.get("source"),
                "amenity": poi.get("amenity") or poi.get("category"),
                "lat": poi.get("lat"),
                "lon": poi.get("lon"),
                "raw_tags": poi.get("raw_tags"),
            }
            for poi in result.pois[:5]
        ]
        log.warning("load_pois retornou poucos POIs (%s). Amostra: %s", len(result.pois), report.sample_pois)
    return result


def compute_route_and_map(
    city: str,
    start: str,
    end: Optional[str],
    selected_pois: List[dict],
    extras: List[str],
    elev_weight: float,
    output_path: Optional[str] = None,
) -> RouteResult:
    """Executa o pipeline completo e retorna o HTML do mapa.

    Parameters
    ----------
    city:
        Nome do município.
    start:
        Endereço de partida.
    end:
        Endereço de destino. Se vazio, usa a partida.
    selected_pois:
        Lista de POIs já escolhidos pelo usuário.
    extras:
        Endereços extras (um por linha) a serem geocodificados.
    elev_weight:
        Peso da penalização de subida.
    output_path:
        Caminho opcional para salvar o HTML.
    """

    city = city.strip()
    start = start.strip()
    end = end.strip() if end else start

    if not city:
        raise ValueError("Informe um município válido.")
    if not start:
        raise ValueError("Informe a partida.")

    log.info("Geocodificando partida/destino...")
    pt0 = geocode_strict_single(start, city) or geocode_fallback_single(start, city)
    if not pt0:
        raise ValueError(f"Falha ao geocodificar partida: {start}")

    pt1 = geocode_strict_single(end, city) or geocode_fallback_single(end, city)
    if not pt1:
        raise ValueError(f"Falha ao geocodificar destino: {end}")

    coords: List[Tuple[float, float]] = [(pt0[0], pt0[1])]
    names = ["Partida"]
    for poi in selected_pois:
        try:
            coords.append((float(poi["lat"]), float(poi["lon"])))
            names.append(poi["name"])
        except (KeyError, TypeError, ValueError):
            log.warning("POI inválido ignorado: %s", poi)

    for extra in extras:
        geo = geocode_strict_single(extra, city) or geocode_fallback_single(extra, city)
        if geo:
            coords.append((geo[0], geo[1]))
            names.append(extra)
        else:
            log.warning("Extra não geocodificado: %s", extra)

    coords.append((pt1[0], pt1[1]))
    names.append("Destino")

    if len(coords) < 3:
        raise ValueError("Selecione ao menos um POI ou extra.")

    log.info("Obtendo altitudes...")
    alts = batch_altitude(coords)
    coords_alt = [(lat, lon, alt) for (lat, lon), alt in zip(coords, alts)]

    log.info("Calculando matriz de distâncias...")
    dist = osrm_table([(lat, lon) for lat, lon, _ in coords_alt])
    if dist is None:
        raise ValueError("Falha ao obter matriz OSRM. Tente novamente.")

    penal = apply_elevation_penalty(dist, coords_alt, float(elev_weight))
    end_idx = len(coords_alt) - 1

    log.info("Resolvendo TSP...")
    route = solve_tsp(penal, 0, end_idx)
    if not route:
        raise ValueError("TSP falhou.")
    if route[0] != 0 or route[-1] != end_idx or len(route) != len(set(route)):
        raise ValueError("Rota inválida: verifique origem/destino ou matriz.")

    log.info("Gerando mapa...")
    m = build_map(route, coords_alt, names)
    if output_path:
        m.save(output_path)
    html = m.get_root().render()
    return RouteResult(route=route, map_html=html)


__all__ = [
    "RouteResult",
    "PoisFetchResult",
    "approximate_distance_km",
    "build_poi_text_blob",
    "fetch_osm_pois",
    "fetch_places",
    "filter_pois_by_text",
    "load_pois",
    "trim_pois_for_osrm",
    "compute_route_and_map",
]
