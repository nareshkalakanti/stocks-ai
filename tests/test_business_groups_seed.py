"""Business group seed file loads on empty SQLite."""

from __future__ import annotations

import json

from stocks.core.database import (
    business_group_members_count,
    business_groups_count,
    clear_all_business_groups,
    init_db,
    save_business_group,
)
from stocks.shared.business_groups import ensure_business_groups, seed_default_business_groups
from stocks.scans.business_groups_playlist import business_groups_playlist_count


def test_seed_default_business_groups_from_optional_file(tmp_path, monkeypatch):
    init_db()
    clear_all_business_groups()
    assert business_groups_count() == 0

    seed_path = tmp_path / "business_groups_seed.json"
    seed_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "SEED GROUP",
                        "token": "SEEDCO",
                        "members": [
                            {"ticker": "SEEDCO", "market": "NSE", "name": "Seed Co"},
                            {"ticker": "SEEDSPN", "market": "NSE", "name": "Seed Spin"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "stocks.shared.business_groups._BUSINESS_GROUPS_SEED_PATH", seed_path
    )
    count = seed_default_business_groups()
    assert count > 0
    assert business_groups_playlist_count(seed_if_empty=False) > 0


def test_seed_default_business_groups_skips_when_populated(tmp_path, monkeypatch):
    init_db()
    seed_path = tmp_path / "business_groups_seed.json"
    seed_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "TEST GROUP",
                        "token": "TESTCO",
                        "members": [
                            {"ticker": "TESTCO", "market": "NSE", "name": "Test Co"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "stocks.shared.business_groups._BUSINESS_GROUPS_SEED_PATH",
        seed_path,
    )

    clear_all_business_groups()
    first = seed_default_business_groups()
    assert first == 1
    second = seed_default_business_groups()
    assert second == 1
    assert business_groups_count() == 1


def test_ensure_business_groups_reseeds_when_under_populated(tmp_path, monkeypatch):
    init_db()
    clear_all_business_groups()
    save_business_group(
        "Partial Group",
        [
            {"ticker": "AAA", "market": "NSE", "name": "AAA Ltd"},
            {"ticker": "BBB", "market": "NSE", "name": "BBB Ltd"},
        ],
        token="AAA",
    )
    assert business_groups_count() == 1
    assert business_group_members_count() == 2

    # Without a seed file, keep the thin DB (committed stocks_ai.db is source of truth).
    monkeypatch.setattr(
        "stocks.shared.business_groups._BUSINESS_GROUPS_SEED_PATH",
        tmp_path / "missing.json",
    )
    assert ensure_business_groups(seed_if_empty=True) == 1

    seed_path = tmp_path / "business_groups_seed.json"
    seed_path.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "name": "FULL GROUP",
                        "token": "FULLCO",
                        "members": [
                            {"ticker": "FULLCO", "market": "NSE", "name": "Full"},
                            {"ticker": "FULLSPN", "market": "NSE", "name": "Spin"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "stocks.shared.business_groups._BUSINESS_GROUPS_SEED_PATH", seed_path
    )
    monkeypatch.setattr(
        "stocks.shared.business_groups._MIN_SEEDED_BUSINESS_GROUP_MEMBERS", 10
    )
    count = ensure_business_groups(seed_if_empty=True)
    assert count >= 1
    assert business_group_members_count() >= 2
