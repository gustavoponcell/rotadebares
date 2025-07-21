import types
from unittest import mock
import geocoding

class FakeLoc:
    def __init__(self, lat, lon):
        self.latitude = lat
        self.longitude = lon
        self.raw = {}


def test_dentro_da_cidade_true():
    bbox = (-10, 10, -20, 20)
    assert geocoding.dentro_da_cidade(0, 0, bbox)

def test_dentro_da_cidade_false():
    bbox = (-10, 10, -20, 20)
    assert not geocoding.dentro_da_cidade(15, 0, bbox)

def test_geocode_strict_cache():
    fake = FakeLoc(1.0, 2.0)
    with mock.patch('geocoding.geocode_rl', return_value=fake) as mg:
        with mock.patch('geocoding.get_city_bbox', return_value=(-2,2,-2,2)):
            geocoding._cache_geo.clear()
            r1 = geocoding.geocode_strict_single('addr', 'city')
            r2 = geocoding.geocode_strict_single('addr', 'city')
            assert r1 == (1.0, 2.0)
            assert r2 == (1.0, 2.0)
            assert mg.call_count == 1

def test_geocode_fallback_photon():
    fake = FakeLoc(3.0, 4.0)
    with mock.patch('geocoding.geocode_rl', return_value=None):
        with mock.patch('geocoding.photon_geocode_rl', return_value=fake):
            geocoding._cache_geo.clear()
            result = geocoding.geocode_fallback_single('addr', 'city')
            assert result == (3.0, 4.0)


def test_geocode_city_mismatch():
    loc = FakeLoc(1.0, 2.0)
    loc.raw = {"address": {"city": "Outra"}}
    with mock.patch('geocoding.geocode_rl', return_value=loc):
        with mock.patch('geocoding.get_city_bbox', return_value=(-2, 2, -2, 2)):
            with mock.patch('geocoding.get_city_polygon', return_value=None):
                geocoding._cache_geo.clear()
                assert geocoding.geocode_strict_single('addr', 'city') is None


def test_geocode_polygon_filter():
    loc = FakeLoc(5.0, 5.0)
    loc.raw = {"address": {"city": "city"}}

    class DummyPoly:
        def contains(self, pt):
            return False

    with mock.patch('geocoding.geocode_rl', return_value=loc):
        with mock.patch('geocoding.get_city_bbox', return_value=None):
            with mock.patch('geocoding.get_city_polygon', return_value=DummyPoly()):
                geocoding._cache_geo.clear()
                assert geocoding.geocode_strict_single('addr', 'city') is None
