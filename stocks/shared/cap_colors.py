"""Shared NC / MIC / SC / MC / LC cap band colors — badges & filter chips app-wide."""

from __future__ import annotations

from stocks.governance.score import CAP_CODE_BANDS

CAP_CODES: tuple[str, ...] = tuple(band[2] for band in CAP_CODE_BANDS)

# Distinct bg / fg / border per tier (used everywhere cap labels appear).
CAP_PALETTE: dict[str, dict[str, str]] = {
    "NC": {"bg": "#e5e7eb", "fg": "#374151", "border": "#9ca3af"},
    "MIC": {"bg": "#ffedd5", "fg": "#c2410c", "border": "#fdba74"},
    "SC": {"bg": "#fef9c3", "fg": "#a16207", "border": "#fcd34d"},
    "MC": {"bg": "#dbeafe", "fg": "#1d4ed8", "border": "#93c5fd"},
    "LC": {"bg": "#d1fae5", "fg": "#047857", "border": "#6ee7b7"},
}


def cap_css_class(code: str) -> str:
    c = str(code or "").strip().upper()
    return f"cap-{c.lower()}" if c in CAP_PALETTE else ""


def cap_colors_css(*, include_chip: bool = True, include_gov_filter: bool = True) -> str:
    """CSS for .cap-badge / .cap-chip and optional gov-map filter buttons."""
    badge_rules = [
        f"  .cap-{code.lower()} {{ background: {c['bg']}; color: {c['fg']}; "
        f"border-color: {c['border']}; }}"
        for code, c in CAP_PALETTE.items()
    ]
    parts = [
        "<style>",
        "  /* Cap band palette — NC MIC SC MC LC */",
        "  .cap-badge {",
        "    display: inline-block;",
        "    font-size: 10px;",
        "    font-weight: 700;",
        "    letter-spacing: 0.04em;",
        "    padding: 1px 6px;",
        "    border-radius: 4px;",
        "    line-height: 1.4;",
        "    border: 1px solid transparent;",
        "  }",
        *badge_rules,
    ]
    if include_chip:
        chip_idle = [
            f'  .cap-chip[data-cap="{code}"] {{ color: {c["fg"]}; border-color: {c["border"]}; }}'
            for code, c in CAP_PALETTE.items()
        ]
        chip_active = [
            f'  .cap-chip[data-cap="{code}"].active, .cap-chip[data-cap="{code}"]:hover {{ '
            f'background: {c["bg"]}; color: {c["fg"]}; border-color: {c["border"]}; }}'
            for code, c in CAP_PALETTE.items()
        ]
        parts.extend(
            [
                "  .cap-chip {",
                "    border: 1px solid #d1d5db;",
                "    background: #fff;",
                "    border-radius: 999px;",
                "    padding: 4px 10px;",
                "    font-size: 12px;",
                "    font-weight: 700;",
                "    cursor: pointer;",
                "    line-height: 1.3;",
                "  }",
                '  .cap-chip[data-cap=""].active, .cap-chip[data-cap=""]:hover {',
                "    background: #f3f4f6; color: #374151; border-color: #d1d5db;",
                "  }",
                *chip_idle,
                *chip_active,
            ]
        )
    if include_gov_filter:
        gov_active = [
            f'  .gov-cap-filter button[data-cap="{code}"].active {{ '
            f'background: {c["bg"]}; color: {c["fg"]}; }}'
            for code, c in CAP_PALETTE.items()
        ]
        parts.extend(
            [
                '  .gov-cap-filter button[data-cap=""].active { background: #f3f4f6; color: #374151; }',
                *gov_active,
            ]
        )
    parts.append("</style>")
    return "\n".join(parts)


CAP_FMT_JS = """
  function fmtCapCode(v, r) {
    const code = String(v || "").toUpperCase();
    if (!code || code === "—") return "—";
    const tip = esc(r && r.cap_label ? r.cap_label : code);
    return `<span class="cap-badge cap-${code.toLowerCase()}" title="${tip}">${esc(code)}</span>`;
  }
"""
