"""Curated NSE boards — verified DINs from AGM / corporate governance filings.

Add companies sparingly. Prefer DIN + designation + disclosure date over volume.
One accurate board beats a hundred name-only Yahoo scans for bridge analysis.
"""

from __future__ import annotations

# Source: 20 Microns Limited AGM / board composition (Aug 2025).
# CIN L99999GJ1987PLC009768 · ISIN INE144J01027
CURATED_BOARDS: list[dict] = [
    {
        "ticker": "20MICRONS",
        "name": "20 Microns Limited",
        "cin": "L99999GJ1987PLC009768",
        "isin": "INE144J01027",
        "sector": "Basic Materials",
        "notes": "Board composition from AGM filings (Aug 2025).",
        "seats": [
            {
                "din": "00041610",
                "name": "Rajesh C. Parikh",
                "designation": "Chairman & Managing Director",
                "category": "Executive",
                "source": "agm_filing_2025-08",
                "as_of": "2025-08-08",
            },
            {
                "din": "00041712",
                "name": "Atil C. Parikh",
                "designation": "CEO & Managing Director",
                "category": "Executive",
                "source": "agm_filing_2025-08",
                "as_of": "2025-08-08",
            },
            {
                "din": "00140489",
                "name": "Sejal R. Parikh",
                "designation": "Whole-time Director",
                "category": "Executive",
                "source": "agm_filing_2025-08",
                "as_of": "2025-08-08",
            },
            {
                "din": "01676073",
                "name": "Ajay I. Ranka",
                "designation": "Independent Director",
                "category": "Independent",
                "source": "agm_filing_2025-08",
                "as_of": "2025-08-08",
            },
            {
                "din": "00323385",
                "name": "Jaideep B. Verma",
                "designation": "Independent Director",
                "category": "Independent",
                "source": "agm_filing_2025-08",
                "as_of": "2025-08-08",
            },
            {
                "din": "00009900",
                "name": "Swaminathan Sivaram",
                "designation": "Independent Director",
                "category": "Independent",
                "source": "agm_filing_2025-08",
                "as_of": "2025-08-08",
            },
            {
                "din": "08965826",
                "name": "Dukhabandhu Rath",
                "designation": "Independent Director",
                "category": "Independent",
                "source": "agm_filing_2025-08",
                "as_of": "2025-08-08",
            },
            {
                "din": "00010589",
                "name": "Premkumar Taneja",
                "designation": "Independent Director",
                "category": "Independent",
                "source": "agm_filing_2025-08",
                "as_of": "2025-08-08",
            },
        ],
    },
]
