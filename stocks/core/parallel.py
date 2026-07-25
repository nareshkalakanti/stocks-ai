"""Bounded thread-pool execution — avoids EMFILE on large Yahoo/DB scans."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

T = TypeVar("T")


def run_thread_pool_map(
    jobs: list[tuple],
    fn: Callable[..., T],
    *,
    max_workers: int,
    batch_size: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[tuple[tuple, T | None]]:
    """
    Run ``fn(*job)`` with at most ``max_workers`` concurrent tasks.

    Only ``batch_size`` futures are queued at once (default ``max_workers * 4``)
    so large universes do not exhaust file descriptors.
    """
    if not jobs:
        return []

    workers = max(1, min(int(max_workers), len(jobs)))
    batch = batch_size if batch_size is not None else max(workers * 4, workers)
    batch = max(batch, workers)
    total = len(jobs)
    done = 0
    out: list[tuple[tuple, T | None]] = []

    for start in range(0, total, batch):
        chunk = jobs[start : start + batch]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fn, *job): job for job in chunk}
            for future in as_completed(futures):
                job = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = None
                out.append((job, result))
                done += 1
                if progress_callback:
                    progress_callback(done, total)
    return out
