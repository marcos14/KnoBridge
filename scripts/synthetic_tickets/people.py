"""Synthetic people, organizations and personal data (rule 9: nothing here is real).

Every personal datum is generated so that the anonymization rules of docs/specs/chamados.md can
find it: CPF and CNPJ with valid check digits, cards that pass Luhn, phones with a valid DDD,
public-looking IPv4 addresses and e-mails under the reserved ``.example`` top-level domain.
"""

from __future__ import annotations

import random
import re
import unicodedata
from dataclasses import dataclass

# First names have three or more letters and are not Portuguese words, so replacing the first
# name never hides a word of the problem. Customers, agents and third parties never share one.
CUSTOMER_FIRST_NAMES = (
    "Adriana",
    "Camila",
    "Diego",
    "Eduarda",
    "Fabiano",
    "Gabriela",
    "Heitor",
    "Isabela",
    "Juliano",
    "Larissa",
    "Marcelo",
    "Natália",
    "Otávio",
    "Patrícia",
    "Sabrina",
    "Vanessa",
    "Wagner",
    "Yasmin",
    "Leandro",
    "Priscila",
)
AGENT_FIRST_NAMES = (
    "Bruno",
    "Rafael",
    "Thiago",
    "Tatiane",
    "Renato",
    "Silvana",
    "Gustavo",
    "Mariana",
)
THIRD_PARTY_FIRST_NAMES = ("Ulisses", "Viviane", "Rodrigo", "Cristiane", "Maurício", "Débora")
LAST_NAMES = (
    "Albuquerque",
    "Barbosa",
    "Cardoso",
    "Duarte",
    "Esteves",
    "Ferraz",
    "Guimarães",
    "Holanda",
    "Lacerda",
    "Macedo",
    "Nogueira",
    "Pacheco",
    "Quintela",
    "Rezende",
    "Sampaio",
    "Teixeira",
    "Valadares",
    "Xavier",
    "Peixoto",
    "Siqueira",
)
ORGANIZATIONS = (
    "Padaria Sol Nascente",
    "Mercearia Três Irmãos",
    "Farmácia Vida Plena",
    "Distribuidora Monte Azul",
    "Papelaria Ponto Certo",
    "Confecções Lírio Branco",
    "Materiais Alicerce Forte",
    "Restaurante Sabor da Serra",
    "Pet Shop Quatro Patas",
    "Ótica Visão Clara",
    "Livraria Página Nova",
    "Laticínios Vale Verde",
)
# Brazilian area codes (DDD): two digits, no zero in either.
AREA_CODES = (11, 12, 19, 21, 27, 31, 41, 47, 48, 51, 61, 62, 71, 81, 85, 91, 92)


@dataclass(frozen=True)
class Person:
    first: str
    last: str

    @property
    def full(self) -> str:
        return f"{self.first} {self.last}"


def _ascii_words(text: str) -> list[str]:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", ascii_text)


def slug(text: str) -> str:
    """Lowercase ASCII letters and digits only (``Ótica Visão Clara`` -> ``oticavisaoclara``)."""
    return "".join(_ascii_words(text))


def kebab(text: str) -> str:
    """Lowercase ASCII words joined by hyphens (``Caixa (PDV)`` -> ``caixa-pdv``)."""
    return "-".join(_ascii_words(text))


def email_for(person: Person, organization: str) -> str:
    return f"{slug(person.first)}.{slug(person.last)}@{slug(organization)}.example"


def _check_digit(digits: list[int], weights: list[int]) -> int:
    rest = sum(d * w for d, w in zip(digits, weights, strict=True)) % 11
    return 0 if rest < 2 else 11 - rest


def cpf(rng: random.Random, *, formatted: bool) -> str:
    """A CPF with valid check digits, never with all digits equal."""
    while True:
        base = [rng.randrange(10) for _ in range(9)]
        if len(set(base)) > 1:
            break
    first = _check_digit(base, list(range(10, 1, -1)))
    second = _check_digit([*base, first], list(range(11, 1, -1)))
    text = "".join(str(d) for d in [*base, first, second])
    if not formatted:
        return text
    return f"{text[:3]}.{text[3:6]}.{text[6:9]}-{text[9:]}"


def cnpj(rng: random.Random, *, formatted: bool) -> str:
    """A CNPJ (branch 0001) with valid check digits."""
    base = [rng.randrange(10) for _ in range(8)] + [0, 0, 0, 1]
    first = _check_digit(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = _check_digit([*base, first], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    text = "".join(str(d) for d in [*base, first, second])
    if not formatted:
        return text
    return f"{text[:2]}.{text[2:5]}.{text[5:8]}/{text[8:12]}-{text[12:]}"


def luhn_valid(number: str) -> bool:
    digits = [int(char) for char in number if char.isdigit()]
    total = 0
    for position, digit in enumerate(reversed(digits)):
        doubled = digit * 2 if position % 2 else digit
        total += doubled - 9 if doubled > 9 else doubled
    return total % 10 == 0


def card(rng: random.Random) -> str:
    """A 16-digit card number that passes Luhn, in groups of four split by spaces or hyphens."""
    digits = [rng.choice((4, 5))] + [rng.randrange(10) for _ in range(14)]
    for last in range(10):
        if luhn_valid("".join(str(d) for d in [*digits, last])):
            digits.append(last)
            break
    text = "".join(str(d) for d in digits)
    separator = rng.choice((" ", "-"))
    return separator.join(text[i : i + 4] for i in range(0, 16, 4))


def phone(rng: random.Random) -> str:
    """A mobile or landline number with DDD, in one of the formats people write."""
    ddd = rng.choice(AREA_CODES)
    if rng.random() < 0.6:
        number = f"9{rng.randint(6000, 9999)}-{rng.randint(0, 9999):04d}"
    else:
        number = f"{rng.randint(2000, 5999)}-{rng.randint(0, 9999):04d}"
    style = rng.randrange(3)
    if style == 0:
        return f"({ddd}) {number}"
    if style == 1:
        return f"{ddd} {number}"
    return f"+55 {ddd} {number}"


def ipv4(rng: random.Random) -> str:
    """An address that looks like a customer's server (first octet never 0, 10, 127 or 192)."""
    first = rng.choice((177, 187, 189, 200, 201))
    return f"{first}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def version(rng: random.Random) -> str:
    """A four-part build number shaped like an IPv4, which the anonymization must keep."""
    return f"{rng.randint(10, 12)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}.{rng.randint(10, 250)}"


def person(rng: random.Random, first_names: tuple[str, ...], taken: set[str]) -> Person:
    """A person whose first name is not in ``taken`` (one marker per name in a ticket)."""
    first = rng.choice([name for name in first_names if name not in taken])
    taken.add(first)
    return Person(first, rng.choice(LAST_NAMES))
