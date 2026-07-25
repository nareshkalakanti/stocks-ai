from stocks.core.database import ensure_db, init_db, _db_initialized_path
import stocks.core.database as db


def test_ensure_db_runs_init_once(monkeypatch):
    calls: list[str] = []

    def _fake_schema():
        calls.append("init")

    monkeypatch.setattr(db, "_init_db_schema", _fake_schema)
    monkeypatch.setattr(db, "_db_initialized_path", None)

    ensure_db()
    ensure_db()
    assert calls == ["init"]


def test_raise_open_file_limit_no_crash():
    from stocks.core.process_limits import raise_open_file_limit

    raise_open_file_limit(256)
