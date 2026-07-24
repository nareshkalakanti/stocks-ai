"""Governance DB — DIN / name matching, curated seed, batched scan."""

from __future__ import annotations

import pandas as pd

from stocks.governance.scan import pending_governance_jobs, run_governance_scan
from stocks.governance.service import (
    companies_with_boards,
    directors_for_ticker,
    multi_board_directors,
    overlaps_for_ticker,
    record_scan_attempt,
    save_company_board,
    seats_for_din,
    seats_for_person,
    seed_curated_boards,
    governance_stats,
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


def test_seed_stores_sector_when_available(tmp_path, monkeypatch):
    db_path = tmp_path / "governance_sector.db"
    monkeypatch.setattr("stocks.governance.db.GOVERNANCE_DB_PATH", db_path)
    monkeypatch.setattr(
        "stocks.governance.service._lookup_company_classification",
        lambda ticker, market="NSE": {
            "sector": "Basic Materials",
            "industry": "Specialty Chemicals",
            "sub_sector": "Specialty Chemicals",
        },
    )
    seed_curated_boards(force=True)
    companies = companies_with_boards()
    row = companies[companies["ticker"] == "20MICRONS"].iloc[0]
    assert row["sector"] == "Basic Materials"


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
        seats=[
            {
                "name": "Jane Doe",
                "designation": "Independent Director",
                "source": "yfinance",
            }
        ],
        protect_din_board=False,
    )
    multi = multi_board_directors()
    assert len(multi) == 1
    seats = seats_for_person(str(multi.iloc[0]["person_id"]))
    assert set(seats["ticker"]) == {"AAA", "BBB"}


def test_purge_bse_and_nse_only_market(tmp_path, monkeypatch):
    from stocks.governance.service import save_company_board
    from stocks.governance.db import get_governance_connection, init_governance_db

    db_path = tmp_path / "governance_nse_only.db"
    monkeypatch.setattr("stocks.governance.db.GOVERNANCE_DB_PATH", db_path)
    init_governance_db()

    save_company_board(
        ticker="NSECO",
        name="NSE Co",
        market="NSE",
        seats=[{"name": "Only Nse", "designation": "Director", "source": "test"}],
        protect_din_board=False,
    )
    try:
        save_company_board(
            ticker="BAD",
            name="Bad",
            market="BSE",
            seats=[{"name": "X", "designation": "Director", "source": "test"}],
            protect_din_board=False,
        )
        assert False, "expected BSE save to fail"
    except ValueError as exc:
        assert "NSE-only" in str(exc)

    # Insert BSE row directly (save_company_board rejects BSE).
    with get_governance_connection() as conn:
        conn.execute(
            """
            INSERT INTO companies (ticker, market, name, updated_at)
            VALUES ('BSECO', 'BSE', 'BSE Co', '2020-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO directors (person_id, din, name, name_key, updated_at)
            VALUES ('n:bse only', NULL, 'Bse Only', 'bse only', '2020-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO board_seats (
                ticker, person_id, designation, category, source, as_of, fetched_at
            ) VALUES ('BSECO', 'n:bse only', 'Director', '', 'test', NULL, '2020-01-01')
            """
        )

    from stocks.governance.db import _purge_bse_data

    with get_governance_connection() as conn:
        purged = _purge_bse_data(conn)
    assert purged["companies_deleted"] >= 1
    assert purged["directors_deleted"] >= 1
    with get_governance_connection() as conn:
        markets = {
            r[0] for r in conn.execute("SELECT DISTINCT market FROM companies").fetchall()
        }
        assert markets == {"NSE"}
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM directors WHERE person_id = 'n:bse only'"
            ).fetchone()[0]
            == 0
        )


def test_batch_skips_scanned(tmp_path, monkeypatch):
    db_path = tmp_path / "governance_batch.db"
    monkeypatch.setattr("stocks.governance.db.GOVERNANCE_DB_PATH", db_path)

    universe = pd.DataFrame(
        [
            {"ticker": "AAA", "name": "A", "market": "NSE"},
            {"ticker": "BBB", "name": "B", "market": "NSE"},
            {"ticker": "CCC", "name": "C", "market": "NSE"},
        ]
    )
    record_scan_attempt("AAA", "empty")
    pending = pending_governance_jobs(universe, skip_scanned=True)
    assert [t for t, _, _ in pending] == ["BBB", "CCC"]

    def _fake_fetch(ticker, market="NSE"):
        # Stable unique DIN per ticker for DIN-backed save path.
        din = f"{(abs(hash(ticker)) % 90_000_000) + 10_000_000:08d}"
        return {
            "ticker": ticker,
            "name": ticker,
            "seats": [
                {
                    "din": din,
                    "name": f"Dir {ticker}",
                    "designation": "Director",
                    "category": "Independent",
                    "source": "nse_test",
                }
            ],
            "source": "nse_test",
        }

    monkeypatch.setattr("stocks.governance.scan.fetch_board_for_ticker", _fake_fetch)
    result = run_governance_scan(universe, batch_size=1, skip_scanned=True)
    assert result["scanned"] == 1
    assert result["pending_before"] == 2
    assert result["pending_after"] == 1
    assert result["done"] is False

    result2 = run_governance_scan(universe, batch_size=40, skip_scanned=True)
    assert result2["pending_after"] == 0
    assert result2["done"] is True


def test_holdings_governance_coverage(tmp_path, monkeypatch):
    from stocks.governance.service import holdings_governance_coverage

    db_path = tmp_path / "governance_hold_cov.db"
    monkeypatch.setattr("stocks.governance.db.GOVERNANCE_DB_PATH", db_path)

    monkeypatch.setattr(
        "stocks.shared.portfolio.load_holdings",
        lambda seed_if_empty=True: pd.DataFrame(
            [
                {"ticker": "AAA", "market": "NSE", "name": "Alpha"},
                {"ticker": "BBB", "market": "NSE", "name": "Beta"},
            ]
        ),
    )
    save_company_board(
        ticker="AAA",
        name="Alpha Ltd",
        seats=[{"name": "Dir A", "designation": "Director", "source": "test"}],
        protect_din_board=False,
    )
    cov = holdings_governance_coverage()
    assert cov["total"] == 2
    assert cov["with_board"] == 1
    assert cov["missing"] == ["BBB"]


def test_dir_score_bridge_and_din_weight():
    from stocks.governance.score import mcap_cap_code, mcap_cap_label, score_director_seats

    assert mcap_cap_code(50) == "NC"
    assert mcap_cap_code(200) == "MIC"
    assert mcap_cap_code(1_000) == "SC"
    assert mcap_cap_code(10_000) == "MC"
    assert mcap_cap_code(50_000) == "LC"
    assert mcap_cap_code(None) is None
    assert "Mid Cap" in (mcap_cap_label(10_000) or "")

    din_bridge = score_director_seats(
        [
            {
                "ticker": "BIGCO",
                "market_cap_cr": 20_000,
                "designation": "Independent Director",
                "category": "Independent",
            },
            {
                "ticker": "SMALLCO",
                "market_cap_cr": 400,
                "designation": "Independent Director",
                "category": "Independent",
            },
        ],
        person_id="00009900",
        din="00009900",
    )
    assert din_bridge["bridge"] is True
    assert din_bridge["big_n"] == 1
    assert din_bridge["small_n"] == 1
    assert din_bridge["dir_score"] > 40

    name_only = score_director_seats(
        [
            {
                "ticker": "BIGCO",
                "market_cap_cr": 20_000,
                "designation": "Director",
            },
            {
                "ticker": "SMALLCO",
                "market_cap_cr": 400,
                "designation": "Director",
            },
        ],
        person_id="n:jane doe",
        din=None,
    )
    assert name_only["match_weight"] == 0.25
    assert name_only["dir_score"] < din_bridge["dir_score"]
    assert name_only["name_collision"] is False

    small_only = score_director_seats(
        [
            {"ticker": "A", "market_cap_cr": 200, "designation": "Director"},
            {"ticker": "B", "market_cap_cr": 300, "designation": "Director"},
        ],
        person_id="00009900",
        din="00009900",
    )
    assert small_only["bridge"] is False
    assert small_only["dir_score"] < din_bridge["dir_score"]
    assert small_only["name_collision"] is False

    crowded_name = score_director_seats(
        [
            {"ticker": f"T{i}", "market_cap_cr": 400, "designation": "Director"}
            for i in range(6)
        ],
        person_id="n:sanjay jain",
        din=None,
    )
    assert crowded_name["din_backed"] is False
    assert crowded_name["name_collision"] is True

    crowded_din = score_director_seats(
        [
            {"ticker": f"T{i}", "market_cap_cr": 400, "designation": "Director"}
            for i in range(6)
        ],
        person_id="00009900",
        din="00009900",
    )
    assert crowded_din["name_collision"] is False


def test_filter_governance_map_by_mcap():
    from stocks.governance.map_data import filter_governance_map_by_mcap

    df = pd.DataFrame(
        [
            {
                "person_id": "00009900",
                "din": "00009900",
                "name": "A",
                "director": "A",
                "board_count": 2,
                "dir_score": 50,
                "din_backed": True,
                "big_n": 1,
                "small_n": 1,
                "bridge": True,
                "tickers": "BIG, SMALL",
                "companies": [
                    {
                        "ticker": "BIG",
                        "market_cap_cr": 25000,
                        "designation": "Director",
                    },
                    {
                        "ticker": "SMALL",
                        "market_cap_cr": 200,
                        "designation": "Director",
                    },
                ],
                "score_breakdown": {},
            }
        ]
    )
    micro = filter_governance_map_by_mcap(df, min_cr=100, max_cr=500, min_boards=2)
    assert micro.empty  # only one company in micro band
    smallish = filter_governance_map_by_mcap(df, min_cr=100, max_cr=30000, min_boards=2)
    assert len(smallish) == 1
    assert set(c["ticker"] for c in smallish.iloc[0]["companies"]) == {"BIG", "SMALL"}


def test_governance_map_rows(tmp_path, monkeypatch):
    from stocks.governance.map_data import build_governance_map_rows

    db_path = tmp_path / "governance_map.db"
    monkeypatch.setattr("stocks.governance.db.GOVERNANCE_DB_PATH", db_path)
    monkeypatch.setattr(
        "stocks.governance.map_data.load_market_cap_from_db",
        lambda tickers: pd.DataFrame(
            [
                {"ticker": "BIGCO", "market_cap_cr": 12_000.0},
                {"ticker": "SMALLCO", "market_cap_cr": 350.0},
            ]
        ),
    )
    monkeypatch.setattr(
        "stocks.governance.map_data.load_company_profiles_from_db",
        lambda tickers: {
            "BIGCO": {
                "website": "https://big.example",
                "long_description": "Large peer company.",
            },
            "SMALLCO": {
                "website": "https://small.example",
                "long_description": "Small company about text.",
            },
        },
    )

    save_company_board(
        ticker="BIGCO",
        name="Big Co Ltd",
        market="NSE",
        seats=[
            {
                "din": "00009900",
                "name": "Swaminathan Sivaram",
                "designation": "Independent Director",
                "category": "Independent",
                "source": "test",
            }
        ],
        protect_din_board=False,
    )
    save_company_board(
        ticker="SMALLCO",
        name="Small Co Ltd",
        market="NSE",
        seats=[
            {
                "din": "00009900",
                "name": "Swaminathan Sivaram",
                "designation": "Independent Director",
                "category": "Independent",
                "source": "test",
            }
        ],
        protect_din_board=False,
    )

    rows = build_governance_map_rows(
        min_boards=2, hydrate_profiles=False, hydrate_mcaps=False
    )
    assert len(rows) == 1
    row = rows.iloc[0]
    assert bool(row["din_backed"]) is True
    assert bool(row["bridge"]) is True
    assert float(row["dir_score"]) > 0
    companies = row["companies"]
    assert {c["ticker"] for c in companies} == {"BIGCO", "SMALLCO"}
    assert any(c.get("sc") for c in companies)
    assert any(c.get("tv") for c in companies)
    assert any(c.get("about") for c in companies)
    by_ticker = {c["ticker"]: c for c in companies}
    assert by_ticker["BIGCO"]["cap_code"] == "MC"
    assert by_ticker["SMALLCO"]["cap_code"] == "MIC"

    from stocks.governance.html import build_governance_map_html

    html_out = build_governance_map_html(rows, standalone=False)
    assert "Dir Score" in html_out
    assert "Swaminathan" in html_out
    assert "govmap-body" in html_out
    assert "gov-cap-tag" in html_out
    assert "gov-cap-mc" in html_out or "gov-cap-mic" in html_out
    assert "govmap-cap-filter" in html_out
    assert 'data-cap="SC"' in html_out
    assert "govmap-hold-filter" in html_out
    assert 'data-hold="HOLD"' in html_out
    assert "capFilter" in html_out
    assert "holdFilter" in html_out
    assert "displayCompanies" in html_out
    assert "matchingCompanies" in html_out
    assert "filter-hit" in html_out
