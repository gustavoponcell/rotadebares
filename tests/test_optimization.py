import pytest

opt = pytest.importorskip('optimization')

DIST = [
    [0, 2, 9, 10],
    [1, 0, 6, 4],
    [15, 7, 0, 8],
    [6, 3, 12, 0],
]


def _check_route(route):
    assert route[0] == 0
    assert route[-1] == 3
    assert set(route) == {0,1,2,3}
    assert len(route) == 4


def test_solve_tsp():
    r = opt.solve_tsp(DIST, 0, 3)
    _check_route(r)


def test_solve_tsp_gls():
    r = opt.solve_tsp_guided_local_search(DIST, 0, 3)
    _check_route(r)


def test_christofides_tsp():
    r = opt.christofides_tsp(DIST, 0, 3)
    _check_route(r)
