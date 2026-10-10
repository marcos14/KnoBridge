"""In-memory ``EmailSender`` for tests: records every message instead of sending it."""

from __future__ import annotations

from knobridge.email.sender import OutgoingEmail


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[OutgoingEmail] = []

    async def send(self, email: OutgoingEmail) -> None:
        self.sent.append(email)

    def sent_to(self, address: str) -> list[OutgoingEmail]:
        return [email for email in self.sent if email.to == address]
