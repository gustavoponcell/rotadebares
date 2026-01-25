import pytest

data_fetch = pytest.importorskip("data_fetch")


def test_tile_bbox_small_and_large():
    small = (-43.0, -20.0, -42.99, -19.99)
    tiles_small = data_fetch.tile_bbox(small, max_tiles_total=16, overlap_m=200)
    assert len(tiles_small) == 1

    large = (-43.0, -20.0, -42.4, -19.4)
    tiles_large = data_fetch.tile_bbox(large, max_tiles_total=4, overlap_m=200)
    assert 1 < len(tiles_large) <= 4
