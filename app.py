import logging
from typing import Dict, List, Optional

import streamlit as st

from core import RouteResult, compute_route_and_map, load_pois


logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="Roteirização de Bares", layout="wide")

st.title("Roteirização de Bares e Restaurantes")

if "pois" not in st.session_state:
    st.session_state.pois = []
if "pois_report" not in st.session_state:
    st.session_state.pois_report = None

st.markdown("Preencha os dados abaixo para carregar os pontos de interesse e gerar a rota otimizada.")

col_left, col_right = st.columns(2)

with col_left:
    city = st.text_input("Município", value="Diamantina")
    load_pois_clicked = st.button("Carregar POIs")

    if load_pois_clicked:
        if not city.strip():
            st.error("Informe um município antes de buscar POIs.")
        else:
            st.info(f"Buscando POIs em {city}...")
            result = load_pois(city)
            st.session_state.pois = result.pois
            st.session_state.pois_report = result.report
            st.success(f"{len(st.session_state.pois)} POIs carregados.")
            if result.report.tiles_failed:
                st.warning(f"{result.report.tiles_failed} tiles falharam na busca Overpass.")
            if len(result.pois) > 500:
                st.warning("Muitos POIs encontrados (>500). Considere filtrar ou reduzir a área.")

    poi_labels: List[str] = []
    poi_lookup: Dict[str, dict] = {}
    for idx, poi in enumerate(st.session_state.pois):
        label = f"{idx + 1}. {poi['name']} ({poi['lat']:.5f},{poi['lon']:.5f})"
        poi_labels.append(label)
        poi_lookup[label] = poi

    selected_labels = st.multiselect("Selecione POIs", options=poi_labels)
    selected_pois = [poi_lookup[label] for label in selected_labels]

with col_right:
    start = st.text_input("Partida", placeholder="Ex.: Rua das Mercês, 310")
    end = st.text_input("Destino", placeholder="Ex.: Rua Barão…, 208")
    extras_text = st.text_area("Extras (um por linha)")
    elev_weight = st.slider("Peso subida", min_value=0.0, max_value=5.0, step=0.1, value=0.0)

compute_clicked = st.button("Calcular rota")

result: Optional[RouteResult] = None

if compute_clicked:
    extras = [line.strip() for line in extras_text.splitlines() if line.strip()]
    if not city.strip():
        st.error("Informe um município.")
    elif not start.strip():
        st.error("Informe a partida.")
    else:
        st.info("Processando rota. Isso pode levar alguns segundos...")
        try:
            result = compute_route_and_map(
                city=city,
                start=start,
                end=end,
                selected_pois=selected_pois,
                extras=extras,
                elev_weight=float(elev_weight),
            )
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:  # pragma: no cover - fallback visual
            st.error(f"Erro inesperado: {exc}")

if result:
    st.success("Rota calculada com sucesso!")
    st.components.v1.html(result.map_html, height=600, scrolling=True)
    st.download_button(
        "Baixar HTML",
        data=result.map_html,
        file_name="rota_otimizada.html",
        mime="text/html",
    )
