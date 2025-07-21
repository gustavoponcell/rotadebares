from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def solve_tsp(dist_matrix, start, end, time_limit_s=5):
    """Resolve o TSP fixando ponto inicial e final."""
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
