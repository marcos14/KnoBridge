"""The answer key (gabarito) of one ticket: what was seeded where, and what anonymization does.

Three lists, so the anonymization can be measured (plan 0005, F6.2):

- ``anonimizar``: personal data the rules of docs/specs/chamados.md must replace, with the marker
  they must produce;
- ``preservar``: text that looks like personal data but must stay (build numbers shaped like an
  IPv4 after "versão");
- ``nao_detectavel``: personal data the rules are known not to catch (names of third parties not
  declared in the payload), to measure the known false negatives.

``onde`` is the field path in the ticket (``messages[2].body``, ``resolution.body``) and
``nota_interna`` says whether that message is an internal note (indexed only when the source
includes internal notes).
"""

from __future__ import annotations

from dataclasses import dataclass, field

MARKERS: dict[str, str] = {
    "email": "[EMAIL]",
    "ip": "[IP]",
    "cnpj": "[CNPJ]",
    "cpf": "[CPF]",
    "cartao": "[CARTAO]",
    "telefone": "[TELEFONE]",
}

Entry = dict[str, str | bool | None]


@dataclass
class AnswerKey:
    external_id: str
    anonimizar: list[Entry] = field(default_factory=list[Entry])
    preservar: list[Entry] = field(default_factory=list[Entry])
    nao_detectavel: list[Entry] = field(default_factory=list[Entry])

    def personal(self, kind: str, value: str, where: str, *, internal: bool = False) -> str:
        """Records a seeded datum (e-mail, CPF...) and returns it, to be written in the text."""
        self.anonimizar.append(_entry(kind, value, MARKERS[kind], where, internal))
        return value

    def name(
        self, kind: str, value: str, marker: str, where: str, *, internal: bool = False
    ) -> str:
        """Records a declared name (``nome``, ``primeiro_nome`` or ``organizacao``)."""
        self.anonimizar.append(_entry(kind, value, marker, where, internal))
        return value

    def keep(self, kind: str, value: str, where: str, *, internal: bool = False) -> str:
        self.preservar.append(_entry(kind, value, None, where, internal))
        return value

    def undetectable(self, kind: str, value: str, where: str, *, internal: bool = False) -> str:
        self.nao_detectavel.append(_entry(kind, value, None, where, internal))
        return value

    def as_json(self) -> dict[str, object]:
        return {
            "external_id": self.external_id,
            "anonimizar": self.anonimizar,
            "preservar": self.preservar,
            "nao_detectavel": self.nao_detectavel,
        }


def _entry(kind: str, value: str, marker: str | None, where: str, internal: bool) -> Entry:
    return {
        "tipo": kind,
        "valor": value,
        "marcador": marker,
        "onde": where,
        "nota_interna": internal,
    }
