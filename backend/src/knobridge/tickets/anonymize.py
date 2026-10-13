"""Deterministic anonymization of a ticket's texts (docs/specs/chamados.md, "Anonimização").

The rules run in the spec's order: e-mail, IP, CNPJ, CPF, card, phone and the names declared in
the payload. Each rule only looks at text no earlier rule replaced, so a marker is never matched
again (``ana.souza@…`` becomes ``[EMAIL]``, never ``[SOLICITANTE]@…``). Numbers only match
between digit boundaries. Names match ignoring case and accents, as whole words, longest first;
every person keeps one marker across the whole ticket.
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator, Mapping

from knobridge.tickets.wire import TicketIn, TicketMessageRole

EMAIL = "[EMAIL]"
IP = "[IP]"
CNPJ = "[CNPJ]"
CPF = "[CPF]"
CARD = "[CARTAO]"
PHONE = "[TELEFONE]"
REQUESTER = "[SOLICITANTE]"
ORGANIZATION = "[ORGANIZACAO]"

# A first name is replaced on its own only from this many letters on ("Ana" yes, "Jo" no).
MIN_FIRST_NAME_LETTERS = 3
# Card groups: a run of 13 to 19 digits, or groups of 3 to 6 digits ("4111 1111 1111 1111",
# Amex "3782 822463 10005"); shorter groups are phone and date fragments ("+55 11 …").
CARD_MIN_DIGITS = 13
CARD_MAX_DIGITS = 19
CARD_GROUP_MIN = 3
CARD_GROUP_MAX = 6
# IPv4 right after these words is a version number, not an address ("versão 10.2.0.1").
VERSION_WORDS = ("versão ", "versao ", "version ", "release ", "build ")

type Match = tuple[int, int, str]
type Finder = Callable[[str], Iterator[Match]]

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![A-Za-z0-9-])")
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
_IPV4_TEXT = rf"{_OCTET}(?:\.{_OCTET}){{3}}"
_IPV4 = re.compile(rf"(?<!\d){_IPV4_TEXT}(?!\d)")
# A loose candidate (hex groups and colons, optionally ending in an IPv4) checked by ``ipaddress``,
# which rejects times such as ``14:02:00``; ``std::vector`` never starts a candidate.
_IPV6 = re.compile(r"(?<![\w:])[0-9A-Fa-f:]{2,39}(?:(?<=:)(?:\d{1,3}\.){3}\d{1,3})?(?![\w:]|\.\d)")
_CNPJ = re.compile(r"(?<!\d)(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{14})(?!\d)")
_CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")
_DIGIT_RUN = re.compile(r"(?<!\d)\d+(?:[ -]\d+)*(?!\d)")
_DIGITS = re.compile(r"\d+")
_PHONE = re.compile(
    r"(?<!\d)(?:"
    r"(?:\+55[ .-]?)?(?:\([1-9][1-9]\)|[1-9][1-9])[ .-]?9?\d{4}[ .-]?\d{4}"
    r"|9?\d{4}-\d{4}"
    r")(?!\d)"
)
_CNPJ_WEIGHTS = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def _only_digits(text: str) -> str:
    return "".join(char for char in text if char.isdigit())


def cpf_is_valid(digits: str) -> bool:
    """11 digits with both check digits right; all-equal digits (``111…``) do not count."""
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for size in (9, 10):
        total = sum(int(digits[i]) * (size + 1 - i) for i in range(size))
        if (total * 10) % 11 % 10 != int(digits[size]):
            return False
    return True


def cnpj_is_valid(digits: str) -> bool:
    """14 digits with both check digits right."""
    if len(digits) != 14:
        return False
    for size in (12, 13):
        weights = _CNPJ_WEIGHTS[13 - size :]
        remainder = sum(int(d) * w for d, w in zip(digits[:size], weights, strict=True)) % 11
        if (0 if remainder < 2 else 11 - remainder) != int(digits[size]):
            return False
    return True


def luhn_is_valid(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        value = int(char)
        if position % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _search(
    pattern: re.Pattern[str], marker: str, accept: Callable[[str, re.Match[str]], bool]
) -> Finder:
    """Matches of ``pattern`` that ``accept`` keeps; after a rejected match the search goes on
    from the next character, so a valid number right after an invalid one is still found."""

    def find(text: str) -> Iterator[Match]:
        position = 0
        while (match := pattern.search(text, position)) is not None:
            if accept(text, match):
                yield match.start(), match.end(), marker
                position = match.end()
            else:
                position = match.start() + 1

    return find


def _is_address(text: str, match: re.Match[str]) -> bool:
    before = text[: match.start()]
    return not before.endswith(("v", "V")) and not before.lower().endswith(VERSION_WORDS)


def _find_ipv6(text: str) -> Iterator[Match]:
    """IPv6 candidates that ``ipaddress`` accepts; a colon ending a sentence is not part of it."""
    for match in _IPV6.finditer(text):
        candidate = match.group().rstrip(":")
        if any(char not in ":." for char in candidate) and _parses_as_ipv6(candidate):
            yield match.start(), match.start() + len(candidate), IP


def _parses_as_ipv6(candidate: str) -> bool:
    try:
        ipaddress.IPv6Address(candidate)
    except ValueError:
        return False
    return True


def _find_cards(text: str) -> Iterator[Match]:
    """Within each run of digit groups, the longest Luhn-valid stretch from the leftmost group."""
    for run in _DIGIT_RUN.finditer(text):
        offset = run.start()
        groups = [(m.start() + offset, m.end() + offset) for m in _DIGITS.finditer(run.group())]
        first = 0
        while first < len(groups):
            last = _card_end(text, groups, first)
            if last is None:
                first += 1
                continue
            yield groups[first][0], groups[last][1], CARD
            first = last + 1


def _card_end(text: str, groups: list[tuple[int, int]], first: int) -> int | None:
    for last in range(len(groups) - 1, first - 1, -1):
        stretch = groups[first : last + 1]
        digits = "".join(text[start:end] for start, end in stretch)
        sized = len(stretch) == 1 or all(
            CARD_GROUP_MIN <= end - start <= CARD_GROUP_MAX for start, end in stretch
        )
        if CARD_MIN_DIGITS <= len(digits) <= CARD_MAX_DIGITS and sized and luhn_is_valid(digits):
            return last
    return None


def _always(_text: str, _match: re.Match[str]) -> bool:
    return True


NUMBER_RULES: tuple[Finder, ...] = (
    _search(_EMAIL, EMAIL, _always),
    _find_ipv6,
    _search(_IPV4, IP, _is_address),
    _search(_CNPJ, CNPJ, lambda _t, m: cnpj_is_valid(_only_digits(m.group()))),
    _search(_CPF, CPF, lambda _t, m: cpf_is_valid(_only_digits(m.group()))),
    _find_cards,
    _search(_PHONE, PHONE, _always),
)


def fold(text: str) -> str:
    """Case and accents dropped: ``José`` and ``jose`` fold the same."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def name_key(name: str | None) -> str:
    """A declared name, folded and with its whitespace collapsed; empty when there is none."""
    return " ".join(fold(name).split()) if name else ""


def _folded_with_index(text: str) -> tuple[str, list[int]]:
    """``text`` folded char by char, with the original index of every folded char."""
    folded: list[str] = []
    index: list[int] = []
    for position, char in enumerate(text):
        part = fold(char)
        folded.append(part)
        index.extend([position] * len(part))
    return "".join(folded), index


def _names_finder(names: Mapping[str, str]) -> Finder:
    keys = sorted(names, key=lambda key: (-len(key), key))
    alternatives = "|".join(r"\s+".join(map(re.escape, key.split())) for key in keys)
    pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)")

    def find(text: str) -> Iterator[Match]:
        folded, index = _folded_with_index(text)
        for match in pattern.finditer(folded):
            end = index[match.end() - 1] + 1
            # A decomposed accent after the last letter belongs to the name.
            while end < len(text) and unicodedata.combining(text[end]):
                end += 1
            yield index[match.start()], end, names[" ".join(match.group().split())]

    return find


def _replace(segments: list[tuple[str, bool]], finder: Finder) -> list[tuple[str, bool]]:
    """Apply ``finder`` to the segments not replaced yet; replaced ones are kept as they are."""
    result: list[tuple[str, bool]] = []
    for text, replaced in segments:
        if replaced:
            result.append((text, True))
            continue
        position = 0
        for start, end, marker in finder(text):
            if start > position:
                result.append((text[position:start], False))
            result.append((marker, True))
            position = end
        if position < len(text):
            result.append((text[position:], False))
    return result


def _letters(word: str) -> int:
    return sum(char.isalpha() for char in word)


class NameBook:
    """Declared names (folded) → marker, filled in order of precedence: a name keeps the first
    marker it gets. Shared by tickets and cards, which declare different people."""

    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    def add(self, name: str | None, marker: str, *, first_name: bool) -> None:
        """``name`` (and its first word, with enough letters, when ``first_name``) → marker;
        an empty name is ignored."""
        key = name_key(name)
        if not key:
            return
        self.names.setdefault(key, marker)
        first = key.split()[0]
        if first_name and _letters(first) >= MIN_FIRST_NAME_LETTERS:
            self.names.setdefault(first, marker)

    def number(self, candidates: Iterable[str | None], label: str) -> None:
        """Each name not declared yet gets ``[<label>_<n>]``, from 1, in order."""
        count = 0
        for name in candidates:
            if name_key(name) and name_key(name) not in self.names:
                count += 1
                self.add(name, f"[{label}_{count}]", first_name=True)


def declared_names(ticket: TicketIn) -> dict[str, str]:
    """Folded name → marker, in the spec's precedence: requester, organization, agents
    (assignees, then agent authors in message order), then other customer authors."""
    book = NameBook()
    requester = ticket.requester
    if requester is not None:
        book.add(requester.name, REQUESTER, first_name=True)
        book.add(requester.organization, ORGANIZATION, first_name=False)
    agents = [person.name for person in ticket.assignees]
    agents += [m.author_name for m in ticket.messages if m.role is TicketMessageRole.AGENT]
    book.number(agents, "ATENDENTE")
    customers = [m.author_name for m in ticket.messages if m.role is TicketMessageRole.CUSTOMER]
    book.number(customers, "CLIENTE")
    return book.names


class TicketAnonymizer:
    """The anonymization of one ticket: the number rules plus the ticket's declared names."""

    def __init__(self, names: Mapping[str, str]) -> None:
        self.names: Mapping[str, str] = dict(names)
        self._finders = NUMBER_RULES + ((_names_finder(self.names),) if self.names else ())

    @classmethod
    def for_ticket(cls, ticket: TicketIn) -> TicketAnonymizer:
        return cls(declared_names(ticket))

    def text(self, value: str) -> str:
        segments = [(value, False)]
        for finder in self._finders:
            segments = _replace(segments, finder)
        return "".join(text for text, _ in segments)

    def author(self, name: str | None) -> str | None:
        """The marker of a message author, or ``None`` when the name is empty or undeclared."""
        return self.names.get(name_key(name))
