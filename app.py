import logging
from typing import Dict, List, Optional, Tuple

import folium
import streamlit as st

from core import (
    RouteResult,
    approximate_distance_km,
    build_poi_text_blob,
    compute_route_and_map,
    fetch_places,
    trim_pois_for_osrm,
)
from data_fetch import AMENITY_TAGS, OSM_AMENITY_TAGS, PTBR_TEXT_TAGS
from geocoding import geocode_fallback_single, geocode_strict_single, get_city_bbox
from overture_fetch import is_overture_enabled


logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="Roteirização de Bares", layout="wide")

st.title("Roteirização de Bares e Restaurantes")

MAX_OSRM_POIS = 300
PREVIEW_MAP_LIMIT = 200

if "pois" not in st.session_state:
    st.session_state.pois = []
if "pois_report" not in st.session_state:
    st.session_state.pois_report = None
if "selected_tags" not in st.session_state:
    st.session_state.selected_tags = list(AMENITY_TAGS)


@st.cache_data(ttl=3600)
def cached_fetch_places(
    city: str,
    selected_tags: Tuple[str, ...],
    include_overture: bool,
) -> Tuple[List[dict], object]:
    bbox = get_city_bbox(city)
    result = fetch_places(
        city=city,
        bbox=bbox,
        selected_tags=list(selected_tags),
        include_overture=include_overture,
        combined_limit=MAX_OSRM_POIS,
    )
    return result.pois, result.report


def _get_reference_coords(city: str, start_text: str) -> Optional[Tuple[float, float]]:
    if start_text:
        geo = geocode_strict_single(start_text, city) or geocode_fallback_single(start_text, city)
        if geo:
            return geo[0], geo[1]
    bbox = get_city_bbox(city)
    if bbox:
        return (bbox[0] + bbox[1]) / 2.0, (bbox[2] + bbox[3]) / 2.0
    return None


def _compute_counts(
    pois: List[dict],
    selected_tags: List[str],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    counts_osm = {tag: 0 for tag in selected_tags if tag in OSM_AMENITY_TAGS}
    counts_text = {tag: 0 for tag in selected_tags if tag in PTBR_TEXT_TAGS}
    for poi in pois:
        amenity = (poi.get("amenity") or poi.get("category") or "").lower()
        if amenity in counts_osm:
            counts_osm[amenity] += 1
        if counts_text:
            blob = build_poi_text_blob(poi).lower()
            for tag in counts_text:
                if tag in blob:
                    counts_text[tag] += 1
    return counts_osm, counts_text


def _build_preview_table(
    pois: List[dict],
    reference: Optional[Tuple[float, float]],
) -> List[dict]:
    rows: List[dict] = []
    for poi in pois:
        lat = float(poi.get("lat", 0.0))
        lon = float(poi.get("lon", 0.0))
        distance_km = None
        if reference:
            distance_km = approximate_distance_km(reference[0], reference[1], lat, lon)
        rows.append(
            {
                "Nome": poi.get("name"),
                "Tipo": poi.get("amenity") or poi.get("category"),
                "Fonte": poi.get("source"),
                "Lat": lat,
                "Lon": lon,
                "Distância (km)": round(distance_km, 2) if distance_km is not None else None,
            }
        )
    return rows


def _build_preview_map(
    pois: List[dict],
    reference: Optional[Tuple[float, float]],
) -> Optional[str]:
    if not pois or len(pois) > PREVIEW_MAP_LIMIT:
        return None
    if reference:
        center_lat, center_lon = reference
    else:
        center_lat = float(pois[0].get("lat", 0.0))
        center_lon = float(pois[0].get("lon", 0.0))
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    for poi in pois:
        folium.Marker(
            location=[poi["lat"], poi["lon"]],
            popup=f"{poi.get('name')} ({poi.get('amenity') or poi.get('category')})",
            tooltip=poi.get("name"),
        ).add_to(fmap)
    return fmap.get_root().render()


st.markdown("Preencha os dados abaixo para carregar os pontos de interesse e gerar a rota otimizada.")

col_left, col_right = st.columns(2)

with col_left:
    city = st.text_input("Município", value="Diamantina", key="city")
    include_overture_toggle = st.toggle("Incluir Overture Places (experimental)", value=False)
    debug_mode = st.toggle("Modo debug", value=False)
    include_overture = include_overture_toggle or is_overture_enabled()

    st.subheader("Filtros de categorias")
    btn_all, btn_clear = st.columns(2)
    if btn_all.button("Selecionar todos", use_container_width=True):
        st.session_state.selected_tags = list(AMENITY_TAGS)
    if btn_clear.button("Limpar", use_container_width=True):
        st.session_state.selected_tags = []

    selected_tags = st.multiselect(
        "Tipos de lugares",
        options=AMENITY_TAGS,
        key="selected_tags",
    )

    if city.strip() and selected_tags:
        with st.spinner("Carregando lugares…"):
            pois, report = cached_fetch_places(city.strip(), tuple(selected_tags), include_overture)
        st.session_state.pois = pois
        st.session_state.pois_report = report
    else:
        st.session_state.pois = []
        st.session_state.pois_report = None

    st.markdown("### Prévia")
    if not city.strip():
        st.info("Informe um município para carregar a prévia.")
    elif not selected_tags:
        st.info("Selecione ao menos uma categoria para visualizar lugares.")
    else:
        preview_pois = st.session_state.pois
        preview_report = st.session_state.pois_report
        if include_overture and preview_report and preview_report.overture_error:
            st.warning("Overture indisponível neste ambiente. Usando apenas OSM.")
        if preview_report and preview_report.trimmed_total:
            st.warning(
                "Limite de POIs aplicado (%s). %s pontos ficaram fora para evitar excesso no OSRM."
                % (len(preview_pois), preview_report.trimmed_total)
            )
        if preview_report and preview_report.tiles_failed:
            st.warning(f"{preview_report.tiles_failed} tiles falharam na busca Overpass.")

        st.metric("Total de lugares", len(preview_pois))

        counts_osm, counts_text = _compute_counts(preview_pois, selected_tags)
        if counts_osm:
            st.markdown("**Contagem por categoria (OSM)**")
            st.dataframe(
                [{"Categoria": key, "Total": value} for key, value in counts_osm.items()],
                use_container_width=True,
                hide_index=True,
            )
        if counts_text:
            st.markdown("**Matches por texto (tags PT-BR)**")
            st.dataframe(
                [{"Tag": key, "Total": value} for key, value in counts_text.items()],
                use_container_width=True,
                hide_index=True,
            )

        reference = _get_reference_coords(city.strip(), st.session_state.get("start", "").strip())
        preview_rows = _build_preview_table(preview_pois, reference)
        st.markdown("**Tabela de lugares**")
        st.dataframe(preview_rows, use_container_width=True, hide_index=True)

        preview_map_html = _build_preview_map(preview_pois, reference)
        if preview_map_html:
            st.markdown("**Mapa preview**")
            st.components.v1.html(preview_map_html, height=400, scrolling=True)

        if debug_mode and preview_report:
            st.markdown("### Debug")
            st.write("**BBox**", preview_report.bbox)
            st.write("**Area ID**", preview_report.area_id)
            if preview_report.tiles:
                st.write("**Tiles**", preview_report.tiles)
            counts_table = [
                {"Etapa": "Overpass bruto", "Total": preview_report.raw_total},
                {"Etapa": "Parse ok", "Total": preview_report.parsed_total},
                {"Etapa": "Merge", "Total": preview_report.merged_total},
                {"Etapa": "Dedupe", "Total": preview_report.dedup_total},
                {"Etapa": "Anti-vazamento", "Total": preview_report.bbox_filtered_total},
                {"Etapa": "Filtro texto", "Total": preview_report.text_filtered_total},
                {"Etapa": "Limite final", "Total": preview_report.limit_total or len(preview_pois)},
            ]
            st.dataframe(counts_table, use_container_width=True, hide_index=True)
            if preview_report.tile_raw_counts:
                st.markdown("**Counts por tile (Overpass)**")
                st.dataframe(preview_report.tile_raw_counts, use_container_width=True, hide_index=True)
            if preview_report.overpass_errors:
                st.markdown("**Erros Overpass**")
                st.dataframe(preview_report.overpass_errors, use_container_width=True, hide_index=True)
            if preview_report.sample_pois:
                st.markdown("**Amostra (<=5)**")
                st.dataframe(preview_report.sample_pois, use_container_width=True, hide_index=True)
            st.markdown("**Primeiros 20 POIs**")
            st.dataframe(preview_rows[:20], use_container_width=True, hide_index=True)

    poi_labels: List[str] = []
    poi_lookup: Dict[str, dict] = {}
    for idx, poi in enumerate(st.session_state.pois):
        label = (
            f"{idx + 1}. {poi['name']}"
            f" ({poi.get('amenity') or poi.get('category')}, {poi.get('source')})"
        )
        poi_labels.append(label)
        poi_lookup[label] = poi

    selected_labels = st.multiselect("Selecione POIs", options=poi_labels)
    selected_pois = [poi_lookup[label] for label in selected_labels]

with col_right:
    start = st.text_input("Partida", placeholder="Ex.: Rua das Mercês, 310", key="start")
    end = st.text_input("Destino", placeholder="Ex.: Rua Barão…, 208", key="end")
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
    elif not selected_pois:
        st.error("Selecione ao menos um POI.")
    else:
        trimmed_selected_pois = selected_pois
        if len(selected_pois) > MAX_OSRM_POIS:
            start_coords = None
            geo = geocode_strict_single(start.strip(), city.strip()) or geocode_fallback_single(start.strip(), city.strip())
            if geo:
                start_coords = (geo[0], geo[1])
            trimmed_selected_pois, trimmed_total = trim_pois_for_osrm(
                selected_pois,
                start_coords,
                get_city_bbox(city.strip()),
                MAX_OSRM_POIS,
            )
            if trimmed_total:
                st.warning(
                    "Muitos POIs selecionados. Mantendo os %s mais próximos e removendo %s pontos."
                    % (len(trimmed_selected_pois), trimmed_total)
                )

        st.info("Processando rota. Isso pode levar alguns segundos...")
        try:
            result = compute_route_and_map(
                city=city,
                start=start,
                end=end,
                selected_pois=trimmed_selected_pois,
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
