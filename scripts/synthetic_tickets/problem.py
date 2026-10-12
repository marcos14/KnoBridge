"""A recurring problem of the fictitious ERP: what customers write, how support solves it."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Problem:
    """One problem with its known solution, the help article about it and two questions.

    ``titles`` and ``complaints`` are variants the generator picks from, so tickets of the same
    problem read differently. ``steps`` feed both the agent's reply and the article. The questions
    paraphrase the problem without copying the title, for the embedding comparison.
    """

    slug: str
    product: str
    category: str
    tags: tuple[str, ...]
    titles: tuple[str, ...]
    complaints: tuple[str, ...]
    symptom: str
    cause: str
    steps: tuple[str, ...]
    solution: str
    questions: tuple[str, str]
