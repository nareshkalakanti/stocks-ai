"""Tests for investment theme tag extraction."""

from __future__ import annotations

from stocks.market.investment_themes import (
    extract_theme_tags,
    merge_theme_tags,
    parse_theme_tags,
    theme_groups_for_ui,
)


def test_ai_infra_transmission_tags():
    text = (
        "Manufacturer of ACSR conductors and aluminium alloy conductors for EHV "
        "transmission lines. Copper conductors for substations."
    )
    tags = extract_theme_tags(text)
    assert "acsr" in tags
    assert "copper" in tags
    assert "aluminium" in tags
    assert "ehv_cables" in tags or "power_transmission" in tags


def test_transformer_oil_and_crgo():
    text = (
        "Oil-immersed power transformers using CRGO steel laminations and "
        "transformer oil for insulation. Enamelled copper windings."
    )
    tags = extract_theme_tags(text)
    assert "transformer_oil" in tags
    assert "crgo_steel" in tags
    assert "copper_windings" in tags


def test_switchgear_and_cooling_tags():
    text = (
        "Medium voltage switchgear, busbars, and SF6 gas-insulated substations. "
        "Liquid cooling and CRAH units for data center facilities."
    )
    tags = extract_theme_tags(text)
    assert "switchgear" in tags
    assert "busbars" in tags
    assert "sf6" in tags
    assert "liquid_cooling" in tags
    assert "crah" in tags
    assert "data_center" in tags


def test_parse_theme_tags():
    assert parse_theme_tags("copper|transformer_oil|") == {"copper", "transformer_oil"}


def test_merge_theme_tags():
    about = "Manufacturer of ACSR conductors and transformer oil for utilities."
    merged = merge_theme_tags("packaging", about)
    tags = parse_theme_tags(merged)
    assert "packaging" in tags
    assert "acsr" in tags
    assert "transformer_oil" in tags


def test_theme_groups_for_ui():
    groups = theme_groups_for_ui()
    ids = {g["id"] for g in groups}
    assert "transmission" in ids
    assert "ai_infra" in ids
    tx = next(g for g in groups if g["id"] == "transmission")
    assert "acsr" in tx["tags"]
