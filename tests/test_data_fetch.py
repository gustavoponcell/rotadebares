from unittest import mock
import pytest

requests = pytest.importorskip("requests")
data_fetch = pytest.importorskip("data_fetch")

class FakeResp:
    def __init__(self, data):
        self._data = data
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


def test_coletar_pois_bbox_filtering():
    elements = [
        {"tags": {"name": "Bar1"}, "lat": 1, "lon": 1},  # inside
        {"tags": {"name": "Bar1"}, "lat": 5, "lon": 5},  # outside dup
        {"tags": {"name": "Bar2"}, "lat": 5, "lon": 5},  # outside only
    ]
    resp = FakeResp({"elements": elements})
    bbox = (0, 2, 0, 2)
    with mock.patch("data_fetch.get_city_bbox", return_value=bbox), \
         mock.patch("data_fetch.session.post", return_value=resp):
        pois = data_fetch.coletar_pois("cidade")
        assert pois == [{"name": "Bar1", "lat": 1.0, "lon": 1.0}]


def test_coletar_pois_dedup_inside():
    elements = [
        {"tags": {"name": "Bar1"}, "lat": 1, "lon": 1},
        {"tags": {"name": "Bar1"}, "lat": 1.1, "lon": 1.1},
    ]
    resp = FakeResp({"elements": elements})
    bbox = (0, 2, 0, 2)
    with mock.patch("data_fetch.get_city_bbox", return_value=bbox), \
         mock.patch("data_fetch.session.post", return_value=resp):
        pois = data_fetch.coletar_pois("cidade")
        assert pois == [{"name": "Bar1", "lat": 1.0, "lon": 1.0}]


def test_coletar_pois_addr_city():
    elements = [
        {"tags": {"name": "Bar1", "addr:city": "cidade"}, "lat": 1, "lon": 1},
        {"tags": {"name": "Bar2", "addr:city": "Outra"}, "lat": 1.5, "lon": 1.5},
    ]
    resp = FakeResp({"elements": elements})
    bbox = (0, 2, 0, 2)
    with mock.patch("data_fetch.get_city_bbox", return_value=bbox), \
         mock.patch("data_fetch.get_city_area_id", return_value=None), \
         mock.patch("data_fetch.get_city_polygon", return_value=None), \
         mock.patch("data_fetch.session.post", return_value=resp):
        pois = data_fetch.coletar_pois("cidade")
        assert pois == [{"name": "Bar1", "lat": 1.0, "lon": 1.0}]


def test_coletar_pois_polygon():
    elements = [
        {"tags": {"name": "Bar1"}, "lat": 1, "lon": 1},
        {"tags": {"name": "Bar2"}, "lat": 5, "lon": 5},
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
        pois = data_fetch.coletar_pois("cidade")
        assert pois == [{"name": "Bar1", "lat": 1.0, "lon": 1.0}]
