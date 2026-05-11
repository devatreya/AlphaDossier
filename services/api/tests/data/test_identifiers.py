from __future__ import annotations

import pytest

from services.api.data import identifiers


def test_us_equity() -> None:
    inst = identifiers.resolve("nvda")
    assert inst.ticker == "NVDA"
    assert inst.region == "US"
    assert inst.asset_class == "equity"


def test_uk_equity() -> None:
    inst = identifiers.resolve("SHEL.L")
    assert inst.region == "UK"
    assert inst.asset_class == "equity"


def test_us_etf() -> None:
    inst = identifiers.resolve("TLT")
    assert inst.region == "US"
    assert inst.asset_class == "etf"


def test_us_index() -> None:
    inst = identifiers.resolve("^GSPC")
    assert inst.region == "US"
    assert inst.asset_class == "index"


def test_uk_index() -> None:
    inst = identifiers.resolve("^FTSE")
    assert inst.region == "UK"
    assert inst.asset_class == "index"


def test_strip_uk_suffix() -> None:
    assert identifiers.stripped_symbol("SHEL.L") == "SHEL"
    assert identifiers.stripped_symbol("AZN.L") == "AZN"


def test_strip_us_passthrough() -> None:
    assert identifiers.stripped_symbol("NVDA") == "NVDA"


def test_strip_index_caret() -> None:
    assert identifiers.stripped_symbol("^GSPC") == "GSPC"


def test_invalid_ticker() -> None:
    with pytest.raises(ValueError):
        identifiers.resolve("not a ticker!")
