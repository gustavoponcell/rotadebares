import sys
import types
import pytest

# Evita falhas de importacao em ambientes sem dependencias pesadas
try:
    from ortools.constraint_solver import pywrapcp
    ORTOOLS_AVAILABLE = True
except Exception:
    ORTOOLS_AVAILABLE = False
    cs = types.ModuleType('ortools.constraint_solver')
    cs.pywrapcp = types.SimpleNamespace()
    cs.routing_enums_pb2 = types.SimpleNamespace()
    sys.modules.setdefault('ortools', types.ModuleType('ortools')).constraint_solver = cs
    sys.modules['ortools.constraint_solver'] = cs

try:
    import networkx
except Exception:
    nx = types.ModuleType('networkx')
    nx.approximation = types.SimpleNamespace(christofides=lambda *a, **k: [])
    sys.modules['networkx'] = nx

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


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="ortools ausente")
def test_solve_tsp():
    r = opt.solve_tsp(DIST, 0, 3)
    _check_route(r)


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="ortools ausente")
def test_solve_tsp_gls():
    r = opt.solve_tsp_guided_local_search(DIST, 0, 3)
    _check_route(r)


@pytest.mark.skipif(not ORTOOLS_AVAILABLE, reason="ortools ausente")
def test_christofides_tsp():
    r = opt.christofides_tsp(DIST, 0, 3)
    _check_route(r)


def test_apply_elevation_penalty_changes_best():
    coords = [(0, 0, 0), (0, 0, 0), (0, 0, 50), (0, 0, 100)]
    base = [[1]*4 for _ in range(4)]
    for i in range(4):
        base[i][i] = 0
    plain_best = min(range(1, 3), key=lambda i: base[i][3])
    penal = opt.apply_elevation_penalty(base, coords, weight=1)
    penal_best = min(range(1, 3), key=lambda i: penal[i][3])
    assert plain_best != penal_best
