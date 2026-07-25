"""Process-level limits — raise open-file ceiling before heavy scans."""

from __future__ import annotations

import os


def raise_open_file_limit(min_soft: int | None = None) -> None:
    """Best-effort bump of RLIMIT_NOFILE (macOS default soft limit is often 256)."""
    target = min_soft
    if target is None:
        raw = os.getenv("OPEN_FILE_LIMIT", "4096")
        try:
            target = int(raw)
        except ValueError:
            target = 4096
    if target <= 0:
        return
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        new_soft = min(max(target, soft), hard if hard > 0 else target)
        if new_soft > soft:
            resource.setrlimit(resource.RLIMIT_NOFILE, (new_soft, hard))
    except Exception:
        pass
