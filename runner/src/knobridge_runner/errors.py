"""Domain errors of the runner, mapped from the server responses (docs/specs/runner.md)."""

from __future__ import annotations

# Process exit codes of `knobridge-runner run` (docs/specs/runner.md, "Retentativas do runner").
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_INVALID_TOKEN = 3
EXIT_WORKSPACE_SUSPENDED = 4
EXIT_UPGRADE_REQUIRED = 5


class RunnerError(Exception):
    """Base class of the errors raised by the runner client."""


class ServerError(RunnerError):
    """An error answer of the server, with its HTTP status and error code."""

    def __init__(self, status: int, code: str | None, message: str) -> None:
        super().__init__(f"{status} {code or 'unknown'}: {message}")
        self.status = status
        self.code = code


class FatalServerError(ServerError):
    """The runner must stop: invalid token, suspended workspace or unsupported protocol."""

    def __init__(self, status: int, code: str | None, message: str, exit_code: int) -> None:
        super().__init__(status, code, message)
        self.exit_code = exit_code


class JobGoneError(ServerError):
    """404 or 409 on a job route: the job is no longer ours; abandon it without retrying."""


class RejectedError(ServerError):
    """413 or 422: the payload was refused; retrying the same body cannot succeed."""


class UnavailableError(RunnerError):
    """Network error, timeout or 5xx after the retry budget was spent."""
