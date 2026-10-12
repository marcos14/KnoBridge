"""Fire-and-forget delivery for e-mails sent on behalf of an HTTP request.

The API schedules :func:`deliver_quietly` as a background task, so it runs after the
transaction committed and after the response left. The response time then does not depend
on the mail server (nor reveal whether a message was sent at all), and an SMTP outage never
fails a request whose database change already happened. Failures are logged by kind only:
recipient, token and body are personal or secret data.
"""

from __future__ import annotations

from collections.abc import Callable

from knobridge.core.logging import get_logger
from knobridge.email.sender import EmailSender, OutgoingEmail

_log = get_logger(__name__)


async def deliver_quietly(
    sender: EmailSender, compose: Callable[[], OutgoingEmail], *, kind: str
) -> None:
    """Render and send one e-mail; log and swallow any failure.

    ``compose`` runs here too (not in the request), so rendering adds no time to the response.
    ``kind`` is the template name, the only detail that reaches the log.
    """
    try:
        await sender.send(compose())
    except Exception as exc:
        # Broad on purpose: this runs after the response, so nobody upstream can handle it.
        _log.warning("email_not_delivered", kind=kind, error=type(exc).__name__)
