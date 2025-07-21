import folium

from .data_fetch import session


def fetch_route_geometry(a, b):
    """Busca linha de caminho entre dois pontos via OSRM."""
    url = f"http://router.project-osrm.org/route/v1/foot/{a[1]},{a[0]};{b[1]},{b[0]}"
    resp = session.get(
        url,
        params={"overview": "full", "geometries": "geojson"},
        timeout=30,
    )
    resp.raise_for_status()
    coords = resp.json()["routes"][0]["geometry"]["coordinates"]
    return [(lat, lng) for lng, lat in coords]


def build_map(route_idx, coords, names):
    """Desenha mapa com marcadores e polylines."""
    m = folium.Map(location=coords[0][:2], zoom_start=14)
    folium.Marker(
        coords[0][:2], tooltip="Partida", icon=folium.Icon(color="green", icon="play")
    ).add_to(m)
    for seq, idx in enumerate(route_idx[1:-1], start=1):
        folium.Marker(
            coords[idx][:2],
            tooltip=f"{seq}. {names[idx]}",
            icon=folium.DivIcon(html=f'<div style="background:#FF5722;color:#fff;border-radius:50%;padding:6px;">{seq}</div>'),
        ).add_to(m)
    folium.Marker(
        coords[route_idx[-1]][:2],
        tooltip="Destino",
        icon=folium.Icon(color="red", icon="flag"),
    ).add_to(m)
    for a, b in zip(route_idx, route_idx[1:]):
        segment = fetch_route_geometry(coords[a], coords[b])
        folium.PolyLine(segment, weight=4, opacity=0.7).add_to(m)
    return m
