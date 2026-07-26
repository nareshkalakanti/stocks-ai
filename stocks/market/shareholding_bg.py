"""Background batch fill for named public individual holders (SHP XBRL)."""

from __future__ import annotations

import threading
import time
from typing import Any

from stocks.core.text_utils import safe_str
from stocks.market.shareholding import hydrate_public_holders_for_tickers

_LOCK = threading.Lock()
_STATE: dict[str, Any] = {
    "running": False,
    "stop": False,
    "scanned": 0,
    "batch_size": 100,
    "batches": 0,
    "pending_start": 0,
    "pending_now": 0,
    "last_ticker": "",
    "error": None,
    "started_at": None,
    "finished_at": None,
}
_THREAD: threading.Thread | None = None


def individual_holders_background_status() -> dict[str, Any]:
    with _LOCK:
        return dict(_STATE)


def stop_individual_holders_background() -> None:
    with _LOCK:
        _STATE["stop"] = True


def start_individual_holders_background(
    tickers: list[str],
    *,
    batch_size: int = 100,
    pause_sec: float = 0.35,
) -> bool:
    """
    Start a daemon that hydrates missing individual >1% holders in batches.

    Returns False if a job is already running.
    """
    global _THREAD
    keys = sorted({safe_str(t).upper() for t in tickers if safe_str(t)})
    if not keys:
        return False
    with _LOCK:
        if _STATE["running"]:
            return False
        _STATE.update(
            {
                "running": True,
                "stop": False,
                "scanned": 0,
                "batch_size": max(10, int(batch_size)),
                "batches": 0,
                "pending_start": len(keys),
                "pending_now": len(keys),
                "last_ticker": "",
                "error": None,
                "started_at": time.time(),
                "finished_at": None,
            }
        )
        target = list(keys)

    def _worker() -> None:
        from stocks.governance.map_data import missing_public_holder_tickers

        try:
            while True:
                with _LOCK:
                    if _STATE["stop"]:
                        break
                    size = int(_STATE["batch_size"] or 100)
                pending = missing_public_holder_tickers(target)
                with _LOCK:
                    _STATE["pending_now"] = len(pending)
                if not pending:
                    break
                batch = pending[:size]
                with _LOCK:
                    _STATE["last_ticker"] = batch[0]
                n = hydrate_public_holders_for_tickers(batch, max_fetch=len(batch))
                with _LOCK:
                    _STATE["scanned"] = int(_STATE["scanned"] or 0) + int(n)
                    _STATE["batches"] = int(_STATE["batches"] or 0) + 1
                    _STATE["last_ticker"] = batch[min(n, len(batch)) - 1] if n else batch[-1]
                    _STATE["pending_now"] = max(0, len(pending) - int(n))
                if pause_sec > 0:
                    time.sleep(float(pause_sec))
        except Exception as exc:  # pragma: no cover - surfaced in status
            with _LOCK:
                _STATE["error"] = str(exc)
        finally:
            with _LOCK:
                _STATE["running"] = False
                _STATE["stop"] = False
                _STATE["finished_at"] = time.time()
                try:
                    _STATE["pending_now"] = len(missing_public_holder_tickers(target))
                except Exception:
                    pass
            try:
                from stocks.market.shareholding import export_scanned_shareholding_data

                export_scanned_shareholding_data()
            except Exception:
                pass

    _THREAD = threading.Thread(
        target=_worker,
        name="individual-holders-bg",
        daemon=True,
    )
    _THREAD.start()
    return True


__all__ = [
    "individual_holders_background_status",
    "start_individual_holders_background",
    "stop_individual_holders_background",
]
