from unittest import mock

import pytest

core = pytest.importorskip("core")
data_fetch = pytest.importorskip("data_fetch")


def test_fetch_places_default_tags_do_not_filter_text():
    pois = [
        {"poi_id": "osm:node:1", "amenity": "bar", "name": "Bar Alpha", "lat": 0, "lon": 0},
        {"poi_id": "osm:node:2", "amenity": "cafe", "name": "Cafe Beta", "lat": 1, "lon": 1},
    ]
    report = data_fetch.PoisFetchReport(tiles_total=1, tiles_failed=0)
    osm_result = data_fetch.PoisFetchResult(pois=pois, report=report)
    with mock.patch("core.fetch_osm_pois", return_value=osm_result):
        result = core.fetch_places(
            city="Cidade",
            bbox=None,
            selected_tags=list(data_fetch.AMENITY_TAGS),
            include_overture=False,
        )
    assert len(result.pois) == 2


def test_fetch_places_text_only_filters_by_text():
    pois = [
        {"poi_id": "osm:node:1", "amenity": "bar", "name": "Boteco do Zé", "lat": 0, "lon": 0},
        {"poi_id": "osm:node:2", "amenity": "bar", "name": "Bar Central", "lat": 1, "lon": 1},
    ]
    report = data_fetch.PoisFetchReport(tiles_total=1, tiles_failed=0)
    osm_result = data_fetch.PoisFetchResult(pois=pois, report=report)
    with mock.patch("core.fetch_osm_pois", return_value=osm_result):
        result = core.fetch_places(
            city="Cidade",
            bbox=None,
            selected_tags=["boteco"],
            include_overture=False,
        )
    assert [poi["poi_id"] for poi in result.pois] == ["osm:node:1"]


def test_trim_pois_for_osrm_limit():
    pois = [
        {"poi_id": f"osm:node:{i}", "lat": float(i), "lon": float(i), "name": f"POI {i}"}
        for i in range(500)
    ]
    trimmed, trimmed_total = core.trim_pois_for_osrm(
        pois=pois,
        start_coords=None,
        bbox=(0.0, 10.0, 0.0, 10.0),
        limit=300,
    )
    assert len(trimmed) == 300
    assert trimmed_total == 200
