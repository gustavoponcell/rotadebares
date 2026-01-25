import logging

import ipywidgets as widgets
from IPython.display import display, clear_output, FileLink

from core import compute_route_and_map, load_pois

log = logging.getLogger(__name__)


class WidgetHandler(logging.Handler):
    """Handler que redireciona logs para um ``ipywidgets.Output``."""

    def __init__(self, widget: widgets.Output) -> None:
        """Inicializa o handler.

        Parameters
        ----------
        widget:
            Widget que exibirá as mensagens de log.
        """

        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        """Imprime a mensagem formatada dentro do widget."""

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
elev_weight = widgets.FloatSlider(
    value=0.0,
    min=0.0,
    max=5.0,
    step=0.1,
    description="Peso subida:",
)
compute_btn = widgets.Button(description="Gerar HTML", button_style="success")
out = widgets.Output()
pois_checkboxes = []
pois_data = []

widget_handler = WidgetHandler(out)
widget_handler.setFormatter(logging.Formatter("%(message)s"))
log.addHandler(widget_handler)
log.propagate = False


def on_load_pois(_: widgets.Button) -> None:
    """Carrega a lista de POIs disponíveis para a cidade informada."""

    with out:
        clear_output()
    log.info(f"🔍 Buscando POIs em {city_widget.value}…")
    pois = load_pois(city_widget.value.strip())
    pois_checkboxes.clear()
    pois_data.clear()
    items = []
    for p in pois:
        desc = f"{p['name']} ({p['lat']:.5f},{p['lon']:.5f})"
        cb = widgets.Checkbox(False, description=desc)
        pois_checkboxes.append(cb)
        pois_data.append(p)
        items.append(cb)
    pois_box.children = items
    log.info(f"✅ {len(pois)} POIs carregados.")


def on_same_change(change: dict) -> None:
    """Sincroniza partida e destino quando o checkbox é marcado."""

    end_txt.disabled = change['new']
    if change['new']:
        end_txt.value = start_txt.value


def on_compute(_: widgets.Button) -> None:
    """Processa todos os passos e gera o HTML da rota."""

    with out:
        clear_output()

    city = city_widget.value.strip()
    start = start_txt.value.strip()
    end = start if same_cb.value else end_txt.value.strip()

    filename = "rota_otimizada.html"
    selected_pois = [
        poi for poi, cb in zip(pois_data, pois_checkboxes) if cb.value
    ]
    extras = [l.strip() for l in custom_txt.value.splitlines() if l.strip()]
    try:
        result = compute_route_and_map(
            city=city,
            start=start,
            end=end,
            selected_pois=selected_pois,
            extras=extras,
            elev_weight=float(elev_weight.value),
        )
    except ValueError as exc:
        log.error(f"❌ {exc}")
        return

    with open(filename, "w", encoding="utf-8") as handle:
        handle.write(result.map_html)
    log.info(f"✅ HTML salvo: {filename}")
    display(FileLink(filename, result_html_prefix="🔗 ", result_html_suffix=" para download"))


def launch_ui() -> None:
    """Exibe a interface interativa no notebook."""

    load_pois_btn.on_click(on_load_pois)
    same_cb.observe(on_same_change, "value")
    compute_btn.on_click(on_compute)

    ui = widgets.HBox(
        [
            widgets.VBox(
                [city_widget, load_pois_btn, widgets.Label("Selecione POIs:"), pois_box]
            ),
            widgets.VBox([
                start_txt,
                end_txt,
                same_cb,
                elev_weight,
                custom_txt,
                compute_btn,
            ]),
        ]
    )
    display(ui, out)

__all__ = ["launch_ui"]
