"""``POST .../sources/{sid}/tickets/upload``: JSON and JSONL files with the rules of the API, the
report by line, errors of the whole file, limits, roles, CSRF, audit and isolation."""

from __future__ import annotations

import json
import uuid
from collections.abc import Generator, Iterator
from typing import Any

import httpx2 as httpx
import pytest
from api_support import START, ApiEnv
from index_support import IndexOverrides, build_world, create_source, error_code, install
from index_support import source_path as path_of
from ingest_support import (
    TicketsWorld,
    delete,
    inbox,
    source_runs,
    ticket,
    tickets_world,
    upsert,
)

from knobridge.api import ticket_uploads
from knobridge.ingestion.models import RunTrigger
from knobridge.tenancy.models import Role
from knobridge.tickets import upload
from knobridge.tickets.models import TicketInboxState

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


@pytest.fixture
def tickets(api: ApiEnv, index: IndexOverrides) -> TicketsWorld:
    return tickets_world(api, Role.ADMIN, Role.EDITOR, Role.VIEWER)


def upload_path(world: TicketsWorld) -> str:
    return path_of(world.world, world.source_id, "tickets/upload")


def jsonl(*elements: object) -> bytes:
    return "".join(json.dumps(element) + "\n" for element in elements).encode()


def send(
    api: ApiEnv,
    world: TicketsWorld,
    content: bytes,
    filename: str = "tickets.jsonl",
    *,
    csrf: bool = True,
) -> httpx.Response:
    return api.client.post(
        upload_path(world),
        files={"file": (filename, content, "application/octet-stream")},
        headers=api.csrf_headers() if csrf else {},
    )


def uploaded(api: ApiEnv, world: TicketsWorld) -> list[dict[str, Any]]:
    return [
        details
        for action, details in api.workspace_audit(world.workspace_id)
        if action == "source.tickets_uploaded"
    ]


def test_upload_jsonl_queues_reports_by_line_and_starts_sync(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    content = jsonl(ticket("A-1"), upsert("A-2"), delete("A-3")) + b"\nnot json\n"
    content += jsonl(ticket("A-4", status="lost"))

    response = send(api, tickets, content)

    assert response.status_code == 200, response.text
    body = response.json()
    [started] = index.starter.started
    assert body == {
        "format": "jsonl",
        "total": 5,
        "counts": {"queued": 3, "unchanged": 0, "stale": 0, "rejected": 2},
        "errors": [
            {
                "line": 5,
                "index": None,
                "external_id": None,
                "code": "invalid_json",
                "message": "The line is not valid JSON.",
                "details": None,
            },
            {
                "line": 6,
                "index": None,
                "external_id": "A-4",
                "code": "validation_error",
                "message": "The item does not match the ticket format.",
                "details": [{"loc": ["status"], "problem": "enum"}],
            },
        ],
        "errors_truncated": False,
        "sync": "started",
        "run_id": str(started.run_id),
    }
    assert [run.trigger for run in source_runs(api, tickets.source_id)] == [RunTrigger.INGEST]
    entries = inbox(api, tickets.source_id)
    assert sorted(entries) == ["A-1", "A-2", "A-3"]
    assert entries["A-1"].state is TicketInboxState.PENDING
    assert entries["A-1"].received_at == START
    assert entries["A-3"].state is TicketInboxState.PENDING_DELETE


def test_upload_json_list_reports_by_index(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    content = json.dumps([ticket("B-1"), 7, {"op": "merge"}, upsert("B-1")]).encode()

    response = send(api, tickets, content, "export.JSON")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["format"], body["total"]) == ("json", 4)
    assert body["counts"] == {"queued": 1, "unchanged": 0, "stale": 0, "rejected": 3}
    assert [(e["line"], e["index"], e["code"], e["details"]) for e in body["errors"]] == [
        (None, 1, "validation_error", [{"loc": [], "problem": "model_type"}]),
        (None, 2, "validation_error", [{"loc": ["op"], "problem": "literal_error"}]),
        (None, 3, "duplicate_in_batch", {"first_index": 0}),
    ]
    assert sorted(inbox(api, tickets.source_id)) == ["B-1"]


def test_upload_json_items_object_like_the_api_body(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    content = json.dumps({"items": [upsert("C-1"), delete("C-2")]}).encode()

    response = send(api, tickets, content, "lote.json")

    assert response.status_code == 200, response.text
    assert response.json()["counts"]["queued"] == 2
    assert sorted(inbox(api, tickets.source_id)) == ["C-1", "C-2"]


def test_upload_many_blocks_with_duplicates_across_blocks(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(upload, "BATCH_SIZE", 2)
    content = jsonl(*(ticket(f"D-{n}") for n in range(5)), ticket("D-0"))

    response = send(api, tickets, content)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {"queued": 5, "unchanged": 0, "stale": 0, "rejected": 1}
    assert [(e["line"], e["code"], e["details"]) for e in body["errors"]] == [
        (6, "duplicate_in_batch", {"first_index": 1})
    ]
    assert len(inbox(api, tickets.source_id)) == 5


def test_upload_large_file_in_blocks_of_100(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    content = jsonl(*(ticket(f"L-{n:04d}") for n in range(250)))

    response = send(api, tickets, content)

    assert response.status_code == 200, response.text
    assert response.json()["counts"]["queued"] == 250
    assert len(inbox(api, tickets.source_id)) == 250
    assert len(index.starter.started) == 1


def test_upload_again_is_unchanged_without_sync(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    content = jsonl(ticket("E-1"))
    assert send(api, tickets, content).status_code == 200
    index.starter.finish(uuid.UUID(tickets.source_id))

    response = send(api, tickets, content)

    body = response.json()
    assert body["counts"] == {"queued": 0, "unchanged": 1, "stale": 0, "rejected": 0}
    assert (body["sync"], body["run_id"]) == ("none", None)
    assert len(index.starter.started) == 1


def test_upload_sync_pending_and_deferred(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    assert send(api, tickets, jsonl(ticket("F-1"))).json()["sync"] == "started"

    pending = send(api, tickets, jsonl(ticket("F-2")))
    index.starter.unavailable = True
    index.starter.finish(uuid.UUID(tickets.source_id))
    deferred = send(api, tickets, jsonl(ticket("F-3")))

    assert (pending.json()["sync"], pending.json()["run_id"]) == ("pending", None)
    assert (deferred.json()["sync"], deferred.json()["run_id"]) == ("deferred", None)


def test_upload_errors_are_truncated(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(upload, "MAX_ERRORS", 2)

    response = send(api, tickets, b"x\ny\nz\n")

    body = response.json()
    assert [e["line"] for e in body["errors"]] == [1, 2]
    assert body["errors_truncated"] is True
    assert body["counts"]["rejected"] == 3
    assert body["sync"] == "none"


def test_upload_is_audited_with_counts_only(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    content = jsonl(ticket("G-1", title="Senha do caixa da Ana"), {"bad": True})

    send(api, tickets, content, "export-setembro.jsonl")

    [details] = uploaded(api, tickets)
    assert details == {
        "name": details["name"],
        "filename": "export-setembro.jsonl",
        "format": "jsonl",
        "total": 2,
        "counts": {"queued": 1, "unchanged": 0, "stale": 0, "rejected": 1},
    }
    assert "Ana" not in json.dumps(details)


@pytest.mark.parametrize(
    ("content", "filename", "code"),
    [
        (b"[1, 2", "a.json", "upload_invalid_json"),
        (b'{"tickets": []}', "a.json", "upload_invalid_json"),
        (b"", "a.json", "upload_empty"),
        (b"[]", "a.json", "upload_empty"),
        (b"\n  \n", "a.jsonl", "upload_empty"),
        (b"external_id;title\n", "a.csv", "upload_format_unsupported"),
    ],
)
def test_upload_errors_of_the_whole_file_write_nothing(
    api: ApiEnv,
    index: IndexOverrides,
    tickets: TicketsWorld,
    content: bytes,
    filename: str,
    code: str,
) -> None:
    response = send(api, tickets, content, filename)

    assert error_code(response) == (422, code)
    assert inbox(api, tickets.source_id) == {}
    assert index.starter.started == []
    assert uploaded(api, tickets) == []


def test_upload_invalid_json_after_valid_elements_writes_nothing(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    content = json.dumps([ticket("H-1"), ticket("H-2")]).encode()[:-1] + b", }"

    response = send(api, tickets, content, "a.json")

    assert error_code(response) == (422, "upload_invalid_json")
    assert inbox(api, tickets.source_id) == {}


def test_upload_without_file_field_or_multipart(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    no_file = api.client.post(
        upload_path(tickets),
        data={"file": "not a file"},
        files={"other": ("a.jsonl", b"{}", "application/octet-stream")},
        headers=api.csrf_headers(),
    )
    as_json = api.client.post(upload_path(tickets), json=[], headers=api.csrf_headers())
    broken = api.client.post(
        upload_path(tickets),
        content=b"--x\r\nnot a part",
        headers={**api.csrf_headers(), "content-type": "multipart/form-data"},
    )

    assert error_code(no_file) == (422, "validation_error")
    assert no_file.json()["error"]["details"] == [{"loc": ["body", "file"], "problem": "missing"}]
    assert as_json.json()["error"]["details"] == [
        {"loc": ["body", "file"], "problem": "multipart_required"}
    ]
    assert broken.json()["error"]["details"] == [
        {"loc": ["body", "file"], "problem": "multipart_invalid"}
    ]


def _shrink(monkeypatch: pytest.MonkeyPatch, *, file: int, envelope: int) -> None:
    monkeypatch.setattr(ticket_uploads, "UPLOAD_MAX_BYTES", file)
    monkeypatch.setattr(ticket_uploads, "ENVELOPE_BYTES", envelope)


def test_upload_413_by_declared_length(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    _shrink(monkeypatch, file=1000, envelope=100)

    response = send(api, tickets, jsonl(*(ticket(f"I-{n}") for n in range(20))))

    assert error_code(response) == (413, "payload_too_large")
    assert response.json()["error"]["details"] == {"max_bytes": 1000}
    assert inbox(api, tickets.source_id) == {}


def test_upload_413_while_streaming_without_length(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    _shrink(monkeypatch, file=1000, envelope=100)

    def body() -> Iterator[bytes]:
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.jsonl"\r\n\r\n'
        for n in range(50):
            yield jsonl(ticket(f"J-{n}"))
        yield b"\r\n--b--\r\n"

    response = api.client.post(
        upload_path(tickets),
        content=body(),
        headers={**api.csrf_headers(), "content-type": "multipart/form-data; boundary=b"},
    )

    assert error_code(response) == (413, "payload_too_large")
    assert inbox(api, tickets.source_id) == {}


def test_upload_413_by_file_size(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    _shrink(monkeypatch, file=100, envelope=10_000)

    response = send(api, tickets, jsonl(ticket("K-1")))

    assert error_code(response) == (413, "payload_too_large")
    assert inbox(api, tickets.source_id) == {}


@pytest.mark.parametrize(("user", "status"), [(1, 200), (2, 403)])
def test_upload_needs_editor(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld, user: int, status: int
) -> None:
    api.login(tickets.world.users[user])

    response = send(api, tickets, jsonl(ticket("M-1")))

    assert response.status_code == status, response.text


def test_upload_needs_csrf(api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld) -> None:
    response = send(api, tickets, jsonl(ticket("N-1")), csrf=False)

    assert error_code(response) == (403, "csrf_failed")
    assert inbox(api, tickets.source_id) == {}


def test_upload_to_inactive_source_is_409(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    deactivated = api.client.patch(
        path_of(tickets.world, tickets.source_id),
        json={"active": False},
        headers=api.csrf_headers(),
    )
    assert deactivated.status_code == 200, deactivated.text

    response = send(api, tickets, jsonl(ticket("O-1")))

    assert error_code(response) == (409, "source_inactive")
    assert inbox(api, tickets.source_id) == {}


def test_upload_to_folder_source_is_404(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    folder = create_source(api, tickets.world)

    response = api.client.post(
        path_of(tickets.world, folder, "tickets/upload"),
        files={"file": ("a.jsonl", jsonl(ticket()), "application/octet-stream")},
        headers=api.csrf_headers(),
    )

    assert error_code(response) == (404, "source_not_found")


def test_upload_to_other_workspace_source_is_404(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    other = build_world(api, Role.ADMIN)

    # The other workspace's admin names this workspace's source under their own workspace.
    response = api.client.post(
        path_of(other, tickets.source_id, "tickets/upload"),
        files={"file": ("a.jsonl", jsonl(ticket()), "application/octet-stream")},
        headers=api.csrf_headers(),
    )
    foreign = api.client.post(
        upload_path(tickets),
        files={"file": ("a.jsonl", jsonl(ticket()), "application/octet-stream")},
        headers=api.csrf_headers(),
    )

    assert error_code(response) == (404, "source_not_found")
    assert error_code(foreign) == (404, "not_found")
    assert inbox(api, tickets.source_id) == {}
