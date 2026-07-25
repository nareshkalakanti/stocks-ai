import threading

from stocks.core.parallel import run_thread_pool_map


def test_run_thread_pool_map_processes_all_jobs_in_batches():
    seen: list[int] = []
    lock = threading.Lock()

    def worker(n: int) -> int:
        with lock:
            seen.append(n)
        return n * 2

    jobs = [(i,) for i in range(10)]
    out = run_thread_pool_map(jobs, worker, max_workers=2, batch_size=3)
    assert len(out) == 10
    assert sorted(v for _, v in out if v is not None) == list(range(0, 20, 2))
    assert sorted(seen) == list(range(10))
