"""``deliver_quietly``: background delivery that never raises and logs without personal data."""

from __future__ import annotations

import asyncio

from structlog.testing import capture_logs

from fakes.email_sender import FakeEmailSender
from knobridge.email.delivery import deliver_quietly
from knobridge.email.sender import OutgoingEmail

EMAIL = OutgoingEmail(
    to="ana@example.test", subject="Assunto", text="token secreto", html="<p>token</p>"
)


class _ExplodingSender:
    async def send(self, email: OutgoingEmail) -> None:
        raise ConnectionResetError("smtp went away for ana@example.test")


def test_deliver_quietly_sends_composed_email() -> None:
    sender = FakeEmailSender()

    asyncio.run(deliver_quietly(sender, lambda: EMAIL, kind="password_reset"))

    assert sender.sent == [EMAIL]


def test_deliver_quietly_logs_failure_kind_only() -> None:
    with capture_logs() as logs:
        asyncio.run(deliver_quietly(_ExplodingSender(), lambda: EMAIL, kind="password_reset"))

    assert logs == [
        {
            "event": "email_not_delivered",
            "kind": "password_reset",
            "error": "ConnectionResetError",
            "log_level": "warning",
        }
    ]


def test_deliver_quietly_survives_rendering_failure() -> None:
    sender = FakeEmailSender()

    def broken_compose() -> OutgoingEmail:
        raise KeyError("link")

    with capture_logs() as logs:
        asyncio.run(deliver_quietly(sender, broken_compose, kind="email_verification"))

    assert sender.sent == []
    assert logs[0]["error"] == "KeyError"
