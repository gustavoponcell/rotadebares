from cache import CacheManager, make_cache_key, stable_coords
from config import Settings


def test_cache_respects_ttl():
    settings = Settings(cache_ttl_seconds=0, cache_enabled=True, cache_persist=False)
    cache = CacheManager(settings)
    key = make_cache_key("test", {"a": 1})
    cache.set(key, "value")
    assert cache.get(key) is None


def test_stable_coords_rounding():
    coords = [(1.12345678, -2.987654321)]
    assert stable_coords(coords) == [[1.123457, -2.987654]]
