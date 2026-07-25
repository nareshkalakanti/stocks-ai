from stocks.core.database import ensure_db, get_connection


def test_configure_sqlite_uses_wal(tmp_path, monkeypatch):
    db_path = tmp_path / "wal.db"
    monkeypatch.setattr("stocks.core.database.DB_PATH", db_path)
    monkeypatch.setattr("stocks.core.database._db_initialized_path", None)

    ensure_db()
    with get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert str(mode).lower() == "wal"
    assert int(timeout) >= 30000
