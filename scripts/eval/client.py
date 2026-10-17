"""The KnoBridge routes the evaluation uses: the panel ones (session and CSRF) to prepare and
clean up, and the public REST (API key) to ask. Contracts in docs/specs/openapi.json."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from eval.jsonx import as_object, get_object, get_opt_str, get_str

CSRF_HEADER = "X-CSRF-Token"


class ApiError(Exception):
    """A non-2xx answer; ``code`` is ``error.code`` of the error envelope (or ``http_<status>``)."""

    def __init__(self, method: str, path: str, status: int, code: str, message: str) -> None:
        super().__init__(f"{method} {path}: HTTP {status} {code}: {message}")
        self.status = status
        self.code = code


def _error_of(response: httpx.Response) -> tuple[str, str]:
    try:
        body: object = response.json()
        error = get_object(as_object(body, "$"), "error", "$")
        return get_str(error, "code", "$.error"), get_opt_str(error, "message", "$.error") or ""
    except ValueError:
        return f"http_{response.status_code}", response.text[:200]


@dataclass(frozen=True)
class Upload:
    filename: str
    content: bytes


class KnoBridgeClient:
    """Thin wrapper over ``httpx.Client``; every method returns the decoded JSON body."""

    def __init__(self, http: httpx.Client, workspace_id: str) -> None:
        self._http = http
        self._csrf: str | None = None
        self._ws = f"/v1/workspaces/{workspace_id}"

    def _call(
        self,
        method: str,
        path: str,
        *,
        body: object = None,
        upload: Upload | None = None,
        api_key: str | None = None,
        params: dict[str, str | int] | None = None,
    ) -> object:
        headers: dict[str, str] = {}
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key}"
        elif method != "GET" and self._csrf is not None:
            headers[CSRF_HEADER] = self._csrf
        files = None if upload is None else {"file": (upload.filename, upload.content)}
        response = self._http.request(
            method,
            path,
            json=body if upload is None and body is not None else None,
            files=files,
            headers=headers,
            params=params,
        )
        if response.status_code >= 400:
            code, message = _error_of(response)
            raise ApiError(method, path, response.status_code, code, message)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def login(self, email: str, password: str) -> None:
        self._call("POST", "/v1/auth/login", body={"email": email, "password": password})
        csrf = as_object(self._call("GET", "/v1/auth/csrf"), "$")
        self._csrf = get_str(csrf, "csrf_token", "$")

    # Panel: preparation and cleanup.

    def create(self, resource: str, body: dict[str, object]) -> dict[str, object]:
        return as_object(self._call("POST", f"{self._ws}/{resource}", body=body), "$")

    def get(self, resource: str) -> dict[str, object]:
        return as_object(self._call("GET", f"{self._ws}/{resource}"), "$")

    def patch(self, resource: str, body: dict[str, object]) -> dict[str, object]:
        return as_object(self._call("PATCH", f"{self._ws}/{resource}", body=body), "$")

    def post(self, resource: str) -> dict[str, object]:
        return as_object(self._call("POST", f"{self._ws}/{resource}"), "$")

    def delete(self, resource: str) -> None:
        self._call("DELETE", f"{self._ws}/{resource}")

    def upload(self, resource: str, upload: Upload) -> dict[str, object]:
        return as_object(self._call("POST", f"{self._ws}/{resource}", upload=upload), "$")

    # Public REST: one conversation per question.

    def create_conversation(self, api_key: str, product_id: str, level: str) -> str:
        body = {"product_id": product_id, "level": level}
        created = as_object(
            self._call("POST", "/v1/conversations", body=body, api_key=api_key), "$"
        )
        return get_str(created, "id", "$")

    def ask(self, api_key: str, conversation_id: str, content: str) -> object:
        return self._call(
            "POST",
            f"/v1/conversations/{conversation_id}/messages",
            body={"content": content, "stream": False},
            api_key=api_key,
        )
