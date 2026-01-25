from unittest import mock
import pytest

requests = pytest.importorskip("requests")
data_fetch = pytest.importorskip("data_fetch")

class FakeResp:
    def __init__(self, data):
        self._data = data
        self.status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return self._data

def test_osrm_table_success():
    resp = FakeResp({"distances": [[0, 1], [1, 0]]})
    with mock.patch('data_fetch.session.get', return_value=resp):
        result = data_fetch.osrm_table([(0,0), (1,1)])
        assert result == [[0,1],[1,0]]

def test_osrm_table_fallback():
    def side_effect(url, params=None, timeout=None):
        if 'sources' in params:
            idx = params['sources']
            return FakeResp({"distances": [[idx*10, idx*10 + 1]]})
        raise requests.RequestException('fail')
    with mock.patch('data_fetch.session.get', side_effect=side_effect):
        result = data_fetch.osrm_table([(0,0), (1,1)])
        assert result == [[0,1],[10,11]]

def test_osrm_table_empty_input():
    with mock.patch('data_fetch.session.get') as mocked_get:
        result = data_fetch.osrm_table([])
        assert result is None
        mocked_get.assert_not_called()


def test_osrm_table_failure_returns_none():
    def side_effect(url, params=None, timeout=None):
        raise requests.RequestException('fail')
    with mock.patch('data_fetch.session.get', side_effect=side_effect):
        result = data_fetch.osrm_table([(0,0), (1,1)])
        assert result is None


def test_coletar_pois_bbox_filtering():
    elements = [
        {"type": "node", "id": 1, "tags": {"name": "Bar1"}, "lat": 1, "lon": 1},  # inside
        {"type": "node", "id": 2, "tags": {"name": "Bar1"}, "lat": 5, "lon": 5},  # outside
        {"type": "node", "id": 3, "tags": {"name": "Bar2"}, "lat": 5, "lon": 5},  # outside only
    ]
    resp = FakeResp({"elements": elements})
    bbox = (0, 2, 0, 2)
    with mock.patch("data_fetch.get_city_bbox", return_value=bbox), \
         mock.patch("data_fetch.get_city_area_id", return_value=None), \
         mock.patch("data_fetch.get_city_polygon", return_value=None), \
         mock.patch("data_fetch.tile_bbox", return_value=[(0, 0, 2, 2)]), \
         mock.patch("data_fetch.session.post", return_value=resp):
        result = data_fetch.coletar_pois("cidade")
        assert result.pois == [
            {
                "poi_id": "osm:node:1",
                "osm_type": "node",
                "osm_id": 1,
                "name": "Bar1",
                "amenity": None,
                "lat": 1.0,
                "lon": 1.0,
            }
        ]


def test_coletar_pois_dedup_inside():
    elements = [
        {"type": "node", "id": 10, "tags": {"name": "Bar1"}, "lat": 1, "lon": 1},
        {"type": "node", "id": 10, "tags": {"name": "Bar1"}, "lat": 1.1, "lon": 1.1},
    ]
    resp = FakeResp({"elements": elements})
    bbox = (0, 2, 0, 2)
    with mock.patch("data_fetch.get_city_bbox", return_value=bbox), \
         mock.patch("data_fetch.get_city_area_id", return_value=None), \
         mock.patch("data_fetch.get_city_polygon", return_value=None), \
         mock.patch("data_fetch.tile_bbox", return_value=[(0, 0, 2, 2)]), \
         mock.patch("data_fetch.session.post", return_value=resp):
        result = data_fetch.coletar_pois("cidade")
        assert result.pois == [
            {
                "poi_id": "osm:node:10",
                "osm_type": "node",
                "osm_id": 10,
                "name": "Bar1",
                "amenity": None,
                "lat": 1.0,
                "lon": 1.0,
            }
        ]


def test_coletar_pois_addr_city():
    elements = [
        {
            "type": "node",
            "id": 21,
            "tags": {"name": "Bar1", "addr:city": "cidade"},
            "lat": 1,
            "lon": 1,
        },
        {
            "type": "node",
            "id": 22,
            "tags": {"name": "Bar2", "addr:city": "Outra"},
            "lat": 1.5,
            "lon": 1.5,
        },
    ]
    resp = FakeResp({"elements": elements})
    bbox = (0, 2, 0, 2)
    with mock.patch("data_fetch.get_city_bbox", return_value=bbox), \
         mock.patch("data_fetch.get_city_area_id", return_value=None), \
         mock.patch("data_fetch.get_city_polygon", return_value=None), \
         mock.patch("data_fetch.tile_bbox", return_value=[(0, 0, 2, 2)]), \
         mock.patch("data_fetch.session.post", return_value=resp):
        result = data_fetch.coletar_pois("cidade")
        assert result.pois == [
            {
                "poi_id": "osm:node:21",
                "osm_type": "node",
                "osm_id": 21,
                "name": "Bar1",
                "amenity": None,
                "lat": 1.0,
                "lon": 1.0,
                "addr:city": "cidade",
            }
        ]


def test_coletar_pois_polygon():
    elements = [
        {"type": "node", "id": 31, "tags": {"name": "Bar1"}, "lat": 1, "lon": 1},
        {"type": "node", "id": 32, "tags": {"name": "Bar2"}, "lat": 5, "lon": 5},
    ]
    resp = FakeResp({"elements": elements})

    class DummyPoly:
        def contains(self, pt):
            x, y = pt.x, pt.y
            return 0 <= y <= 2 and 0 <= x <= 2

    with mock.patch("data_fetch.get_city_bbox", return_value=None), \
         mock.patch("data_fetch.get_city_area_id", return_value=1), \
         mock.patch("data_fetch.get_city_polygon", return_value=DummyPoly()), \
         mock.patch("data_fetch.session.post", return_value=resp):
        result = data_fetch.coletar_pois("cidade")
        assert result.pois == [
            {
                "poi_id": "osm:node:31",
                "osm_type": "node",
                "osm_id": 31,
                "name": "Bar1",
                "amenity": None,
                "lat": 1.0,
                "lon": 1.0,
            }
        ]


def test_coletar_pois_dedup_across_tiles():
    elements_tile_1 = [
        {"type": "node", "id": 1, "tags": {"name": "Bar1"}, "lat": 1, "lon": 1},
        {"type": "node", "id": 2, "tags": {"name": "Bar2"}, "lat": 1.5, "lon": 1.5},
    ]
    elements_tile_2 = [
        {"type": "node", "id": 1, "tags": {"name": "Bar1"}, "lat": 1.1, "lon": 1.1},
        {"type": "node", "id": 3, "tags": {"name": "Bar3"}, "lat": 1.6, "lon": 1.6},
    ]
    resp_1 = FakeResp({"elements": elements_tile_1})
    resp_2 = FakeResp({"elements": elements_tile_2})
    bbox = (0, 2, 0, 2)
    with mock.patch("data_fetch.get_city_bbox", return_value=bbox), \
         mock.patch("data_fetch.get_city_area_id", return_value=None), \
         mock.patch("data_fetch.get_city_polygon", return_value=None), \
         mock.patch("data_fetch.tile_bbox", return_value=[(0, 0, 1, 1), (1, 1, 2, 2)]), \
         mock.patch("data_fetch.session.post", side_effect=[resp_1, resp_2]):
        result = data_fetch.coletar_pois("cidade")
        assert len(result.pois) == 3
        assert result.report.tiles_total == 2
        assert result.report.tiles_failed == 0


def test_coletar_pois_anti_vazamento_bbox():
    elements = [
        {"type": "node", "id": 1, "tags": {"name": "Dentro"}, "lat": 1, "lon": 1},
        {"type": "node", "id": 2, "tags": {"name": "Fora"}, "lat": 3, "lon": 3},
    ]
    resp = FakeResp({"elements": elements})
    bbox = (0, 2, 0, 2)
    with mock.patch("data_fetch.get_city_bbox", return_value=bbox), \
         mock.patch("data_fetch.get_city_area_id", return_value=None), \
         mock.patch("data_fetch.get_city_polygon", return_value=None), \
         mock.patch("data_fetch.tile_bbox", return_value=[(-0.1, -0.1, 2.1, 2.1)]), \
         mock.patch("data_fetch.session.post", return_value=resp):
        result = data_fetch.coletar_pois("cidade")
        assert result.pois == [
            {
                "poi_id": "osm:node:1",
                "osm_type": "node",
                "osm_id": 1,
                "name": "Dentro",
                "amenity": None,
                "lat": 1.0,
                "lon": 1.0,
            }
        ]
