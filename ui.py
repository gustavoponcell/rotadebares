import logging

import ipywidgets as widgets
from IPython.display import display, clear_output, FileLink

from geocoding import geocode_strict_single, geocode_fallback_single
from data_fetch import coletar_pois, batch_altitude, osrm_table
from optimization import solve_tsp
from mapping import build_map

log = logging.getLogger(__name__)


class WidgetHandler(logging.Handler):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def emit(self, record):
        msg = self.format(record)
        with self.widget:
            print(msg)


city_widget = widgets.Text(value="Diamantina", description="Município:")
load_pois_btn = widgets.Button(description="Buscar Locais", button_style="info")
pois_box = widgets.VBox([], layout=widgets.Layout(overflow='auto', height='300px', border='1px solid #ccc'))
custom_txt = widgets.Textarea(placeholder="Extras (uma linha cada)", description="Extras:")
start_txt = widgets.Text(placeholder="Ex.: Rua das Mercês, 310", description="Partida:")
end_txt = widgets.Text(placeholder="Ex.: Rua Barão…, 208", description="Destino:")
same_cb = widgets.Checkbox(description="Partida = Destino")
compute_btn = widgets.Button(description="Gerar HTML", button_style="success")
out = widgets.Output()
pois_checkboxes = []

widget_handler = WidgetHandler(out)
widget_handler.setFormatter(logging.Formatter("%(message)s"))
log.addHandler(widget_handler)
log.propagate = False


def on_load_pois(_):
    with out:
        clear_output()
    log.info(f"🔍 Buscando POIs em {city_widget.value}…")
    pois = coletar_pois(city_widget.value.strip())
    pois_checkboxes.clear()
    items = []
    for p in pois:
        desc = f"{p['name']} ({p['lat']:.5f},{p['lon']:.5f})"
        cb = widgets.Checkbox(False, description=desc)
        pois_checkboxes.append(cb)
        items.append(cb)
    pois_box.children = items
    log.info(f"✅ {len(pois)} POIs carregados.")


def on_same_change(change):
    end_txt.disabled = change['new']
    if change['new']:
        end_txt.value = start_txt.value


def on_compute(_):
    with out:
        clear_output()

    city = city_widget.value.strip()
    start = start_txt.value.strip()
    end = start if same_cb.value else end_txt.value.strip()

    log.info("⏳ Geocodificando partida e destino…")
    pt0 = geocode_strict_single(start, city) or geocode_fallback_single(start, city)
    if not pt0:
        log.error(f"❌ Falha geocode partida: {start}")
        return
    pt1 = pt0 if same_cb.value else (geocode_strict_single(end, city) or geocode_fallback_single(end, city))
    if not pt1:
        log.error(f"❌ Falha geocode destino: {end}")
        return

    coords = [(pt0[0], pt0[1])]
    names = ["Partida"]
    for cb in pois_checkboxes:
        if cb.value:
            nm, coord = cb.description.split(' (')
            lat, lon = coord[:-1].split(',')
            coords.append((float(lat), float(lon)))
            names.append(nm)
    extras = [l.strip() for l in custom_txt.value.splitlines() if l.strip()]
    for ex in extras:
        geo = geocode_strict_single(ex, city) or geocode_fallback_single(ex, city)
        if geo:
            coords.append((geo[0], geo[1]))
            names.append(ex)

    coords.append((pt1[0], pt1[1]))
    names.append("Destino")

    if len(coords) < 3:
        log.error("❌ Selecione ao menos um POI ou extra.")
        return

    log.info("⏳ Obtendo altitudes…")
    alts = batch_altitude(coords)
    coords = [(lat, lon, alt) for (lat, lon), alt in zip(coords, alts)]

    log.info("⏳ Calculando matriz…")
    dist = osrm_table([(lat, lon) for lat, lon, _ in coords])

    end_idx = len(coords) - 1
    best = min(range(1, end_idx), key=lambda i: dist[i][end_idx])

    log.info("🚦 Resolvendo TSP…")
    route = solve_tsp(dist, 0, best)
    if not route:
        log.error("❌ TSP falhou")
        return
    route.append(end_idx)

    log.info("🗺️ Gerando mapa…")
    m = build_map(route, coords, names)
    filename = "rota_otimizada.html"
    m.save(filename)
    log.info(f"✅ HTML salvo: {filename}")
    display(FileLink(filename, result_html_prefix="🔗 ", result_html_suffix=" para download"))


def launch_ui():
    load_pois_btn.on_click(on_load_pois)
    same_cb.observe(on_same_change, 'value')
    compute_btn.on_click(on_compute)

    ui = widgets.HBox([
        widgets.VBox([city_widget, load_pois_btn, widgets.Label("Selecione POIs:"), pois_box]),
        widgets.VBox([start_txt, end_txt, same_cb, custom_txt, compute_btn])
    ])
    display(ui, out)

__all__ = ["launch_ui"]
