"""Governance DB — DIN / name matching, curated seed, shared seats."""

from __future__ import annotations

from stocks.governance.service import (
    directors_for_ticker,
    governance_stats,
    multi_board_directors,
    overlaps_for_ticker,
    save_company_board,
    seats_for_din,
    seats_for_person,
    seed_curated_boards,
)


def test_seed_20microns_and_shared_person(tmp_path, monkeypatch):
    db_path = tmp_path / "governance_test.db"
    monkeypatch.setattr("stocks.governance.db.GOVERNANCE_DB_PATH", db_path)

    n = seed_curated_boards(force=True)
    assert n == 1
    stats = governance_stats()
    assert stats["companies"] == 1
    assert stats["directors"] == 8
    assert stats["directors_with_din"] == 8

    board = directors_for_ticker("20MICRONS")
    assert len(board) == 8
    assert "00009900" in set(board["din"].dropna().astype(str))

    save_company_board(
        ticker="FAKEPEER",
        name="Fake Peer Industries Limited",
        seats=[
            {
                "din": "00009900",
                "name": "Swaminathan Sivaram",
                "designation": "Independent Director",
                "category": "Independent",
                "source": "test",
                "as_of": "2025-01-01",
            }
        ],
        protect_din_board=False,
    )
    multi = multi_board_directors()
    assert "00009900" in set(multi["din"].dropna().astype(str))
    seats = seats_for_din("00009900")
    assert set(seats["ticker"]) == {"20MICRONS", "FAKEPEER"}
    overlaps = overlaps_for_ticker("20MICRONS")
    assert "FAKEPEER" in set(overlaps["also_ticker"])


def test_protect_din_board_from_name_only_scan(tmp_path, monkeypatch):
    db_path = tmp_path / "governance_protect.db"
    monkeypatch.setattr("stocks.governance.db.GOVERNANCE_DB_PATH", db_path)
    seed_curated_boards(force=True)

    result = save_company_board(
        ticker="20MICRONS",
        name="20 Microns Limited",
        seats=[
            {
                "name": "Someone Else",
                "designation": "Director",
                "source": "yfinance",
            }
        ],
        protect_din_board=True,
    )
    assert result["skipped"] is True
    board = directors_for_ticker("20MICRONS")
    assert len(board) == 8
    assert "00041610" in set(board["din"].dropna().astype(str))


def test_name_only_person_id_shared(tmp_path, monkeypatch):
    db_path = tmp_path / "governance_name.db"
    monkeypatch.setattr("stocks.governance.db.GOVERNANCE_DB_PATH", db_path)

    save_company_board(
        ticker="AAA",
        name="Alpha Ltd",
        seats=[{"name": "Jane Doe", "designation": "Director", "source": "yfinance"}],
        protect_din_board=False,
    )
    save_company_board(
        ticker="BBB",
        name="Beta Ltd",
        seats=[{"name": "Jane Doe", "designation": "Independent Director", "source": "yfinance"}],
        protect_din_board=False,
    )
    multi = multi_board_directors()
    assert len(multi) == 1
    seats = seats_for_person(str(multi.iloc[0]["person_id"]))
    assert set(seats["ticker"]) == {"AAA", "BBB"}
