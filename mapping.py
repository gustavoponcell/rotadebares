import logging
from typing import List, Tuple

import folium
import requests

from data_fetch import session

log = logging.getLogger(__name__)


def fetch_route_geometry(a: Tuple[float, float], b: Tuple[float, float]) -> List[Tuple[float, float]]:
    """Busca linha de caminho entre dois pontos via OSRM."""
    url = f"http://router.project-osrm.org/route/v1/foot/{a[1]},{a[0]};{b[1]},{b[0]}"
    try:
        resp = session.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=30)
        resp.raise_for_status()
        coords = resp.json()["routes"][0]["geometry"]["coordinates"]
        return [(lat, lng) for lng, lat in coords]
    except requests.RequestException as e:
        log.error(f"Erro OSRM Route: {e}")
    except Exception as e:
        log.error(f"Erro ao processar resposta OSRM Route: {e}")
    return []


def fetch_route_geometry_multi(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Obtém a geometria de uma rota que passa por ``points``.

    Parameters
    ----------
    points:
        Lista ordenada de pares ``(lat, lon)`` que compõem a rota.

    Returns
    -------
    List[Tuple[float, float]]
        Coordenadas da linha da rota no formato ``(lat, lon)``.
    """

    coord_str = ";".join(f"{lon},{lat}" for lat, lon in points)
    url = f"http://router.project-osrm.org/route/v1/foot/{coord_str}"
    try:
        resp = session.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=30)
        resp.raise_for_status()
        coords = resp.json()["routes"][0]["geometry"]["coordinates"]
        return [(lat, lng) for lng, lat in coords]
    except requests.RequestException as e:
        log.error(f"Erro OSRM Route múltiplo: {e}")
    except Exception as e:
        log.error(f"Erro ao processar resposta OSRM Route múltiplo: {e}")
    return []


def build_map(route_idx: List[int], coords: List[Tuple[float, float, float]], names: List[str]) -> folium.Map:
    """Monta o mapa interativo da rota.

    Parameters
    ----------
    route_idx:
        Sequência de índices que define a ordem de visita.
    coords:
        Lista de tuplas ``(lat, lon, alt)`` correspondentes a cada ponto.
    names:
        Nomes dos locais exibidos no mapa.

    Returns
    -------
    folium.Map
        Mapa com marcadores e a linha da rota.
    """

    m = folium.Map(location=coords[0][:2], zoom_start=14)
    folium.Marker(coords[0][:2], tooltip="Partida", icon=folium.Icon(color="green", icon="play")).add_to(m)
    for seq, idx in enumerate(route_idx[1:-1], start=1):
        folium.Marker(
            coords[idx][:2],
            tooltip=f"{seq}. {names[idx]}",
            icon=folium.DivIcon(html=f'<div style="background:#FF5722;color:#fff;border-radius:50%;padding:6px;">{seq}</div>'),
        ).add_to(m)
    folium.Marker(coords[route_idx[-1]][:2], tooltip="Destino", icon=folium.Icon(color="red", icon="flag")).add_to(m)
    ordered = [coords[i][:2] for i in route_idx]
    full_route = fetch_route_geometry_multi(ordered)
    folium.PolyLine(full_route, weight=4, opacity=0.7).add_to(m)
    return m

__all__ = ["fetch_route_geometry", "fetch_route_geometry_multi", "build_map"]
