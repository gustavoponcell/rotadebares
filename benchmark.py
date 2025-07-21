import time

try:
    from optimization import solve_tsp, solve_tsp_guided_local_search, christofides_tsp
except Exception as exc:
    raise SystemExit(f"Dependencies missing: {exc}")

DIST = [
    [0, 2, 9, 10],
    [1, 0, 6, 4],
    [15, 7, 0, 8],
    [6, 3, 12, 0],
]


def bench(func, name, loops=100):
    t0 = time.perf_counter()
    for _ in range(loops):
        func(DIST, 0, 3)
    t1 = time.perf_counter()
    print(f"{name}: {t1 - t0:.4f}s over {loops} runs")


if __name__ == "__main__":
    bench(solve_tsp, "solve_tsp")
    bench(solve_tsp_guided_local_search, "solve_tsp_guided_local_search")
    bench(christofides_tsp, "christofides_tsp")
