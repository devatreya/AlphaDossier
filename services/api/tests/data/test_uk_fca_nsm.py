from __future__ import annotations

from services.api.data import uk_fca_nsm


async def test_search_returns_empty() -> None:
    docs = await uk_fca_nsm.search_nsm("SHEL.L", company_name="Shell plc")
    assert docs == []


def test_coverage_note() -> None:
    note = uk_fca_nsm.coverage_note()
    assert note["data_quality"] == "unavailable"
    assert "FCA NSM" in note["reason"]
