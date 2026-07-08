"""Stock narrative notes for expand panels."""

from __future__ import annotations

from stocks.core.config import STOCK_NOTES_PATH
from stocks.shared.stock_notes import (
    attach_stock_notes,
    load_stock_notes_file,
    sync_stock_notes_from_file,
)


def test_load_stock_notes_file_gna_fiem():
    notes = load_stock_notes_file(STOCK_NOTES_PATH)
    assert "GNA" in notes
    assert "FIEM" in notes
    assert "6.7 million" in notes["GNA"]["business"]
    assert len(notes["GNA"]["triggers"]) >= 2


def test_sync_and_attach():
    n = sync_stock_notes_from_file(STOCK_NOTES_PATH)
    assert n >= 2
    import pandas as pd

    df = pd.DataFrame([{"ticker": "GNA", "name": "GNA Axles"}])
    out = attach_stock_notes(df, sync_file=False)
    note = out.iloc[0]["stock_note"]
    assert isinstance(note, dict)
    assert note.get("business")
