"""Prompt template loader.

Prompts live as markdown files at the repo root under prompts/. Load them by
short name (e.g. 'news' loads prompts/news.md). Variables use Python str.format
syntax — escape literal braces in the prompt as `{{` / `}}`.
"""
from __future__ import annotations

from pathlib import Path

# services/api/agents/_prompts.py -> repo root is parents[3]
PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


class PromptNotFound(FileNotFoundError):
    pass


def load_prompt(name: str) -> str:
    """Read prompts/{name}.md. Raises PromptNotFound if missing."""
    if "/" in name or ".." in name:
        raise ValueError(f"prompt name must be a bare slug, got {name!r}")
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise PromptNotFound(f"prompt {name!r} not found at {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, **variables: object) -> str:
    """Load prompts/{name}.md and substitute {var} placeholders."""
    return load_prompt(name).format(**variables)
