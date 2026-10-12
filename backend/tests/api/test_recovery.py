"""Password recovery and e-mail verification routes: forgot, reset, verify, resend."""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from api_support import CHEAP, PASSWORD, START, ApiEnv, SeededUser, db_settings
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from fakes.email_sender import FakeEmailSender
from knobridge.api.app import create_app
from knobridge.core.clock import FrozenClock
from knobridge.email.sender import EmailDeliveryError, OutgoingEmail
from knobridge.security.passwords import PasswordHasher
from knobridge.tenancy.models import UserStatus

pytestmark = pytest.mark.integration

NEW_PASSWORD = "a brand new passphrase"  # noqa: S105 - test value
# Settings default: e-mails of each kind per address per window.
EMAIL_LIMIT = 3


def _forgot(api: ApiEnv, email: str) -> tuple[int, bytes]:
    response = api.client.post("/v1/auth/password/forgot", json={"email": email})
    return response.status_code, response.content


def _reset(api: ApiEnv, token: str, password: str = NEW_PASSWORD) -> tuple[int, str]:
    response = api.client.post(
        "/v1/auth/password/reset", json={"token": token, "password": password}
    )
    code: str = response.json()["error"]["code"] if response.content else ""
    return response.status_code, code


def _reset_token(api: ApiEnv, user: SeededUser) -> str:
    assert _forgot(api, user.email)[0] == 204
    return api.emailed_token(user.email)


def test_forgot_password_same_response_for_unknown_email(api: ApiEnv) -> None:
    user = api.create_user()

    known = api.client.post("/v1/auth/password/forgot", json={"email": user.email.upper()})
    unknown = api.client.post(
        "/v1/auth/password/forgot", json={"email": "nobody-here@example.test"}
    )

    assert known.status_code == unknown.status_code == 204
    assert known.content == unknown.content == b""
    assert sorted(known.headers.keys()) == sorted(unknown.headers.keys())
    [email] = api.emails.sent_to(user.email)
    assert "/reset-password?token=" in email.text
    assert api.emails.sent_to("nobody-here@example.test") == []
    assert api.audit_actions(user.id) == [("auth.password_reset.requested", {})]


def test_forgot_password_skips_suspended_user(api: ApiEnv) -> None:
    user = api.create_user(status=UserStatus.SUSPENDED)

    assert _forgot(api, user.email) == (204, b"")
    assert api.emails.sent_to(user.email) == []


def test_forgot_password_limits_emails_per_address_silently(api: ApiEnv) -> None:
    user = api.create_user()
    for _ in range(EMAIL_LIMIT):
        assert _forgot(api, user.email) == (204, b"")

    over_limit = _forgot(api, user.email)
    sent_while_blocked = len(api.emails.sent_to(user.email))
    api.clock.advance(timedelta(hours=1))
    _forgot(api, user.email)

    assert over_limit == (204, b"")
    assert sent_while_blocked == EMAIL_LIMIT
    assert len(api.emails.sent_to(user.email)) == EMAIL_LIMIT + 1


def test_forgot_password_validates_body(api: ApiEnv) -> None:
    response = api.client.post("/v1/auth/password/forgot", json={"email": ""})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


class _BrokenSender:
    async def send(self, email: OutgoingEmail) -> None:
        raise EmailDeliveryError("Could not deliver the e-mail")


@pytest.fixture
def broken_mail_api(app_database_url: str) -> Generator[ApiEnv]:
    clock, hasher = FrozenClock(START), PasswordHasher(CHEAP)
    app = create_app(
        db_settings(app_database_url),
        clock=clock,
        password_hasher=hasher,
        email_sender=_BrokenSender(),
    )
    with TestClient(app) as client:
        yield ApiEnv(
            client=client,
            clock=clock,
            database_url=app_database_url,
            hasher=hasher,
            emails=FakeEmailSender(),
        )


def test_forgot_password_mail_failure_is_logged_without_personal_data(
    broken_mail_api: ApiEnv,
) -> None:
    user = broken_mail_api.create_user()

    with capture_logs() as logs:
        status = _forgot(broken_mail_api, user.email)

    assert status == (204, b"")
    [entry] = [log for log in logs if log["event"] == "email_not_delivered"]
    assert entry == {
        "event": "email_not_delivered",
        "kind": "password_reset",
        "error": "EmailDeliveryError",
        "log_level": "warning",
    }
    assert user.email not in repr(logs)


def test_reset_password_revokes_sessions(api: ApiEnv) -> None:
    user = api.create_user()
    api.login(user)
    api.login(user)  # a second device
    token = _reset_token(api, user)

    response = api.client.post(
        "/v1/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}
    )

    assert response.status_code == 204
    sessions = api.sessions(user.id)
    assert len(sessions) == 2
    assert all(session.revoked_at == START for session in sessions)
    assert "knobridge_session" not in api.client.cookies
    assert api.client.get("/v1/me").status_code == 401
    old = api.client.post("/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert old.status_code == 401
    api.login(user, NEW_PASSWORD)
    assert ("auth.password_reset.completed", {"revoked_sessions": 2}) in api.audit_actions(user.id)


def test_reset_password_marks_email_verified(api: ApiEnv) -> None:
    user = api.create_user()
    token = _reset_token(api, user)
    api.clock.advance(timedelta(minutes=5))

    assert _reset(api, token) == (204, "")
    first_verified_at = api.user(user.id).email_verified_at
    api.clock.advance(timedelta(minutes=5))
    assert _reset(api, _reset_token(api, user), "yet another passphrase") == (204, "")

    assert first_verified_at == START + timedelta(minutes=5)
    assert api.user(user.id).email_verified_at == first_verified_at  # first date is kept


def test_reset_token_reuse_rejected(api: ApiEnv) -> None:
    user = api.create_user()
    token = _reset_token(api, user)
    assert _reset(api, token) == (204, "")

    second = _reset(api, token, "yet another passphrase")

    assert second == (400, "invalid_token")
    api.login(user, NEW_PASSWORD)


def test_reset_password_weak_password_keeps_token(api: ApiEnv) -> None:
    user = api.create_user()
    token = _reset_token(api, user)

    weak = _reset(api, token, "short")

    assert weak == (422, "weak_password")
    assert _reset(api, token) == (204, "")


def test_reset_password_invalidates_older_links(api: ApiEnv) -> None:
    user = api.create_user()
    first = _reset_token(api, user)
    second = _reset_token(api, user)

    assert _reset(api, second) == (204, "")
    assert _reset(api, first, "yet another passphrase") == (400, "invalid_token")


def test_reset_token_expires(api: ApiEnv) -> None:
    user = api.create_user()
    token = _reset_token(api, user)
    api.clock.advance(timedelta(hours=1))

    assert _reset(api, token) == (400, "invalid_token")


def test_reset_password_rejects_unknown_token(api: ApiEnv) -> None:
    assert _reset(api, "not-a-real-token") == (400, "invalid_token")


def _verification_token(api: ApiEnv, user: SeededUser) -> str:
    response = api.client.post("/v1/auth/email/resend", headers=api.csrf_headers())
    assert response.status_code == 204, response.text
    [*_, email] = api.emails.sent_to(user.email)
    assert "/verify-email?token=" in email.text
    return api.emailed_token(user.email)


def test_verify_email_marks_verified(api: ApiEnv) -> None:
    user = api.create_user()
    api.login(user)
    token = _verification_token(api, user)
    api.clock.advance(timedelta(minutes=5))
    api.client.cookies.clear()  # the link may be opened in another browser

    response = api.client.post("/v1/auth/email/verify", json={"token": token})

    assert response.status_code == 204
    assert api.user(user.id).email_verified_at == START + timedelta(minutes=5)
    actions = {action for action, _ in api.audit_actions(user.id)}
    assert {"auth.email_verification.requested", "auth.email.verified"} <= actions


def test_verify_email_rejects_used_token(api: ApiEnv) -> None:
    user = api.create_user()
    api.login(user)
    token = _verification_token(api, user)
    assert api.client.post("/v1/auth/email/verify", json={"token": token}).status_code == 204

    again = api.client.post("/v1/auth/email/verify", json={"token": token})

    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_token"


def test_verify_email_rejects_reset_token(api: ApiEnv) -> None:
    user = api.create_user()
    token = _reset_token(api, user)

    response = api.client.post("/v1/auth/email/verify", json={"token": token})

    assert response.status_code == 400
    assert api.user(user.id).email_verified_at is None


def test_resend_verification_conflicts_when_already_verified(api: ApiEnv) -> None:
    user = api.create_user()
    api.login(user)
    api.client.post("/v1/auth/email/verify", json={"token": _verification_token(api, user)})

    response = api.client.post("/v1/auth/email/resend", headers=api.csrf_headers())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_already_verified"


def test_resend_verification_limited_per_address(api: ApiEnv) -> None:
    user = api.create_user()
    api.login(user)
    for _ in range(EMAIL_LIMIT):
        _verification_token(api, user)

    response = api.client.post("/v1/auth/email/resend", headers=api.csrf_headers())

    assert response.status_code == 429
    assert response.json()["error"] == {
        "code": "too_many_attempts",
        "message": "Too many e-mails requested. Try again later.",
        "details": {"retry_after_seconds": 3600},
    }
    assert len(api.emails.sent_to(user.email)) == EMAIL_LIMIT


def test_resend_verification_requires_csrf_and_session(api: ApiEnv) -> None:
    user = api.create_user()
    api.login(user)

    without_csrf = api.client.post("/v1/auth/email/resend")
    api.client.post("/v1/auth/logout", headers=api.csrf_headers())
    api.client.get("/v1/auth/csrf")
    without_session = api.client.post("/v1/auth/email/resend", headers=api.csrf_headers())

    assert without_csrf.status_code == 403
    assert without_session.status_code == 401
    assert api.emails.sent_to(user.email) == []
