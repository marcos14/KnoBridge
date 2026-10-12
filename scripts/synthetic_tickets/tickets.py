"""One synthetic ticket in the KnoBridge format (docs/specs/chamados.md) and its answer key."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from synthetic_tickets import people
from synthetic_tickets.answer_key import AnswerKey
from synthetic_tickets.catalog import (
    FIRST_DAY,
    ORIGINAL_STATUS,
    PRIORITIES,
    SPAN_DAYS,
    STATUS_WEIGHTS,
    SUPPORT_DOMAIN,
    TICKET_URL,
)
from synthetic_tickets.people import Person
from synthetic_tickets.problem import Problem

Ticket = dict[str, object]
Message = dict[str, object]

GREETINGS = ("Bom dia.", "Boa tarde.", "Olá, equipe de suporte.", "Oi, tudo bem?")
# Sentences a customer adds with a personal datum; {value} is the datum.
CUSTOMER_PERSONAL = {
    "email": "Se precisar, me responda em {value}.",
    "telefone": "Meu telefone para contato é {value}.",
    "cpf": "O CPF do titular do cadastro é {value}.",
    "cnpj": "O CNPJ da loja é {value}.",
    "cartao": "O cartão da empresa cadastrado para a mensalidade é {value}.",
    "ip": "O servidor do sistema fica no IP {value}.",
}
NOTE_PERSONAL = {
    "cpf": "CPF conferido no cadastro: {value}.",
    "cnpj": "CNPJ da empresa: {value}.",
    "telefone": "Retornar no telefone {value}.",
}
WAITING = (
    "para analisar, preciso de um print da tela e do horário em que o erro aconteceu.",
    "pode confirmar se o problema acontece em todos os computadores da loja?",
)
THANKS = ("Funcionou, obrigado!", "Deu certo aqui, pode encerrar.", "Resolvido, muito obrigada.")


@dataclass(frozen=True)
class Cast:
    """Who appears in a ticket. First names never repeat, so each has one marker."""

    requester: Person
    organization: str
    agents: tuple[Person, ...]
    colleague: Person | None
    third_party: Person | None


def _pick_status(rng: random.Random) -> str:
    return rng.choices(list(STATUS_WEIGHTS), weights=list(STATUS_WEIGHTS.values()))[0]


def _cast(rng: random.Random) -> Cast:
    taken: set[str] = set()
    requester = people.person(rng, people.CUSTOMER_FIRST_NAMES, taken)
    agents = [people.person(rng, people.AGENT_FIRST_NAMES, taken)]
    if rng.random() < 0.2:
        agents.append(people.person(rng, people.AGENT_FIRST_NAMES, taken))
    colleague = (
        people.person(rng, people.CUSTOMER_FIRST_NAMES, taken) if rng.random() < 0.15 else None
    )
    third = (
        people.person(rng, people.THIRD_PARTY_FIRST_NAMES, taken) if rng.random() < 0.1 else None
    )
    return Cast(requester, rng.choice(people.ORGANIZATIONS), tuple(agents), colleague, third)


def _lower_first(sentence: str) -> str:
    """Lowercases only the first letter, so acronyms (NCM, CNAB, A1) stay as they are."""
    return sentence[:1].lower() + sentence[1:]


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


class _Builder:
    """Writes the messages of one ticket in order, recording every seeded datum in the key."""

    def __init__(self, rng: random.Random, problem: Problem, cast: Cast, key: AnswerKey) -> None:
        self.rng = rng
        self.problem = problem
        self.cast = cast
        self.key = key
        self.messages: list[Message] = []
        self.clock = FIRST_DAY + timedelta(minutes=rng.randrange(SPAN_DAYS * 24 * 60))
        self.created_at = self.clock

    @property
    def where(self) -> str:
        return f"messages[{len(self.messages)}].body"

    def tick(self, low_minutes: int, high_minutes: int) -> datetime:
        self.clock += timedelta(minutes=self.rng.randint(low_minutes, high_minutes))
        return self.clock

    def agent_marker(self, agent: Person) -> str:
        return f"[ATENDENTE_{self.cast.agents.index(agent) + 1}]"

    def requester_first(self, *, internal: bool = False) -> str:
        first = self.cast.requester.first
        return self.key.name("primeiro_nome", first, "[SOLICITANTE]", self.where, internal=internal)

    def add(
        self, role: str, author: str | None, body: str, *, public: bool = True, fmt: str = "text"
    ) -> None:
        message: Message = {"role": role, "author_name": author, "body": body}
        if not public:
            message["public"] = False
        if fmt != "text":
            message["body_format"] = fmt
        message["created_at"] = _stamp(self.clock)
        self.messages.append(message)

    def opening(self) -> None:
        rng, key, cast, where = self.rng, self.key, self.cast, self.where
        parts = [rng.choice(GREETINGS), rng.choice(self.problem.complaints)]
        if rng.random() < 0.4:
            parts.append(f"Estamos na versão {key.keep('versao', people.version(rng), where)}.")
        if cast.third_party is not None:
            name = key.undetectable("nome_nao_declarado", cast.third_party.full, where)
            parts.append(f"O contador {name} precisa do relatório até sexta.")
        kinds = rng.sample(sorted(CUSTOMER_PERSONAL), k=rng.choice((0, 1, 1, 2, 3)))
        for kind in kinds:
            value = self._personal_value(kind)
            parts.append(CUSTOMER_PERSONAL[kind].format(value=key.personal(kind, value, where)))
        if rng.random() < 0.5:
            name = key.name("nome", cast.requester.full, "[SOLICITANTE]", where)
            organization = key.name("organizacao", cast.organization, "[ORGANIZACAO]", where)
            parts.append(f"Att., {name} ({organization})")
        else:
            parts.append(f"Obrigada, {self.requester_first()}.")
        self.add("customer", cast.requester.full, " ".join(parts))

    def _personal_value(self, kind: str) -> str:
        rng = self.rng
        if kind == "email":
            return people.email_for(self.cast.requester, self.cast.organization)
        if kind == "telefone":
            return people.phone(rng)
        if kind == "cpf":
            return people.cpf(rng, formatted=rng.random() < 0.7)
        if kind == "cnpj":
            return people.cnpj(rng, formatted=rng.random() < 0.7)
        if kind == "cartao":
            return people.card(rng)
        return people.ipv4(rng)

    def assignment(self) -> None:
        agent = self.cast.agents[0]
        self.tick(5, 90)
        name = self.key.name("nome", agent.full, self.agent_marker(agent), self.where)
        self.add(
            "system", "Automação", f"Status alterado para Em atendimento. Responsável: {name}."
        )

    def internal_note(self) -> None:
        agent = self.rng.choice(self.cast.agents)
        self.tick(10, 240)
        parts = [f"Problema conhecido: {_lower_first(self.problem.cause)}"]
        for kind in self.rng.sample(sorted(NOTE_PERSONAL), k=self.rng.randint(1, 2)):
            value = self._personal_value(kind)
            recorded = self.key.personal(kind, value, self.where, internal=True)
            parts.append(NOTE_PERSONAL[kind].format(value=recorded))
        self.add("agent", agent.full, " ".join(parts), public=False)

    def waiting(self) -> None:
        agent = self.cast.agents[0]
        self.tick(30, 600)
        body = f"Olá {self.requester_first()}, {self.rng.choice(WAITING)}"
        self.add("agent", agent.full, body)

    def answer(self) -> None:
        agent = self.cast.agents[0]
        self.tick(30, 1440)
        first = self.requester_first()
        signature = self.key.name(
            "primeiro_nome", agent.first, self.agent_marker(agent), self.where
        )
        intro = f"o caso é conhecido: {_lower_first(self.problem.cause)} Siga estes passos:"
        if self.rng.random() < 0.35:
            items = "".join(f"<li>{step}</li>" for step in self.problem.steps)
            body = (
                f"<p>Olá {first},</p><p>{intro}</p><ol>{items}</ol>"
                f"<p>Att.,<br><b>{signature}</b></p>"
            )
            self.add("agent", agent.full, body, fmt="html")
            return
        steps = "\n".join(f"{n}. {step}" for n, step in enumerate(self.problem.steps, 1))
        self.add("agent", agent.full, f"Olá {first}, {intro}\n\n{steps}\n\nAtt., {signature}")

    def thanks(self) -> None:
        self.tick(20, 2880)
        colleague = self.cast.colleague
        if colleague is None:
            self.add("customer", self.cast.requester.full, self.rng.choice(THANKS))
            return
        first = self.key.name("primeiro_nome", colleague.first, "[CLIENTE_1]", self.where)
        self.add(
            "customer", colleague.full, f"Aqui é {first}, do financeiro. Testamos e deu certo."
        )


def build_ticket(
    rng: random.Random, seed: int, index: int, problem: Problem
) -> tuple[Ticket, AnswerKey]:
    """Ticket number ``index`` (1-based) of ``problem``; same arguments, same ticket."""
    external_id = f"VTX-{seed}-{index:05d}"
    number = str(40000 + index)
    status = _pick_status(rng)
    cast = _cast(rng)
    key = AnswerKey(external_id)
    builder = _Builder(rng, problem, cast, key)

    builder.opening()
    if rng.random() < 0.4:
        builder.assignment()
    if rng.random() < 0.35:
        builder.internal_note()
    resolved_at: datetime | None = None
    resolution: dict[str, str] | None = None
    if status == "pending":
        builder.waiting()
    elif status in ("resolved", "closed"):
        builder.answer()
        resolved_at = builder.tick(1, 30)
        resolution = {"body": problem.solution}
        if cast.colleague is not None or rng.random() < 0.5:
            builder.thanks()
    updated_at = builder.tick(1, 60)

    agents = [
        {"name": agent.full, "email": f"{people.slug(agent.first)}@{SUPPORT_DOMAIN}"}
        for agent in cast.agents
    ]
    ticket: Ticket = {
        "external_id": external_id,
        "number": number,
        "title": rng.choice(problem.titles),
        "status": status,
        "original_status": rng.choice(ORIGINAL_STATUS[status]),
        "priority": rng.choice(PRIORITIES),
        "category": problem.category,
        "product": problem.product,
        "tags": list(problem.tags),
        "url": TICKET_URL.format(number=number),
        "created_at": _stamp(builder.created_at),
        "updated_at": _stamp(updated_at),
        "resolved_at": None if resolved_at is None else _stamp(resolved_at),
        "requester": {
            "name": cast.requester.full,
            "email": people.email_for(cast.requester, cast.organization),
            "organization": cast.organization,
        },
        "assignees": agents,
        "messages": builder.messages,
        "resolution": resolution,
        "attachments": [{"name": f"print-{problem.slug}.png"}] if rng.random() < 0.3 else [],
        "custom_fields": {
            "versao_sistema": f"{rng.randint(10, 12)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}",
            "filial": rng.randint(1, 8),
            "ambiente": rng.choice(("produção", "homologação")),
        },
    }
    return ticket, key
