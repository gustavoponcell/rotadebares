import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .geocoding import get_city_bbox, dentro_da_cidade

# Sessão HTTP com retries
session = requests.Session()
retries = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[502, 504, 522, 524],
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)


def coletar_pois(cidade):
    """Consulta Overpass para coletar bares e afins."""
    bbox = get_city_bbox(cidade)
    if bbox:
        s, n, w, e = bbox
        q = f"""
        [out:json][timeout:60];
        (
          node["amenity"="bar"]({s},{w},{n},{e});
          node["bar"="yes"]({s},{w},{n},{e});
          node["craft"="brewery"]({s},{w},{n},{e});
          node["shop"="alcohol"]({s},{w},{n},{e});
          node["amenity"="pub"]({s},{w},{n},{e});
          node["amenity"="cafe"]({s},{w},{n},{e});
          node["amenity"="fast_food"]({s},{w},{n},{e});
          node["amenity"="nightclub"]({s},{w},{n},{e});
        );
        out center tags;
        """
    else:
        q = f"""
        [out:json][timeout:60];
        area["name"="{cidade}"][boundary="administrative"][admin_level="8"]->.a;
        (
          node["amenity"="bar"](area.a);
          way["amenity"="bar"](area.a);
          rel["amenity"="bar"](area.a);
        );
        out center tags;
        """
    resp = session.post(
        "http://overpass-api.de/api/interpreter",
        data={"data": q},
        timeout=60,
    )
    pois = []
    if resp.status_code == 200:
        for el in resp.json().get("elements", []):
            name = el.get("tags", {}).get("name")
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            if not (name and lat and lon):
                continue
            if bbox and not dentro_da_cidade(lat, lon, bbox):
                continue
            pois.append({"name": name, "lat": float(lat), "lon": float(lon)})
    return pois


def batch_altitude(latlons):
    """Obtém altitudes via Open-Elevation."""
    locs = [{"latitude": lat, "longitude": lon} for lat, lon in latlons]
    resp = session.post(
        "https://api.open-elevation.com/api/v1/lookup",
        json={"locations": locs},
        timeout=30,
    )
    if resp.status_code != 200:
        return [0] * len(locs)
    return [r.get("elevation", 0) for r in resp.json().get("results", [])]


def osrm_table(latlons, timeout=30):
    """Calcula matriz de distâncias via OSRM."""
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in latlons)
    url = f"http://router.project-osrm.org/table/v1/foot/{coord_str}"
    params = {"annotations": "distance"}
    try:
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("distances", [])
    except (requests.exceptions.ReadTimeout, requests.exceptions.HTTPError):
        full = []
        for i in range(len(latlons)):
            r = session.get(
                url,
                params={"annotations": "distance", "sources": i},
                timeout=timeout,
            )
            r.raise_for_status()
            full.append(r.json().get("distances", [[0] * len(latlons)])[0])
        return full
