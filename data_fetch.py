import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from geocoding import get_city_bbox, dentro_da_cidade

log = logging.getLogger(__name__)

# Sessao HTTP com retries
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[502,504,522,524], allowed_methods=["GET","POST"])
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)


def coletar_pois(cidade: str) -> List[dict]:
    """Busca bares e restaurantes via Overpass."""
    bbox = get_city_bbox(cidade)
    if bbox:
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

    pois_by_name = {}
    for el in elements:
        name = el.get("tags", {}).get("name")
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not (name and lat and lon):
            continue
        inside = not bbox or dentro_da_cidade(float(lat), float(lon), bbox)
        if not inside:
            # se existir duplicata dentro da bbox, manteremos apenas ela
            continue
        if name not in pois_by_name:
            pois_by_name[name] = {
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
            }
    return list(pois_by_name.values())


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


def osrm_table(latlons: List[Tuple[float, float]], timeout: int = 30) -> List[List[float]]:
    """Retorna matriz de distâncias usando OSRM."""
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
                    return [[0] * len(latlons) for _ in latlons]
                results[idx] = row
        return results
    except Exception as e:
        log.error(f"Erro ao processar resposta OSRM: {e}")
        return [[0] * len(latlons) for _ in latlons]

__all__ = ["coletar_pois", "batch_altitude", "osrm_table", "session"]
