import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from data_fetch import PoisFetchReport, PoisFetchResult, batch_altitude, coletar_pois, osrm_table
from geocoding import geocode_fallback_single, geocode_strict_single
from mapping import build_map
from optimization import apply_elevation_penalty, solve_tsp

log = logging.getLogger(__name__)


@dataclass
class RouteResult:
    route: List[int]
    map_html: str


def load_pois(city: str) -> PoisFetchResult:
    """Carrega POIs para um município usando o Overpass."""

    city = city.strip()
    if not city:
        return PoisFetchResult(pois=[], report=PoisFetchReport(tiles_total=0, tiles_failed=0))
    return coletar_pois(city)


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
