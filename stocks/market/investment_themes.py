"""Investment theme tags for company profiles and Watching search.

Tags are regex-extracted from About Us / Yahoo copy and stored pipe-delimited in
``company_profile_cache.theme_tags``. Theme groups bundle tags for quick filters
in the Watching UI (Strategy → Watching).
"""

from __future__ import annotations

import re
from typing import Any

# (tag_key, regex pattern) — order preserved for stable pipe output.
BASE_THEME_PATTERNS: tuple[tuple[str, str], ...] = (
    ("copper", r"\bcopper\b"),
    ("aluminium", r"\balumin(?:ium|um)\b"),
    ("cobalt", r"\bcobalt\b"),
    ("nickel", r"\bnickel\b"),
    ("zinc", r"\bzinc\b"),
    ("steel", r"\bsteel\b"),
    ("cdmo", r"\bcdmo\b|contract\s+development\s+and\s+manufactur"),
    ("api", r"\bactive\s+pharmaceutical\b|\bapis?\b"),
    ("formulation", r"\bformulation\b"),
    ("pharma", r"\bpharma(?:ceutical)?\b"),
    ("biotech", r"\bbiotech(?:nology)?\b"),
    ("defence", r"\bdefen[cs]e\b|\baerospace\b"),
    ("ev", r"\belectric\s+vehicle|\bev\b|\bbattery\b"),
    ("renewable", r"\brenewable\b|\bsolar\b|\bwind\s+power\b"),
    ("semiconductor", r"\bsemiconductor\b|\bwafers?\b"),
    ("specialty_chem", r"\bspecialt[y]?\s+chem"),
    ("packaging", r"\bpackaging\b|\bfoil\b"),
    ("auto", r"\bautomotive\b|\boe\s*ms?\b|\bauto\s+component"),
    ("railways", r"\brailways?\b|\bvande\s+bharat\b"),
    ("infra", r"\binfrastructure\b|\bconstruction\b"),
    ("fmcg", r"\bfmcg\b|\bconsumer\s+(?:goods|durables)\b"),
    ("it_services", r"\bit\s+services\b|\bsoftware\s+services\b|\bdigital\s+transformation\b"),
)

# AI / data-center power infrastructure — high-voltage, transformers, switchgear, backup, cooling.
AI_INFRA_THEME_PATTERNS: tuple[tuple[str, str], ...] = (
    # Transmission & cable
    ("acsr", r"\bacsr\b|alumin(?:ium|um)\s+conductor\s+steel\s+reinfor"),
    ("aaac", r"\baaac\b|all\s+alumin(?:ium|um)\s+alloy\s+conductor"),
    ("opgw", r"\bopgw\b|optical\s+ground\s+wire"),
    ("ehv_cables", r"\bextra\s*high\s*voltage\b|\behv\b|\b765\s*kv\b|\b400\s*kv\b"),
    ("xlpe", r"\bxlpe\b|cross[\s-]linked\s+polyethylene"),
    # Transformer core & fluids
    ("transformer_oil", r"\btransformer\s+oil\b|\binsulating\s+oil\b|\bdielectric\s+fluid\b"),
    ("crgo_steel", r"\bcrgo\b|cold\s+rolled\s+grain\s+oriented"),
    ("amorphous_core", r"\bamorphous\s+core\b|\bamorphous\s+metal\b"),
    ("copper_windings", r"\bcopper\s+wind(?:ing|ings)\b|\benamelled\s+copper\b"),
    ("bushings", r"\bbushings?\b"),
    ("tap_changers", r"\btap\s+changers?\b|\bon[\s-]load\s+tap\b"),
    ("radiators", r"\btransformer\s+radiators?\b|\boil\s+radiators?\b"),
    ("ester_fluid", r"\bester\s+fluid\b|\bnatural\s+ester\b|\bsynthetic\s+ester\b"),
    # Switchgear & in-facility distribution
    ("switchgear", r"\bswitchgear\b|\bswitch\s+gear\b"),
    ("busducts", r"\bbus\s*ducts?\b|\bbusway\b"),
    ("busbars", r"\bbus\s*bars?\b|\bbusbars?\b"),
    ("vcb", r"\bvacuum\s+circuit\s+breaker\b|\bvcb\b"),
    ("gis", r"\bgas[\s-]insulated\s+switchgear\b|\bgis\s+substation\b"),
    ("ais", r"\bair[\s-]insulated\s+switchgear\b|\bais\s+substation\b"),
    ("sf6", r"\bsf6\b|sulfur\s+hexafluoride|sulphur\s+hexafluoride"),
    # Backup & storage
    ("industrial_ups", r"\bindustrial\s+ups\b|\buninterruptible\s+power\s+suppl"),
    ("flywheel", r"\bflywheel\s+(?:energy\s+)?storage\b"),
    ("lead_acid", r"\blead[\s-]acid\s+batter"),
    ("lifepo4", r"\blifepo4\b|lithium\s+iron\s+phosphate"),
    ("diesel_genset", r"\bdiesel\s+generators?\b|\bdg\s+sets?\b|\bgensets?\b"),
    ("bess", r"\bbess\b|battery\s+energy\s+storage"),
    # Data-center cooling
    ("liquid_cooling", r"\bliquid\s+cool(?:ing|ant)\b"),
    ("immersion_cooling", r"\bimmersion\s+cool(?:ing|ant)\b"),
    ("direct_to_chip", r"\bdirect[\s-]to[\s-]chip\b|\bd2c\s+cool"),
    ("chilled_water", r"\bchilled\s+water\b|\bchiller\s+plant\b"),
    ("crah", r"\bcrah\b|computer\s+room\s+air\s+handling"),
    ("crac", r"\bcrac\b|computer\s+room\s+air\s+condition"),
    ("heat_exchanger", r"\bheat\s+exchangers?\b|\bplate\s+heat\s+exchanger\b"),
    ("cdu", r"\bcoolant\s+distribution\s+unit\b|\bcdus?\b"),
    # Grid / power infra (broader)
    ("power_transmission", r"\bpower\s+transmission\b|\btransmission\s+line\b|\btransmission\s+&?\s*distribution\b"),
    ("smart_grid", r"\bsmart\s+grid\b|\bgrid\s+moderni[sz]ation\b"),
    ("data_center", r"\bdata\s+cent(?:er|re)s?\b|\bserver\s+farm\b|\bcolocation\b|\bcolocation\b"),
)

THEME_PATTERNS: tuple[tuple[str, str], ...] = BASE_THEME_PATTERNS + AI_INFRA_THEME_PATTERNS

_COMPILED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (tag, re.compile(pat, re.I)) for tag, pat in THEME_PATTERNS
)

# Quick-filter bundles for Watching UI (any tag in group matches).
THEME_GROUPS: dict[str, dict[str, Any]] = {
    "transmission": {
        "label": "Transmission",
        "tags": ("acsr", "aaac", "opgw", "ehv_cables", "xlpe", "copper", "aluminium", "power_transmission"),
        "search_hint": "acsr | copper | aluminium",
    },
    "transformers": {
        "label": "Transformers",
        "tags": (
            "transformer_oil",
            "crgo_steel",
            "amorphous_core",
            "copper_windings",
            "bushings",
            "tap_changers",
            "radiators",
            "ester_fluid",
        ),
        "search_hint": "transformer oil | crgo | copper windings",
    },
    "switchgear": {
        "label": "Switchgear",
        "tags": ("switchgear", "busducts", "busbars", "vcb", "gis", "ais", "sf6"),
        "search_hint": "switchgear | busbar | sf6",
    },
    "backup_power": {
        "label": "Backup",
        "tags": ("industrial_ups", "flywheel", "lead_acid", "lifepo4", "diesel_genset", "bess"),
        "search_hint": "ups | bess | diesel generator",
    },
    "cooling": {
        "label": "Cooling",
        "tags": (
            "liquid_cooling",
            "immersion_cooling",
            "direct_to_chip",
            "chilled_water",
            "crah",
            "crac",
            "heat_exchanger",
            "cdu",
        ),
        "search_hint": "liquid cooling | crah | heat exchanger",
    },
    "ai_infra": {
        "label": "AI Infra",
        "tags": tuple(tag for tag, _ in AI_INFRA_THEME_PATTERNS),
        "search_hint": "data center | transformer oil | switchgear",
    },
}

# Search-box aliases → strings matched in rowHay (tags use underscores; copy uses spaces).
SEARCH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "aluminium": ("aluminium", "aluminum"),
    "aluminum": ("aluminium", "aluminum"),
    "transformer_oil": ("transformer oil", "transformer_oil", "insulating oil"),
    "transformer oil": ("transformer oil", "transformer_oil", "insulating oil"),
    "crgo": ("crgo", "crgo_steel", "cold rolled grain oriented"),
    "acsr": ("acsr", "aluminum conductor steel reinforced", "aluminium conductor steel reinforced"),
    "sf6": ("sf6", "sulfur hexafluoride", "sulphur hexafluoride"),
    "ups": ("ups", "industrial ups", "uninterruptible power"),
    "bess": ("bess", "battery energy storage"),
    "dg": ("dg set", "diesel generator", "genset", "diesel_genset"),
    "data_center": ("data center", "data centre", "data_center", "colocation"),
    "data center": ("data center", "data centre", "data_center", "colocation"),
    "liquid_cooling": ("liquid cooling", "liquid_cooling"),
    "liquid cooling": ("liquid cooling", "liquid_cooling"),
    "switchgear": ("switchgear", "switch gear"),
    "busbar": ("busbar", "bus bar", "busbars"),
    "ehv": ("ehv", "extra high voltage", "ehv_cables"),
}


def theme_display_label(tag: str) -> str:
    """Human label for a stored tag key."""
    return tag.replace("_", " ").title()


def parse_theme_tags(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {t.strip().lower() for t in str(raw).split("|") if t.strip()}


def extract_theme_tags(*texts: str) -> str:
    blob = " ".join(str(t) for t in texts if t)
    if not blob:
        return ""
    tags: list[str] = []
    for tag, pat in _COMPILED_PATTERNS:
        if pat.search(blob):
            tags.append(tag)
    return "|".join(tags)


def merge_theme_tags(stored: str | None, *texts: str) -> str:
    """Union stored pipe tags with tags regex-extracted from profile copy."""
    have = parse_theme_tags(stored)
    have.update(parse_theme_tags(extract_theme_tags(*texts)))
    if not have:
        return ""
    ordered = [tag for tag, _ in THEME_PATTERNS if tag in have]
    return "|".join(ordered)


def theme_groups_for_ui() -> list[dict[str, Any]]:
    """Serialize theme groups for the Watching HTML toolbar."""
    out: list[dict[str, Any]] = []
    for key, spec in THEME_GROUPS.items():
        out.append(
            {
                "id": key,
                "label": spec["label"],
                "tags": list(spec["tags"]),
                "search_hint": spec.get("search_hint", ""),
            }
        )
    return out
