"""A fake KnoBridge API for the evaluation tests: the routes ``scripts/eval`` uses, served by
``httpx.MockTransport`` with synthetic answers. No network, no LLM."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

CSRF = "csrf-fake"
API_KEY = "kbk_fake_key"
WORKSPACE = "11111111-1111-1111-1111-111111111111"
NO_SOURCE = "Não encontrei essa informação nas fontes que tenho disponíveis."
WS = f"/v1/workspaces/{WORKSPACE}"


def citation(index: int, kind: str, uri: str, path: str | None = None) -> dict[str, object]:
    return {"index": index, "kind": kind, "uri": uri, "path": path, "title": uri, "snippet": "…"}


def message(
    content: str,
    citations: list[dict[str, object]] | None = None,
    *,
    status: str = "completed",
    steps: int | None = 1,
    cost: float | None = 0.001,
    latency: int | None = 100,
) -> dict[str, object]:
    return {
        "status": status,
        "content": content,
        "citations": citations or [],
        "steps": steps,
        "model": "fake-chat",
        "input_tokens": 120,
        "output_tokens": 30,
        "cost_usd": cost,
        "latency_ms": latency,
        "error_code": "provider_error" if status == "failed" else None,
    }


@dataclass
class FakeKnoBridge:
    """State and behavior knobs of the fake API."""

    answers: dict[str, dict[str, object] | int] = field(
        default_factory=dict[str, "dict[str, object] | int"]
    )
    run_status: str = "succeeded"
    polls_before_done: int = 1
    upload_rejected: int = 0
    sync_conflict: bool = False
    sync_error: str | None = None
    fail_create: str | None = None
    rerank_available: bool = True
    fail_cleanup: bool = False
    interrupt_on: str | None = None
    calls: list[str] = field(default_factory=list[str])
    bodies: dict[str, list[object]] = field(default_factory=dict[str, list[object]])
    counter: int = 0
    polls: dict[str, int] = field(default_factory=dict[str, int])
    sources: dict[str, dict[str, object]] = field(default_factory=dict[str, dict[str, object]])

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def _id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}-{self.counter}"

    def _record(self, request: httpx.Request) -> str:
        path = request.url.path.removeprefix(WS)
        call = f"{request.method} {path}"
        self.calls.append(call)
        if request.headers.get("content-type", "").startswith("application/json"):
            body: object = json.loads(request.content)
            self.bodies.setdefault(call, []).append(body)
        return path

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = self._record(request)
        if request.url.path.startswith("/v1/conversations"):
            return self._public(request, path)
        if path == "/v1/auth/login":
            response = httpx.Response(200, json={"user": {}, "workspaces": []})
            response.headers["set-cookie"] = f"knobridge_csrf={CSRF}; Path=/"
            return response
        if path == "/v1/auth/csrf":
            return httpx.Response(200, json={"csrf_token": CSRF})
        if request.method != "GET" and request.headers.get("x-csrf-token") != CSRF:
            return _error(403, "csrf_failed")
        return self._panel(request, path)

    def _panel(self, request: httpx.Request, path: str) -> httpx.Response:
        method = request.method
        if method == "DELETE":
            return _error(500, "boom") if self.fail_cleanup else httpx.Response(204)
        if method == "POST" and path == self.fail_create:
            return _error(422, "validation_error")
        if method == "POST" and path in ("/providers", "/collections"):
            return httpx.Response(201, json={"id": self._id(path.strip("/"))})
        if method == "POST" and path == "/sources":
            return self._create_source(request)
        if match := re.fullmatch(r"/sources/([^/]+)/sync", path):
            if self.sync_conflict:
                self.sources[match[1]]["last_run"] = {"id": "run-running"}
                return _error(409, "sync_already_running")
            if self.sync_error is not None:
                return _error(409, self.sync_error)
            return httpx.Response(202, json={"id": self._id("run"), "status": "queued"})
        if re.fullmatch(r"/sources/[^/]+/(tickets|cards)/upload", path):
            return self._upload(request)
        if match := re.fullmatch(r"/runs/([^/]+)", path):
            return self._run(match[1])
        if match := re.fullmatch(r"/sources/([^/]+)", path):
            return httpx.Response(200, json=self.sources[match[1]])
        if path == "/products":
            return httpx.Response(201, json=self._product(request))
        if path == "/levels":
            return httpx.Response(200, json={"items": [_level(lvl) for lvl in _LEVELS]})
        if match := re.fullmatch(r"/levels/([a-z_]+)", path):
            body = json.loads(request.content)
            if self.fail_cleanup and body.get("provider_id") is None:
                return _error(500, "boom")
            return httpx.Response(200, json=_level(match[1]) | body)
        if path == "/api-keys":
            return httpx.Response(201, json={"api_key": {"id": "key-1"}, "key": API_KEY})
        if path == "/api-keys/key-1/revoke":
            return _error(500, "boom") if self.fail_cleanup else httpx.Response(200, json={})
        return _error(404, "not_found")

    def _create_source(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        source_id = self._id("src")
        stats = None
        if body["name"].endswith("-codigo"):
            stats = {
                "chunks": 40,
                "dominant": [{"kind": "directory", "pattern": "gerado/**", "share": 0.6}],
            }
        self.sources[source_id] = {
            "id": source_id,
            "name": body["name"],
            "kind": body["kind"],
            "document_count": 3,
            "index_stats": stats,
            "last_run": None,
        }
        return httpx.Response(201, json={"id": source_id})

    def _upload(self, request: httpx.Request) -> httpx.Response:
        if b'filename="' not in request.content:
            return _error(422, "validation_error")
        run_id = None if self.upload_rejected else self._id("run")
        counts = {"queued": 5, "unchanged": 0, "stale": 0, "rejected": self.upload_rejected}
        return httpx.Response(200, json={"counts": counts, "run_id": run_id, "sync": "started"})

    def _run(self, run_id: str) -> httpx.Response:
        polls = self.polls.get(run_id, 0) + 1
        self.polls[run_id] = polls
        status = "running" if polls <= self.polls_before_done else self.run_status
        error = "disk full" if status == "failed" else None
        return httpx.Response(
            200, json={"id": run_id, "status": status, "chunks_written": 7, "error": error}
        )

    def _product(self, request: httpx.Request) -> dict[str, object]:
        body = json.loads(request.content)
        return {
            "id": "prod-1",
            "name": body["name"],
            "no_source_message": NO_SOURCE,
            "rerank": body["rerank"],
            "rerank_available": self.rerank_available,
            "min_similarity": body["min_similarity"],
            "effective_min_similarity": [
                {"embedding_model": "fake-embedding", "value": 0.35, "source": "fallback"}
            ],
        }

    def _public(self, request: httpx.Request, path: str) -> httpx.Response:
        if request.headers.get("authorization") != f"Bearer {API_KEY}":
            return _error(401, "invalid_api_key")
        if path == "/v1/conversations":
            return httpx.Response(201, json={"id": self._id("conv")})
        content = json.loads(request.content)["content"]
        if content == self.interrupt_on:
            raise KeyboardInterrupt
        answer = self.answers.get(content)
        if isinstance(answer, int):
            return _error(answer, "level_not_configured")
        body = answer if answer is not None else message(NO_SOURCE, status="no_source")
        message_id = self._id("msg")
        return httpx.Response(
            200, json={"user_message_id": "u", "message": body | {"id": message_id}}
        )


_LEVELS = ("end_user", "support", "product_dev")


def _level(level: str) -> dict[str, object]:
    return {
        "level": level,
        "provider_id": None,
        "model": None,
        "temperature": 0.2,
        "max_steps": 2,
    }


def _error(status: int, code: str) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": code, "details": None}})


class FakeClock:
    """Starts at a fixed instant; ``sleep`` advances the monotonic time without waiting."""

    def __init__(self) -> None:
        self._now = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)
        self._monotonic = 0.0
        self.sleeps = 0

    def now(self) -> datetime:
        current = self._now
        self._now += timedelta(minutes=5)
        return current

    def monotonic(self) -> float:
        return self._monotonic

    def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self._monotonic += seconds
