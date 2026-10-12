"""Anonymization rules of docs/specs/chamados.md, each with positives and negatives."""

from __future__ import annotations

import pytest
from ticket_payload_support import message, minimal, ticket

from knobridge.tickets.anonymize import (
    TicketAnonymizer,
    cnpj_is_valid,
    cpf_is_valid,
    declared_names,
    luhn_is_valid,
    name_key,
)

NO_NAMES = TicketAnonymizer({})


def _clean(text: str) -> str:
    return NO_NAMES.text(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Escreva para ana.souza@exemplo.com.br hoje", "Escreva para [EMAIL] hoje"),
        ("mailto:Fulano_1+x@sub.exemplo.io.", "mailto:[EMAIL]."),
        (
            "https://suporte.exemplo.com/?email=ana@exemplo.com.br&x=1",
            "https://suporte.exemplo.com/?email=[EMAIL]&x=1",
        ),
    ],
)
def test_anonymize_replaces_emails(text: str, expected: str) -> None:
    assert _clean(text) == expected


@pytest.mark.parametrize(
    "text",
    ["fale com @suporte", "ana@localhost", "ana@exemplo.c", "ana@exemplo.com-x", "a @ b.com"],
)
def test_anonymize_keeps_what_is_not_an_email(text: str) -> None:
    assert _clean(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("servidor 192.168.0.10 caiu", "servidor [IP] caiu"),
        ("de 0.0.0.0 a 255.255.255.255.", "de [IP] a [IP]."),
        ("rota 2001:db8::1 ok", "rota [IP] ok"),
        ("link-local fe80::1: falhou", "link-local [IP]: falhou"),
        ("mapeado ::ffff:192.168.0.1 aqui", "mapeado [IP] aqui"),
        ("completo 2001:0db8:0000:0000:0000:ff00:0042:8329", "completo [IP]"),
    ],
)
def test_anonymize_replaces_ip_addresses(text: str, expected: str) -> None:
    assert _clean(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "versão 10.2.0.1",
        "Versao 10.2.0.1",
        "VERSION 1.2.3.4",
        "release 1.2.3.4",
        "build 1.2.3.4",
        "v1.2.3.4",
        "V1.2.3.4",
        "256.1.1.1",
        "1.2.3",
        "às 14:02:00",
        "std::vector",
        "separador :: aqui",
        "dead:beef",
    ],
)
def test_anonymize_keeps_versions_times_and_non_addresses(text: str) -> None:
    assert _clean(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CNPJ 11.222.333/0001-81.", "CNPJ [CNPJ]."),
        ("CNPJ 11222333000181", "CNPJ [CNPJ]"),
        ("CPF 529.982.247-25.", "CPF [CPF]."),
        ("CPF 52998224725", "CPF [CPF]"),
    ],
)
def test_anonymize_replaces_valid_cnpj_and_cpf(text: str, expected: str) -> None:
    assert _clean(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "CNPJ 11.222.333/0001-82",
        "CPF 529.982.247-26",
        "CPF 111.111.111-11",
        "CPF 11111111111",
        "pedido 529982247251",
        "pedido 1529982247251x",
    ],
)
def test_anonymize_keeps_numbers_that_look_like_documents_but_do_not_validate(text: str) -> None:
    assert _clean(text) == text


def test_anonymize_matches_numbers_only_between_digit_boundaries() -> None:
    assert _clean("ref 052998224725") == "ref 052998224725"


def test_anonymize_finds_a_valid_number_right_after_an_invalid_one() -> None:
    assert _clean("11.222.333/0001-82 e 11.222.333/0001-81") == "11.222.333/0001-82 e [CNPJ]"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("cartão 4111 1111 1111 1111.", "cartão [CARTAO]."),
        ("cartão 4111-1111-1111-1111", "cartão [CARTAO]"),
        ("cartão 4111111111111111", "cartão [CARTAO]"),
        ("amex 3782 822463 10005", "amex [CARTAO]"),
        ("cartão 4111 1111 1111 1111 2026", "cartão [CARTAO] 2026"),
    ],
)
def test_anonymize_replaces_luhn_valid_cards(text: str, expected: str) -> None:
    assert _clean(text) == expected


@pytest.mark.parametrize(
    "text",
    ["cartão 4111 1111 1111 1112", "pedido 4111111111111", "codigo 41 11 11 11 11 11 11 1"],
)
def test_anonymize_keeps_digit_runs_that_are_not_cards(text: str) -> None:
    assert _clean(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ligue (11) 98765-4321.", "ligue [TELEFONE]."),
        ("ligue (11)98765-4321", "ligue [TELEFONE]"),
        ("ligue 11 98765-4321", "ligue [TELEFONE]"),
        ("ligue 11.3333.4444", "ligue [TELEFONE]"),
        ("ligue 1133334444", "ligue [TELEFONE]"),
        ("ligue +55 11 98765-4321", "ligue [TELEFONE]"),
        ("ligue +55 (21) 3333-4444", "ligue [TELEFONE]"),
        ("ligue +5511987654321", "ligue [TELEFONE]"),
        ("ligue 98765-4321", "ligue [TELEFONE]"),
        ("ligue 3333-4444", "ligue [TELEFONE]"),
    ],
)
def test_anonymize_replaces_phones_with_and_without_ddi_and_ddd(text: str, expected: str) -> None:
    assert _clean(text) == expected


@pytest.mark.parametrize(
    "text",
    ["ramal 3333 4444", "CEP 01310-100", "erro 4021", "data 2026-10-01", "ligue 01 98765 4321"],
)
def test_anonymize_keeps_numbers_that_are_not_phones(text: str) -> None:
    assert _clean(text) == text


def test_anonymize_phone_with_ddi_in_groups_is_not_taken_for_a_card() -> None:
    # 13 digits that pass Luhn, but groups of two are not a card's.
    assert luhn_is_valid("5511987654325")

    assert _clean("+55 11 98765-4325") == "[TELEFONE]"


def test_check_digit_helpers_reject_wrong_lengths() -> None:
    assert cpf_is_valid("5299822472") is False
    assert cnpj_is_valid("1122233300018") is False
    assert luhn_is_valid("4111111111111111") is True


def _names_ticket() -> TicketAnonymizer:
    payload = minimal(
        requester={"name": "José da Silva", "organization": "Padaria Exemplo"},
        assignees=[{"name": "Bruno Lima"}, {"name": None}, {"name": "bruno lima"}],
        messages=[
            message("oi", role="customer", author_name="Jose da Silva"),
            message("oi", role="agent", author_name="Carla Dias", minute=1),
            message("oi", role="customer", author_name="Davi Rocha", minute=2),
            message("oi", role="customer", author_name="Eva", minute=3),
            message("oi", role="system", author_name="Robô Status", minute=4),
            message("oi", role="agent", author_name="Bruno", minute=5),
            message("oi", role="customer", author_name="Jo Li", minute=6),
        ],
    )
    return TicketAnonymizer.for_ticket(ticket(payload))


def test_declared_names_follow_the_precedence_and_order_of_the_spec() -> None:
    names = _names_ticket().names

    assert names == {
        "jose da silva": "[SOLICITANTE]",
        "jose": "[SOLICITANTE]",
        "padaria exemplo": "[ORGANIZACAO]",
        "bruno lima": "[ATENDENTE_1]",
        "bruno": "[ATENDENTE_1]",
        "carla dias": "[ATENDENTE_2]",
        "carla": "[ATENDENTE_2]",
        "davi rocha": "[CLIENTE_1]",
        "davi": "[CLIENTE_1]",
        "eva": "[CLIENTE_2]",
        "jo li": "[CLIENTE_3]",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("JOSÉ DA SILVA ligou", "[SOLICITANTE] ligou"),
        ("jose da   silva ligou", "[SOLICITANTE] ligou"),
        ("Falei com José.", "Falei com [SOLICITANTE]."),
        ("José ligou", "[SOLICITANTE] ligou"),
        ("Josefina ligou", "Josefina ligou"),
        ("A Padaria Exemplo pediu", "A [ORGANIZACAO] pediu"),
        ("A padaria pediu", "A padaria pediu"),
        ("bruno e Carla Dias responderam", "[ATENDENTE_1] e [ATENDENTE_2] responderam"),
        ("Davi falou com Eva", "[CLIENTE_1] falou com [CLIENTE_2]"),
        ("Jo Li e Jo", "[CLIENTE_3] e Jo"),
        ("Robô Status mudou", "Robô Status mudou"),
    ],
)
def test_anonymize_replaces_declared_names_ignoring_case_and_accents(
    text: str, expected: str
) -> None:
    assert _names_ticket().text(text) == expected


def test_anonymize_replaces_the_email_before_the_name_in_it() -> None:
    anonymizer = TicketAnonymizer.for_ticket(ticket())

    assert anonymizer.text("ana.souza@exemplo.com.br e Ana") == "[EMAIL] e [SOLICITANTE]"


def test_anonymize_never_matches_a_marker_again() -> None:
    anonymizer = TicketAnonymizer({"email": "[CLIENTE_1]", "ip": "[CLIENTE_2]"})

    assert anonymizer.text("email a@b.com.br ip 10.0.0.1") == (
        "[CLIENTE_1] [EMAIL] [CLIENTE_2] [IP]"
    )


def test_anonymize_author_gives_the_marker_of_a_declared_name_only() -> None:
    anonymizer = _names_ticket()

    assert anonymizer.author("BRUNO LIMA") == "[ATENDENTE_1]"
    assert anonymizer.author("Robô Status") is None
    assert anonymizer.author(None) is None
    assert anonymizer.author("   ") is None


def test_declared_names_without_requester_or_names_are_empty() -> None:
    payload = minimal(requester={"name": " ", "organization": None}, messages=[message("x")])

    assert declared_names(ticket(payload)) == {}
    assert name_key(None) == ""
