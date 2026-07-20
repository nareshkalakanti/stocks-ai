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


def test_seed_default_business_groups_from_repo_file():
    init_db()
    clear_all_business_groups()
    assert business_groups_count() == 0

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


def test_ensure_business_groups_reseeds_when_under_populated():
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

    count = ensure_business_groups(seed_if_empty=True)
    assert count >= 133
    assert business_group_members_count() >= 400
    assert business_groups_playlist_count(seed_if_empty=False) >= 400
