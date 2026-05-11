from __future__ import annotations

import pytest

from services.api.agents import _prompts


def test_load_prompt_reads_news_md() -> None:
    text = _prompts.load_prompt("news")
    assert "ticker" in text.lower()
    assert "{ticker}" in text  # placeholder still raw before render
    assert "{context}" in text


def test_render_prompt_substitutes_vars() -> None:
    out = _prompts.render_prompt("news", ticker="NVDA", context="C1: hello")
    assert "NVDA" in out
    assert "C1: hello" in out
    assert "{ticker}" not in out


def test_load_unknown_prompt_raises() -> None:
    with pytest.raises(_prompts.PromptNotFound):
        _prompts.load_prompt("does_not_exist_xyz")


def test_load_prompt_rejects_path_traversal() -> None:
    with pytest.raises(ValueError):
        _prompts.load_prompt("../etc/passwd")
    with pytest.raises(ValueError):
        _prompts.load_prompt("a/b")
