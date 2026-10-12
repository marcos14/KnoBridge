"""Command line: ``uv run python -m synthetic_tickets --seed N --tickets 300 --out <pasta>``.

Writes the dataset outside the repository (rule 9 keeps only a small example in the E2E
fixtures). Exit code 0 on success, 2 on bad input.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from synthetic_tickets.generate import generate, write

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAX_TICKETS = 100_000


def _positive(text: str) -> int:
    value = int(text)
    if not 1 <= value <= MAX_TICKETS:
        raise argparse.ArgumentTypeError(f"use 1 to {MAX_TICKETS}")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synthetic_tickets",
        description="Gera chamados sintéticos em pt-BR, o gabarito da anonimização, "
        "artigos de ajuda e perguntas.",
    )
    parser.add_argument("--seed", type=int, default=1, help="semente (padrão 1)")
    parser.add_argument("--tickets", type=_positive, default=300, help="quantos chamados")
    parser.add_argument("--out", type=Path, required=True, help="pasta de saída, fora do repo")
    return parser


def main(argv: list[str] | None = None, *, repo_root: Path = REPO_ROOT) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    out: Path = args.out.resolve()
    if out.is_relative_to(repo_root.resolve()):
        print(f"erro: {out} fica dentro do repositório; gere fora dele.")
        return 2
    dataset = generate(args.seed, args.tickets)
    write(dataset, out)
    print(
        f"{len(dataset.tickets)} chamados, {len(dataset.documents)} artigos e "
        f"{len(dataset.questions)} perguntas em {out.as_posix()}"
    )
    return 0
