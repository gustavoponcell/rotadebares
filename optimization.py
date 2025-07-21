from typing import List

import networkx as nx

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def solve_tsp(dist_matrix: List[List[float]], start: int, end: int, time_limit_s: int = 5) -> List[int] | None:
    """Resolve o TSP fixando inicio e fim.

    Parameters
    ----------
    dist_matrix:
        Matriz de distâncias entre os pontos.
    start:
        Índice do ponto de partida.
    end:
        Índice do destino final.
    time_limit_s:
        Tempo limite de busca em segundos.

    Returns
    -------
    list[int] | None
        Ordem dos índices a serem visitados ou ``None`` em caso de falha.
    """
    n = len(dist_matrix)
    mgr = pywrapcp.RoutingIndexManager(n, 1, [start], [end])
    routing = pywrapcp.RoutingModel(mgr)

    def cb(i, j):
        return int(dist_matrix[mgr.IndexToNode(i)][mgr.IndexToNode(j)])

    idx = routing.RegisterTransitCallback(cb)
    routing.SetArcCostEvaluatorOfAllVehicles(idx)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.time_limit.seconds = time_limit_s

    sol = routing.SolveWithParameters(params)
    if not sol:
        return None

    route = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        route.append(mgr.IndexToNode(index))
        index = sol.Value(routing.NextVar(index))
    route.append(mgr.IndexToNode(index))
    return route

__all__ = ["solve_tsp"]


def solve_tsp_guided_local_search(
    dist_matrix: List[List[float]], start: int, end: int, time_limit_s: int = 5
) -> List[int] | None:
    """Resolve o TSP usando GUIDED_LOCAL_SEARCH do OR-Tools.

    Parameters
    ----------
    dist_matrix:
        Matriz de distâncias entre os pontos.
    start:
        Índice do ponto de partida.
    end:
        Índice do destino final.
    time_limit_s:
        Tempo limite de busca em segundos.

    Returns
    -------
    list[int] | None
        Ordem dos índices a serem visitados ou ``None`` em caso de falha.
    """

    n = len(dist_matrix)
    mgr = pywrapcp.RoutingIndexManager(n, 1, [start], [end])
    routing = pywrapcp.RoutingModel(mgr)

    def cb(i: int, j: int) -> int:
        return int(dist_matrix[mgr.IndexToNode(i)][mgr.IndexToNode(j)])

    idx = routing.RegisterTransitCallback(cb)
    routing.SetArcCostEvaluatorOfAllVehicles(idx)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = time_limit_s

    sol = routing.SolveWithParameters(params)
    if not sol:
        return None

    route = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        route.append(mgr.IndexToNode(index))
        index = sol.Value(routing.NextVar(index))
    route.append(mgr.IndexToNode(index))
    return route


def christofides_tsp(dist_matrix: List[List[float]], start: int, end: int) -> List[int]:
    """Aproxima o TSP via algoritmo de Christofides da NetworkX.

    Esta função ignora ``time_limit_s`` e sempre retorna um ciclo começando em
    ``start``. O ``end`` é reposicionado para o final da lista.

    Parameters
    ----------
    dist_matrix:
        Matriz de distâncias entre os pontos.
    start:
        Índice do ponto de partida.
    end:
        Índice do destino final.

    Returns
    -------
    list[int]
        Ordem aproximada dos índices a serem visitados.
    """

    n = len(dist_matrix)
    g = nx.Graph()
    for i in range(n):
        for j in range(i + 1, n):
            g.add_edge(i, j, weight=dist_matrix[i][j])

    cycle = nx.approximation.christofides(g, weight="weight")

    # reordena para comecar em start e terminar em end
    if start in cycle:
        while cycle[0] != start:
            cycle.append(cycle.pop(0))
    if end in cycle:
        while cycle[-1] != end:
            cycle.append(cycle.pop(0))
    else:
        # remove retorno ao inicio e adiciona end no final
        cycle = cycle[:-1] + [end]

    return cycle


__all__.extend(["solve_tsp_guided_local_search", "christofides_tsp"])
