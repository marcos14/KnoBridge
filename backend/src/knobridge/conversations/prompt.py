"""Build what the LLM receives for one turn: instructions, numbered sources, history, question.

Pure functions (no IO), so the prompt is tested without a database or a provider. The
sources are numbered from 1 in the order the retriever returned them; the answer cites them
as ``[n]`` and the same numbers are stored in ``Message.citations``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from knobridge.assistants.models import AssistantTone
from knobridge.conversations.models import MessageRole
from knobridge.conversations.retrieval import Source
from knobridge.llm.provider import ChatMessage, ChatRole

TITLE_LENGTH = 80
_ELLIPSIS = "…"

_TONES = {
    AssistantTone.NEUTRAL: "Use a neutral, objective tone.",
    AssistantTone.FORMAL: "Use a formal, professional tone.",
    AssistantTone.FRIENDLY: "Use a friendly, approachable tone.",
}


@dataclass(frozen=True)
class AssistantProfile:
    """The assistant settings that shape the prompt."""

    system_prompt: str
    language: str
    tone: AssistantTone
    no_source_message: str


@dataclass(frozen=True)
class HistoryItem:
    role: MessageRole
    content: str


def instructions(profile: AssistantProfile) -> str:
    """The fixed rules of every answer, after the assistant's own system prompt."""
    rules = (
        "Answer only with information from the numbered sources below. Cite every statement "
        "with the number of its source in square brackets, like [1] or [2][3]. "
        f"Answer in the language {profile.language}. {_TONES[profile.tone]} "
        "If the sources do not contain the answer, reply exactly with this message and "
        f"nothing else: {profile.no_source_message}"
    )
    return "\n\n".join(part for part in (profile.system_prompt.strip(), rules) if part)


def numbered_sources(sources: Sequence[Source]) -> str:
    blocks: list[str] = []
    for index, source in enumerate(sources, start=1):
        header = f"[{index}] {source.title}"
        if source.uri:
            header += f" ({source.uri})"
        blocks.append(f"{header}\n{source.content}")
    return "Sources:\n\n" + "\n\n".join(blocks)


def build_messages(
    profile: AssistantProfile,
    sources: Sequence[Source],
    history: Sequence[HistoryItem],
    question: str,
) -> list[ChatMessage]:
    """System instructions, the sources, the history window (oldest first), the question."""
    messages = [
        ChatMessage(ChatRole.SYSTEM, instructions(profile)),
        ChatMessage(ChatRole.SYSTEM, numbered_sources(sources)),
    ]
    messages.extend(
        ChatMessage(
            ChatRole.USER if item.role is MessageRole.USER else ChatRole.ASSISTANT, item.content
        )
        for item in history
    )
    messages.append(ChatMessage(ChatRole.USER, question))
    return messages


def title_from_question(question: str) -> str:
    """The conversation title: the first question on one line, cut at a word boundary."""
    line = " ".join(question.split())
    if len(line) <= TITLE_LENGTH:
        return line
    cut = line[: TITLE_LENGTH - len(_ELLIPSIS)]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() + _ELLIPSIS
