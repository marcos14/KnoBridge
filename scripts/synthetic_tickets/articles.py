"""Help articles of the fictitious ERP and the questions that compare embedding models (F6.3).

One short Markdown article per problem (``docs/<slug>.md``) and one overview per product
(``docs/visao-geral-<produto>.md``, a distractor that mentions every problem of the product
without solving any). Each problem has two questions, each with the article that answers it and
the solved tickets (resolved or closed) of the same problem.
"""

from __future__ import annotations

from collections.abc import Iterable

from synthetic_tickets.catalog import ERP_NAME, PROBLEMS
from synthetic_tickets.people import kebab
from synthetic_tickets.problem import Problem

SOLVED = frozenset({"resolved", "closed"})


def article_path(problem: Problem) -> str:
    return f"docs/{problem.slug}.md"


def article(problem: Problem) -> str:
    steps = "\n".join(f"{n}. {step}" for n, step in enumerate(problem.steps, 1))
    return (
        f"# {problem.titles[0]}\n\n"
        f"Produto: {ERP_NAME}, módulo {problem.product}. Categoria: {problem.category}.\n\n"
        f"## Sintoma\n\n{problem.symptom}\n\n"
        f"## Causa\n\n{problem.cause}\n\n"
        f"## Como resolver\n\n{steps}\n"
    )


def overview(product: str, problems: Iterable[Problem]) -> str:
    items = "\n".join(f"- {problem.titles[0]}" for problem in problems)
    return (
        f"# Visão geral: {product}\n\n"
        f"O módulo {product} do {ERP_NAME} reúne as rotinas do dia a dia da área. "
        "Os assuntos mais procurados no suporte são:\n\n"
        f"{items}\n\n"
        "Cada assunto tem um artigo próprio com o sintoma, a causa e o passo a passo.\n"
    )


def documents() -> dict[str, str]:
    """Every article by path, in a stable order: the problems, then the product overviews."""
    docs = {article_path(problem): article(problem) for problem in PROBLEMS}
    products = dict.fromkeys(problem.product for problem in PROBLEMS)
    for product in products:
        same = [problem for problem in PROBLEMS if problem.product == product]
        docs[f"docs/visao-geral-{kebab(product)}.md"] = overview(product, same)
    return docs


def questions(solved_by_problem: dict[str, list[str]]) -> list[dict[str, object]]:
    """Two questions per problem, with the expected article and solved tickets."""
    return [
        {
            "id": f"{problem.slug}-{number}",
            "pergunta": text,
            "problema": problem.slug,
            "documento_esperado": article_path(problem),
            "chamados_esperados": solved_by_problem.get(problem.slug, []),
        }
        for problem in PROBLEMS
        for number, text in enumerate(problem.questions, 1)
    ]
