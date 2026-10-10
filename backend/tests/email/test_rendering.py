from __future__ import annotations

from datetime import timedelta

import pytest
from jinja2 import UndefinedError

from knobridge.core.settings import Settings
from knobridge.email.rendering import (
    LINK_PATHS,
    SUBJECTS,
    EmailComposer,
    EmailTemplate,
    describe_duration,
)
from knobridge.email.sender import OutgoingEmail

BASE_URL = "https://kb.example"
TOKEN = "tok_abc-123"  # noqa: S105 - synthetic token


@pytest.fixture
def composer() -> EmailComposer:
    return EmailComposer(public_base_url=BASE_URL)


def _compose_all(composer: EmailComposer) -> dict[EmailTemplate, OutgoingEmail]:
    expires = timedelta(hours=12)
    to = "ana@example.com"
    return {
        EmailTemplate.PASSWORD_RESET: composer.password_reset(
            to=to, token=TOKEN, expires_in=expires
        ),
        EmailTemplate.EMAIL_VERIFICATION: composer.email_verification(
            to=to, token=TOKEN, expires_in=expires
        ),
        EmailTemplate.INVITATION: composer.invitation(
            to=to,
            token=TOKEN,
            expires_in=expires,
            workspace_name="Suporte",
            inviter_name="Bruno",
        ),
    }


def test_render_password_reset_contains_link(composer: EmailComposer) -> None:
    email = composer.password_reset(
        to="ana@example.com", token=TOKEN, expires_in=timedelta(hours=1)
    )

    link = f"{BASE_URL}/reset-password?token={TOKEN}"
    assert email.to == "ana@example.com"
    assert email.subject == "Redefinição de senha do KnoBridge"
    assert link in email.text
    assert f'href="{link}"' in email.html
    assert "1 hora" in email.text
    assert "1 hora" in email.html


@pytest.mark.parametrize("template", list(EmailTemplate))
def test_templates_have_text_and_html(composer: EmailComposer, template: EmailTemplate) -> None:
    email = _compose_all(composer)[template]

    link = composer.link(template, TOKEN)
    assert email.subject == SUBJECTS[template]
    assert link in email.text
    assert link in email.html
    assert "<" not in email.text
    assert email.html.startswith("<!doctype html>")
    assert "12 horas" in email.text
    assert "12 horas" in email.html


def test_every_template_has_subject_and_link_path() -> None:
    assert set(SUBJECTS) == set(EmailTemplate)
    assert set(LINK_PATHS) == set(EmailTemplate)


def test_invitation_mentions_workspace_and_inviter(composer: EmailComposer) -> None:
    email = _compose_all(composer)[EmailTemplate.INVITATION]

    assert 'Bruno convidou você para participar do workspace "Suporte"' in email.text
    assert "<strong>Suporte</strong>" in email.html


def test_invitation_html_escapes_user_supplied_names(composer: EmailComposer) -> None:
    email = composer.invitation(
        to="ana@example.com",
        token=TOKEN,
        expires_in=timedelta(days=7),
        workspace_name="<script>x</script>",
        inviter_name="Eve & Co",
    )

    assert "<script>" not in email.html
    assert "&lt;script&gt;x&lt;/script&gt;" in email.html
    assert "Eve &amp; Co" in email.html
    assert "Eve & Co" in email.text


def test_link_strips_trailing_slash_and_encodes_token() -> None:
    composer = EmailComposer(public_base_url="https://kb.example/")

    link = composer.link(EmailTemplate.EMAIL_VERIFICATION, "a b/c")

    assert link == "https://kb.example/verify-email?token=a+b%2Fc"


def test_render_rejects_missing_context(composer: EmailComposer) -> None:
    with pytest.raises(UndefinedError):
        composer.render(EmailTemplate.PASSWORD_RESET, {"expires_in": "1 hora"})


def test_composer_from_settings_uses_public_base_url() -> None:
    composer = EmailComposer.from_settings(Settings(public_base_url="https://painel.example"))

    link = composer.link(EmailTemplate.EMAIL_VERIFICATION, "t")

    assert link == "https://painel.example/verify-email?token=t"


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (timedelta(days=1), "1 dia"),
        (timedelta(days=7), "7 dias"),
        (timedelta(hours=1), "1 hora"),
        (timedelta(hours=36), "36 horas"),
        (timedelta(minutes=1), "1 minuto"),
        (timedelta(minutes=30), "30 minutos"),
        (timedelta(seconds=90), "2 minutos"),
        (timedelta(seconds=10), "1 minuto"),
    ],
)
def test_describe_duration_uses_largest_exact_unit(duration: timedelta, expected: str) -> None:
    assert describe_duration(duration) == expected
