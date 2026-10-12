"""The whole synthetic dataset for one seed, and how it is written to a folder."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from synthetic_tickets.articles import SOLVED, documents, questions
from synthetic_tickets.catalog import PROBLEMS
from synthetic_tickets.tickets import Ticket, build_ticket

TICKETS_FILE = "tickets.jsonl"
ANSWER_KEY_FILE = "gabarito.json"
QUESTIONS_FILE = "perguntas.json"


@dataclass(frozen=True)
class Dataset:
    seed: int
    tickets: list[Ticket]
    answer_key: dict[str, object]
    documents: dict[str, str]
    questions: list[dict[str, object]]


def generate(seed: int, count: int) -> Dataset:
    """``count`` tickets for ``seed``: the same arguments always give the same dataset."""
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not security
    tickets: list[Ticket] = []
    keys: list[dict[str, object]] = []
    solved: dict[str, list[str]] = {}
    for index in range(1, count + 1):
        problem = rng.choice(PROBLEMS)
        ticket, key = build_ticket(rng, seed, index, problem)
        tickets.append(ticket)
        keys.append(key.as_json())
        if ticket["status"] in SOLVED:
            solved.setdefault(problem.slug, []).append(key.external_id)
    answer_key: dict[str, object] = {"versao": 1, "semente": seed, "chamados": keys}
    return Dataset(seed, tickets, answer_key, documents(), questions(solved))


def ticket_line(ticket: Ticket) -> str:
    """One JSONL line: compact, UTF-8 as is (no ``\\u`` escapes)."""
    return json.dumps(ticket, ensure_ascii=False, separators=(",", ":"))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write(dataset: Dataset, out: Path) -> None:
    """Writes ``tickets.jsonl``, ``gabarito.json``, ``perguntas.json`` and ``docs/*.md``."""
    _write(out / TICKETS_FILE, "".join(f"{ticket_line(t)}\n" for t in dataset.tickets))
    _write(out / ANSWER_KEY_FILE, _pretty(dataset.answer_key))
    _write(out / QUESTIONS_FILE, _pretty(dataset.questions))
    for relative, text in dataset.documents.items():
        _write(out / relative, text)


def _pretty(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
