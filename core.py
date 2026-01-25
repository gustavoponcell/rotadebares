import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from data_fetch import PoisFetchReport, PoisFetchResult, batch_altitude, coletar_pois, osrm_table
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

    osm_result = coletar_pois(city)
    report = osm_result.report
    report.osm_total = len(osm_result.pois)

    overture_enabled = is_overture_enabled() if include_overture is None else include_overture
    overture_pois: List[dict] = []
    if overture_enabled and is_overture_enabled():
        bbox = get_city_bbox(city)
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

    combined = list(osm_result.pois) + list(overture_pois)
    report.overture_enabled = bool(overture_enabled and is_overture_enabled())
    report.overture_total = len(overture_pois)
    report.combined_total = len(combined)

    trimmed = _trim_pois_by_bbox_center(combined, get_city_bbox(city), combined_limit)
    report.trimmed_total = max(0, report.combined_total - len(trimmed))

    return PoisFetchResult(pois=trimmed, report=report)


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


__all__ = ["RouteResult", "PoisFetchResult", "load_pois", "compute_route_and_map"]
