"""Builds the transactional e-mails (pt-BR) from the Jinja2 templates in ``templates/``.

Each e-mail has a plain-text and an HTML version. The links point to pages of the admin
panel under ``public_base_url`` and carry the single-use token in the query string.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from urllib.parse import urlencode

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from knobridge.core.settings import Settings
from knobridge.email.sender import OutgoingEmail


class EmailTemplate(StrEnum):
    PASSWORD_RESET = "password_reset"  # noqa: S105 - template name, not a secret
    EMAIL_VERIFICATION = "email_verification"
    INVITATION = "invitation"
    INITIAL_PASSWORD = "initial_password"  # noqa: S105 - template name, not a secret


SUBJECTS: dict[EmailTemplate, str] = {
    EmailTemplate.PASSWORD_RESET: "Redefinição de senha do KnoBridge",
    EmailTemplate.EMAIL_VERIFICATION: "Confirme seu e-mail no KnoBridge",
    EmailTemplate.INVITATION: "Você foi convidado para um workspace no KnoBridge",
    EmailTemplate.INITIAL_PASSWORD: "Defina sua senha do KnoBridge",
}

# Admin panel pages that consume each token (frontend routes).
LINK_PATHS: dict[EmailTemplate, str] = {
    EmailTemplate.PASSWORD_RESET: "/reset-password",
    EmailTemplate.EMAIL_VERIFICATION: "/verify-email",
    EmailTemplate.INVITATION: "/accept-invitation",
    EmailTemplate.INITIAL_PASSWORD: "/set-password",
}

_SECONDS_PER_UNIT: tuple[tuple[int, str, str], ...] = (
    (86400, "dia", "dias"),
    (3600, "hora", "horas"),
    (60, "minuto", "minutos"),
)


def describe_duration(duration: timedelta) -> str:
    """Spell a validity window in pt-BR using the largest exact unit ("24 horas", "7 dias")."""
    seconds = max(int(duration.total_seconds()), 60)
    for unit, singular, plural in _SECONDS_PER_UNIT:
        if seconds >= unit and seconds % unit == 0:
            count = seconds // unit
            return f"{count} {singular if count == 1 else plural}"
    minutes = -(-seconds // 60)  # round up: never promise more time than the token has
    return f"{minutes} minutos"


def _default_environment() -> Environment:
    return Environment(
        loader=PackageLoader("knobridge.email", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html",), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text: str
    html: str


class EmailComposer:
    """Renders each transactional e-mail and builds its link."""

    def __init__(self, *, public_base_url: str, environment: Environment | None = None) -> None:
        self._base_url = public_base_url.rstrip("/")
        self._env = environment or _default_environment()

    @classmethod
    def from_settings(cls, settings: Settings) -> EmailComposer:
        return cls(public_base_url=settings.public_base_url)

    def link(self, template: EmailTemplate, token: str) -> str:
        return f"{self._base_url}{LINK_PATHS[template]}?{urlencode({'token': token})}"

    def render(self, template: EmailTemplate, context: dict[str, object]) -> RenderedEmail:
        return RenderedEmail(
            subject=SUBJECTS[template],
            text=self._env.get_template(f"{template}.txt").render(context),
            html=self._env.get_template(f"{template}.html").render(context),
        )

    def password_reset(self, *, to: str, token: str, expires_in: timedelta) -> OutgoingEmail:
        return self._compose(EmailTemplate.PASSWORD_RESET, to, token, expires_in)

    def email_verification(self, *, to: str, token: str, expires_in: timedelta) -> OutgoingEmail:
        return self._compose(EmailTemplate.EMAIL_VERIFICATION, to, token, expires_in)

    def invitation(
        self,
        *,
        to: str,
        token: str,
        expires_in: timedelta,
        workspace_name: str,
        inviter_name: str,
    ) -> OutgoingEmail:
        return self._compose(
            EmailTemplate.INVITATION,
            to,
            token,
            expires_in,
            workspace_name=workspace_name,
            inviter_name=inviter_name,
        )

    def initial_password(self, *, to: str, token: str, expires_in: timedelta) -> OutgoingEmail:
        return self._compose(EmailTemplate.INITIAL_PASSWORD, to, token, expires_in)

    def _compose(
        self,
        template: EmailTemplate,
        to: str,
        token: str,
        expires_in: timedelta,
        **extra: object,
    ) -> OutgoingEmail:
        context: dict[str, object] = {
            "link": self.link(template, token),
            "expires_in": describe_duration(expires_in),
            "base_url": self._base_url,
            **extra,
        }
        rendered = self.render(template, context)
        return OutgoingEmail(
            to=to, subject=rendered.subject, text=rendered.text, html=rendered.html
        )
