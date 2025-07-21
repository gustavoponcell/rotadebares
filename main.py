# -*- coding: utf-8 -*-
"""
Roteirização interativa de bares e restaurantes (100% gratuito)
Este script combina coleta de POIs, geocoding, cálculo de altitudes,
matriz de distâncias, otimização de rota e geração de mapa HTML.
Comentários simples explicam cada bloco de forma acessível.
"""

import os  # para acessar variáveis de ambiente, se for usar outras APIs
import requests  # para chamadas HTTP (Overpass, OSRM, Open-Elevation)
from requests.adapters import HTTPAdapter  # para configurar retries automáticos
from urllib3.util.retry import Retry  # política de retry (backoff)
import folium  # para desenhar mapas interativos e marcadores
import ipywidgets as widgets  # para UI interativa no Colab
from tqdm.notebook import tqdm  # para barras de progresso
from IPython.display import display, clear_output, FileLink  # para mostrar resultados
from geopy.geocoders import Nominatim, Photon  # geocoders do OpenStreetMap
from geopy.exc import GeocoderTimedOut  # exceção de timeout no geopy
from ortools.constraint_solver import pywrapcp, routing_enums_pb2  # OR-Tools para TSP

# ---------------------
# Configura sessão HTTP com retries
# ---------------------
session = requests.Session()
# Permite até 5 tentativas em erros 502, 504, etc., com backoff exponencial
retries = Retry(
    total=5,
    backoff_factor=1,  # 1s → 2s → 4s → 8s...
    status_forcelist=[502, 504, 522, 524],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("http://", adapter)
session.mount("https://", adapter)

# ---------------------
# Inicializa geocoders e cache de resultados
# ---------------------
geolocator = Nominatim(user_agent="tsp_app", timeout=10)
photon = Photon(user_agent="tsp_app", timeout=10)
_city_geolocator = Nominatim(user_agent="tsp_app_bbox", timeout=10)
# Guarda endereços já geocodificados para não repetir chamadas
_cache_geo = {}

# -----------------------------------------------------------------------
# 1) Funções de geocoding e bounding box
# -----------------------------------------------------------------------

def get_city_bbox(city_name):
    """
    Pega a bounding box (sul, norte, oeste, leste) de uma cidade.
    Usa Nominatim para obter limites administrativos.
    Retorna tupla (south, north, west, east) ou None.
    """
    loc = _city_geolocator.geocode(
        {"city": city_name, "state": "Minas Gerais", "country": "Brazil"},
        exactly_one=True
    )
    if not loc or 'boundingbox' not in loc.raw:
        return None
    sb, nb, wb, eb = loc.raw['boundingbox']
    return float(sb), float(nb), float(wb), float(eb)


def dentro_da_cidade(lat, lon, bbox):
    """
    Verifica se uma coordenada está dentro da bounding box.
    """
    s, n, w, e = bbox
    return s <= lat <= n and w <= lon <= e


def geocode_strict_single(address, city):
    """
    Geocoding estrito usando viewbox e bounded para limitar à cidade.
    Guarda resultado em cache para evitar duplicações.
    """
    key = f"strict|{address}|{city}"
    if key in _cache_geo:
        return _cache_geo[key]
    bbox = get_city_bbox(city)
    params = {"street": address, "city": city, "state": "Minas Gerais", "country": "Brazil"}
    try:
        if bbox:
            sb, nb, wb, eb = bbox
            viewbox = [(sb, wb), (nb, eb)]
            loc = geolocator.geocode(
                params, exactly_one=True, viewbox=viewbox, bounded=True
            )
        else:
            loc = geolocator.geocode(params, exactly_one=True)
        if loc and (not bbox or dentro_da_cidade(loc.latitude, loc.longitude, bbox)):
            return _cache_geo.setdefault(key, (loc.latitude, loc.longitude))
    except GeocoderTimedOut:
        pass
    return None


def geocode_fallback_single(address, city):
    """
    Geocoding de fallback: tenta Nominatim "normal" e depois Photon.
    Também valida dentro da bounding box.
    """
    key = f"fallback|{address}|{city}"
    if key in _cache_geo:
        return _cache_geo[key]
    bbox = get_city_bbox(city)
    # 1) Nominatim sem viewbox
    try:
        loc = geolocator.geocode(
            {"street": address, "city": city, "state": "Minas Gerais", "country": "Brazil"},
            exactly_one=True
        )
        if loc and (not bbox or dentro_da_cidade(loc.latitude, loc.longitude, bbox)):
            return _cache_geo.setdefault(key, (loc.latitude, loc.longitude))
    except Exception:
        pass
    # 2) Photon
    try:
        loc2 = photon.geocode(f"{address}, {city}, MG, Brazil", exactly_one=True)
        if loc2 and (not bbox or dentro_da_cidade(loc2.latitude, loc2.longitude, bbox)):
            return _cache_geo.setdefault(key, (loc2.latitude, loc2.longitude))
    except Exception:
        pass
    return None

# -----------------------------------------------------------------------
# 2) Coletar POIs com Overpass + filtro por bounding box
# -----------------------------------------------------------------------

def coletar_pois(cidade):
    """
    Monta query Overpass para buscar bares e bebidas na city bbox.
    Filtra resultados sem nome ou fora da bounding box.
    Retorna lista de dicts com 'name', 'lat', 'lon'.
    """
    bbox = get_city_bbox(cidade)
    if bbox:
        s, n, w, e = bbox
        # Query inclui diferentes tags relacionadas a bares e pubs
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
        # fallback para area admin_level=8 se bbox não estiver disponível
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
        data={"data": q}, timeout=60
    )
    pois = []
    if resp.status_code == 200:
        for el in resp.json().get("elements", []):
            name = el.get("tags", {}).get("name")
            # extrai coordenadas, seja em node ou em center de way/rel
            lat = el.get("lat") or el.get("center", {}).get("lat")
            lon = el.get("lon") or el.get("center", {}).get("lon")
            # só mantêm se tiver nome e coordenadas dentro da cidade
            if not (name and lat and lon):
                continue
            if bbox and not dentro_da_cidade(lat, lon, bbox):
                continue
            pois.append({"name": name, "lat": float(lat), "lon": float(lon)})
    return pois

# -----------------------------------------------------------------------
# 3) Altitudes em lote com Open-Elevation
# -----------------------------------------------------------------------

def batch_altitude(latlons):
    """
    Recebe lista de (lat, lon) e retorna lista de altitudes.
    Em caso de erro, retorna zeros.
    """
    locs = [{"latitude": lat, "longitude": lon} for lat, lon in latlons]
    resp = session.post(
        "https://api.open-elevation.com/api/v1/lookup",
        json={"locations": locs}, timeout=30

    )
    if resp.status_code != 200:
        return [0] * len(locs)
    return [r.get("elevation", 0) for r in resp.json().get("results", [])]

# -----------------------------------------------------------------------
# 4) Matriz de distâncias via OSRM Table (com retries e fallback)
# -----------------------------------------------------------------------

def osrm_table(latlons, timeout=30):
    """
    Tenta obter matriz completa de distâncias.
    Se falhar (timeout ou HTTP error), faz consulta linha a linha.
    """
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in latlons)
    url = f"http://router.project-osrm.org/table/v1/foot/{coord_str}"
    params = {"annotations": "distance"}
    try:
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json().get("distances", [])
    except (requests.exceptions.ReadTimeout, requests.exceptions.HTTPError):
        # quebra em n requisições para cada fonte
        full = []
        for i in range(len(latlons)):
            r = session.get(
                url,
                params={"annotations": "distance", "sources": i},
                timeout=timeout
            )
            r.raise_for_status()
            full.append(r.json().get("distances", [[0]*len(latlons)])[0])
        return full

# -----------------------------------------------------------------------
# 5) Solução TSP com OR-Tools
# -----------------------------------------------------------------------

def solve_tsp(dist_matrix, start, end, time_limit_s=5):
    """
    Resolve o TSP fixando início e fim,
    retorna lista de índices representando a ordem.
    """
    n = len(dist_matrix)
    mgr = pywrapcp.RoutingIndexManager(n, 1, [start], [end])
    routing = pywrapcp.RoutingModel(mgr)
    # callback que retorna custo entre dois nós
    def cb(i, j):
        return int(dist_matrix[mgr.IndexToNode(i)][mgr.IndexToNode(j)])
    idx = routing.RegisterTransitCallback(cb)
    routing.SetArcCostEvaluatorOfAllVehicles(idx)
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.time_limit.seconds = time_limit_s
    sol = routing.SolveWithParameters(params)
    if not sol:
        return None
    # extrai rota do objeto solution
    route = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        route.append(mgr.IndexToNode(index))
        index = sol.Value(routing.NextVar(index))
    route.append(mgr.IndexToNode(index))
    return route

# -----------------------------------------------------------------------
# 6) Geração do mapa final com Folium
# -----------------------------------------------------------------------

def fetch_route_geometry(a, b):
    """
    Busca linha de caminho entre dois pontos via OSRM Route API.
    Retorna lista de tuplas (lat, lon).
    """
    url = f"http://router.project-osrm.org/route/v1/foot/{a[1]},{a[0]};{b[1]},{b[0]}"
    resp = session.get(
        url, params={"overview": "full", "geometries": "geojson"},
        timeout=30
    )
    resp.raise_for_status()
    coords = resp.json()["routes"][0]["geometry"]["coordinates"]
    # converte [lon, lat] para (lat, lon)
    return [(lat, lng) for lng, lat in coords]


def build_map(route_idx, coords, names):
    """
    Desenha marcadores de partida, POIs ordenados e destino,
    além de polylines para cada trecho do TSP.
    """
    # inicia mapa centrado na partida
    m = folium.Map(location=coords[0][:2], zoom_start=14)
    # marcador verde para partida
    folium.Marker(
        coords[0][:2], tooltip="Partida",
        icon=folium.Icon(color="green", icon="play")
    ).add_to(m)
    # marcadores numerados para POIs intermediários
    for seq, idx in enumerate(route_idx[1:-1], start=1):
        folium.Marker(
            coords[idx][:2], tooltip=f"{seq}. {names[idx]}",
            icon=folium.DivIcon(html=f'<div style="background:#FF5722;color:#fff;'
                                     f'border-radius:50%;padding:6px;">{seq}</div>')
        ).add_to(m)
    # marcador vermelho para destino
    folium.Marker(
        coords[route_idx[-1]][:2], tooltip="Destino",
        icon=folium.Icon(color="red", icon="flag")
    ).add_to(m)
    # desenha linhas entre cada par de pontos
    for a, b in zip(route_idx, route_idx[1:]):
        segment = fetch_route_geometry(coords[a], coords[b])
        folium.PolyLine(segment, weight=4, opacity=0.7).add_to(m)
    return m

# -----------------------------------------------------------------------
# 7) Interface interativa no Jupyter / Colab
# -----------------------------------------------------------------------

# Widgets básicos: input de cidade, partida, destino, extras, botões
city_widget    = widgets.Text(value="Diamantina", description="Município:")
load_pois_btn  = widgets.Button(description="Buscar Locais", button_style="info")
pois_box       = widgets.VBox([], layout=widgets.Layout(overflow='auto', height='300px', border='1px solid #ccc'))
custom_txt     = widgets.Textarea(placeholder="Extras (uma linha cada)", description="Extras:")
start_txt      = widgets.Text(placeholder="Ex.: Rua das Mercês, 310", description="Partida:")
end_txt        = widgets.Text(placeholder="Ex.: Rua Barão…, 208", description="Destino:")
same_cb        = widgets.Checkbox(description="Partida = Destino")
compute_btn    = widgets.Button(description="Gerar HTML", button_style="success")
out            = widgets.Output()
pois_checkboxes= []  # lista de caixas de seleção para os POIs

# Função para buscar e listar POIs na interface
def on_load_pois(_):
    with out:
        clear_output()
        print(f"🔍 Buscando POIs em {city_widget.value}…")
        pois = coletar_pois(city_widget.value.strip())
        pois_checkboxes.clear()
        items = []
        for p in pois:
            desc = f"{p['name']} ({p['lat']:.5f},{p['lon']:.5f})"
            cb = widgets.Checkbox(False, description=desc)
            pois_checkboxes.append(cb)
            items.append(cb)
        pois_box.children = items
        print(f"✅ {len(pois)} POIs carregados.")

# Sincroniza valor de destino com partida se checkbox marcado
def on_same_change(change):
    end_txt.disabled = change['new']
    if change['new']:
        end_txt.value = start_txt.value

# Função principal que roda quando clica em "Gerar HTML"
def on_compute(_):
    with out:
        clear_output()
        # leitura de inputs
        city = city_widget.value.strip()
        start = start_txt.value.strip()
        end = start if same_cb.value else end_txt.value.strip()

        print("⏳ Geocodificando partida e destino…")
        pt0 = geocode_strict_single(start, city) or geocode_fallback_single(start, city)
        if not pt0:
            print(f"❌ Falha geocode partida: {start}")
            return
        pt1 = pt0 if same_cb.value else (geocode_strict_single(end, city) or geocode_fallback_single(end, city))
        if not pt1:
            print(f"❌ Falha geocode destino: {end}")
            return

        # monta lista de coordenadas e nomes
        coords = [(pt0[0], pt0[1])]
        names = ["Partida"]
        for cb in pois_checkboxes:
            if cb.value:
                nm, coord = cb.description.split(' (')
                lat, lon = coord[:-1].split(',')
                coords.append((float(lat), float(lon)))
                names.append(nm)
        # adiciona extras digitados
        extras = [l.strip() for l in custom_txt.value.splitlines() if l.strip()]
        for ex in extras:
            geo = geocode_strict_single(ex, city) or geocode_fallback_single(ex, city)
            if geo:
                coords.append((geo[0], geo[1]))
                names.append(ex)

        coords.append((pt1[0], pt1[1]))
        names.append("Destino")

        if len(coords) < 3:
            print("❌ Selecione ao menos um POI ou extra.")
            return

        # obtém altitudes e incorpora a tupla (lat, lon, alt)
        print("⏳ Obtendo altitudes…")
        alts = batch_altitude(coords)
        coords = [(lat, lon, alt) for (lat, lon), alt in zip(coords, alts)]

        # calcula matriz de distâncias
        print("⏳ Calculando matriz…")
        dist = osrm_table([(lat, lon) for lat, lon, _ in coords])

        # define o índice final como o ponto mais próximo do destino
        end_idx = len(coords) - 1
        best = min(range(1, end_idx), key=lambda i: dist[i][end_idx])

        # resolve o TSP
        print("🚦 Resolvendo TSP…")
        route = solve_tsp(dist, 0, best)
        if not route:
            print("❌ TSP falhou")
            return
        route.append(end_idx)

        # gera e salva o mapa
        print("🗺️ Gerando mapa…")
        m = build_map(route, coords, names)
        filename = "rota_otimizada.html"
        m.save(filename)
        print(f"✅ HTML salvo: {filename}")
        display(FileLink(filename, result_html_prefix="🔗 ", result_html_suffix=" para download"))

# Conecta callbacks e exibe a interface
load_pois_btn.on_click(on_load_pois)
same_cb.observe(on_same_change, 'value')
compute_btn.on_click(on_compute)

ui = widgets.HBox([
    widgets.VBox([city_widget, load_pois_btn, widgets.Label("Selecione POIs:"), pois_box]),
    widgets.VBox([start_txt, end_txt, same_cb, custom_txt, compute_btn])
])
display(ui, out)
