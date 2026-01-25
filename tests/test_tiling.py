import pytest

data_fetch = pytest.importorskip("data_fetch")


def test_tile_bbox_small_and_large():
    small = (-43.0, -20.0, -42.99, -19.99)
    tiles_small = data_fetch.tile_bbox(small, max_tiles_total=16, overlap_m=200)
    assert len(tiles_small) == 1

    large = (-43.0, -20.0, -42.4, -19.4)
    tiles_large = data_fetch.tile_bbox(large, max_tiles_total=4, overlap_m=200)
    assert 1 < len(tiles_large) <= 4


def test_tile_bbox_order_preserved():
    bbox = (-43.0, -20.0, -42.0, -19.0)
    tiles = data_fetch.tile_bbox(bbox, max_tiles_total=4, overlap_m=0)
    assert tiles
    for tile in tiles:
        min_lon, min_lat, max_lon, max_lat = tile
        assert min_lon <= max_lon
        assert min_lat <= max_lat
        assert bbox[0] <= min_lon <= bbox[2]
        assert bbox[1] <= min_lat <= bbox[3]
