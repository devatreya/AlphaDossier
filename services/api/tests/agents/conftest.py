"""Helpers for agent tests: minimal Anthropic SDK fakes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class FakeContentBlock:
    type: str
    name: str | None = None
    input: dict[str, Any] | None = None
    text: str | None = None


@dataclass
class FakeMessage:
    content: list[FakeContentBlock]
    model: str = "claude-sonnet-4-6"
    stop_reason: str = "tool_use"
    usage: FakeUsage = field(default_factory=FakeUsage)


@dataclass
class _FakeMessages:
    response: FakeMessage
    last_kwargs: dict[str, Any] = field(default_factory=dict)

    async def create(self, **kwargs: Any) -> FakeMessage:
        self.last_kwargs = kwargs
        return self.response


@dataclass
class FakeAnthropic:
    messages: _FakeMessages

    @classmethod
    def with_tool_use(
        cls,
        tool_input: dict[str, Any],
        *,
        model: str = "claude-sonnet-4-6",
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> "FakeAnthropic":
        msg = FakeMessage(
            content=[
                FakeContentBlock(type="tool_use", name="submit_analysis", input=tool_input)
            ],
            model=model,
            usage=FakeUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        )
        return cls(messages=_FakeMessages(response=msg))

    @classmethod
    def with_text(
        cls,
        text: str,
        *,
        model: str = "claude-sonnet-4-6",
    ) -> "FakeAnthropic":
        msg = FakeMessage(
            content=[FakeContentBlock(type="text", text=text)],
            model=model,
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=10, output_tokens=20),
        )
        return cls(messages=_FakeMessages(response=msg))
