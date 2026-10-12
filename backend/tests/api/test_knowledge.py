"""Review and export of knowledge items (``/v1/workspaces/{id}/sources/{sid}/knowledge``): list
with filters, edit, approve, discard and reopen with audit and the source sync after the commit,
the exported zip and workspace isolation."""

from __future__ import annotations

import io
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any

import pytest
from api_support import ApiEnv, SessionFactory, run_db
from index_support import IndexOverrides, IndexWorld, build_world, error_code, install
from runner_job_support import add_module
from runner_support import COMMIT, add_runner_source, create_runner

from knobridge.core.db import system_session
from knobridge.harness.models import (
    KnowledgeConfidence,
    KnowledgeItem,
    KnowledgeItemKind,
    KnowledgeReviewStatus,
)
from knobridge.ingestion.models import RunTrigger, Source
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

RULE_CONTENT: dict[str, Any] = {
    "enunciado": "A nota só é emitida se o cliente tiver CNPJ válido.",
    "quando": "Ao emitir a nota.",
    "mensagem": "Informe o CNPJ do cliente.",
    "resolucao": "Completar o cadastro.",
    "parametros": [],
    "classificacao": "intencional",
    "relevancia": "alta",
}
MODULE_CONTENT: dict[str, Any] = {
    "objetivo": "Emite notas.",
    "fluxo_principal": [{"ordem": 1, "passo": "Abrir o pedido.", "evidencias": [0]}],
    "mensagens": [],
    "faq": [],
    "duvidas": [],
}
EVIDENCE: list[Any] = [
    {
        "path": "src/faturamento/notas.ts",
        "start_line": 80,
        "end_line": 82,
        "symbol": "emitirNota",
        "excerpt": "if (!cnpj) {\n  throw x;\n}",
        "excerpt_truncated": False,
        "excerpt_omitted": None,
        "redacted": False,
    }
]


@dataclass(frozen=True)
class KnowledgeWorld:
    world: IndexWorld
    source_id: str
    module_id: str
    other_module_id: str
    overrides: IndexOverrides

    @property
    def path(self) -> str:
        return f"/v1/workspaces/{self.world.workspace_id}/sources/{self.source_id}/knowledge"


def _world(api: ApiEnv) -> KnowledgeWorld:
    """Admin (logged in) and viewer; a runner source with two modules."""
    overrides = install(api)
    world = build_world(api, Role.ADMIN, Role.VIEWER)
    runner_id, _ = create_runner(api, world.workspace_id)
    source_id = add_runner_source(api, world, runner_id)
    module_id = add_module(api, world, source_id)
    other = add_module(api, world, source_id, key="src-estoque")
    return KnowledgeWorld(world, source_id, module_id, other, overrides)


def _add_item(
    api: ApiEnv,
    kw: KnowledgeWorld,
    key: str,
    *,
    module_id: str | None = None,
    kind: KnowledgeItemKind = KnowledgeItemKind.RULE,
    **fields: Any,  # noqa: ANN401 - other columns
) -> str:
    async def scenario(factory: SessionFactory) -> str:
        async with system_session(factory) as db:
            item = KnowledgeItem(
                workspace_id=kw.world.workspace_id,
                source_id=uuid.UUID(kw.source_id),
                module_id=uuid.UUID(module_id or kw.module_id),
                kind=kind,
                key=key,
                title="Nota fiscal exige CNPJ" if kind is KnowledgeItemKind.RULE else "Faturamento",
                content=RULE_CONTENT if kind is KnowledgeItemKind.RULE else MODULE_CONTENT,
                evidence=EVIDENCE,
                commit_sha=COMMIT,
                generated_by="harness:claude_code:sonnet",
            )
            for name, value in fields.items():
                setattr(item, name, value)
            db.add(item)
            await db.flush()
            return str(item.id)

    return run_db(api.database_url, scenario)


def _stored(api: ApiEnv, item_id: str) -> KnowledgeItem:
    async def scenario(factory: SessionFactory) -> KnowledgeItem:
        async with system_session(factory) as db:
            return await db.get_one(KnowledgeItem, uuid.UUID(item_id))

    return run_db(api.database_url, scenario)


def _source(api: ApiEnv, source_id: str) -> Source:
    async def scenario(factory: SessionFactory) -> Source:
        async with system_session(factory) as db:
            return await db.get_one(Source, uuid.UUID(source_id))

    return run_db(api.database_url, scenario)


def _patch(api: ApiEnv, kw: KnowledgeWorld, item_id: str, body: dict[str, Any]) -> Any:  # noqa: ANN401
    return api.client.patch(f"{kw.path}/{item_id}", json=body, headers=api.csrf_headers())


def test_list_knowledge_items_with_filters(api: ApiEnv) -> None:
    kw = _world(api)
    rule = _add_item(api, kw, "src-faturamento.R001")
    _add_item(api, kw, "src-faturamento.E001", kind=KnowledgeItemKind.MODULE)
    _add_item(
        api,
        kw,
        "src-estoque.R001",
        module_id=kw.other_module_id,
        review_status=KnowledgeReviewStatus.DISCARDED,
    )
    _add_item(
        api,
        kw,
        "src-faturamento.R002",
        review_status=KnowledgeReviewStatus.APPROVED,
        confidence=KnowledgeConfidence.REVIEWED,
    )

    everything = api.client.get(kw.path)
    by_module = api.client.get(kw.path, params={"module": "src-estoque"})
    approved = api.client.get(kw.path, params={"review_status": "approved"})
    reviewed = api.client.get(kw.path, params={"confidence": "revisado"})
    modules = api.client.get(kw.path, params={"kind": "module"})
    page = api.client.get(kw.path, params={"limit": 1, "offset": 1})

    assert everything.status_code == 200
    body = everything.json()
    assert [item["key"] for item in body["items"]] == [
        "src-estoque.R001",
        "src-faturamento.E001",
        "src-faturamento.R001",
        "src-faturamento.R002",
    ]
    assert body["total"] == 4
    first_rule = body["items"][2]
    assert first_rule == {
        "id": rule,
        "source_id": kw.source_id,
        "module_id": kw.module_id,
        "module_key": "src-faturamento",
        "key": "src-faturamento.R001",
        "kind": "rule",
        "title": "Nota fiscal exige CNPJ",
        "content": RULE_CONTENT,
        "edited": None,
        "evidence": EVIDENCE,
        "confidence": "inferido",
        "review_status": "pending",
        "evidence_changed": False,
        "commit_sha": COMMIT,
        "generated_by": "harness:claude_code:sonnet",
        "job_id": None,
        "updated_at": first_rule["updated_at"],
    }
    assert [item["key"] for item in by_module.json()["items"]] == ["src-estoque.R001"]
    assert [item["key"] for item in approved.json()["items"]] == ["src-faturamento.R002"]
    assert [item["key"] for item in reviewed.json()["items"]] == ["src-faturamento.R002"]
    assert [item["key"] for item in modules.json()["items"]] == ["src-faturamento.E001"]
    assert (page.json()["total"], [i["key"] for i in page.json()["items"]]) == (
        4,
        ["src-faturamento.E001"],
    )


def test_list_knowledge_rejects_a_malformed_module_filter(api: ApiEnv) -> None:
    kw = _world(api)

    response = api.client.get(kw.path, params={"module": "Não Válido"})

    assert error_code(response) == (422, "validation_error")


def test_approve_sets_confidence_revisado(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(api, kw, "src-faturamento.R001", evidence_changed=True)

    response = _patch(api, kw, item_id, {"action": "approve"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["review_status"], body["confidence"], body["evidence_changed"]) == (
        "approved",
        "revisado",
        False,
    )
    stored = _stored(api, item_id)
    assert (stored.review_status, stored.confidence) == (
        KnowledgeReviewStatus.APPROVED,
        KnowledgeConfidence.REVIEWED,
    )
    [start] = kw.overrides.starter.started
    assert str(start.source_id) == kw.source_id
    assert (
        "knowledge_item.updated",
        {
            "item_key": "src-faturamento.R001",
            "source_id": kw.source_id,
            "action": "approve",
            "edited": [],
        },
    ) in api.workspace_audit(kw.world.workspace_id)


def test_review_sync_runs_with_the_harness_trigger(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(api, kw, "src-faturamento.R001")

    _patch(api, kw, item_id, {"action": "discard"})
    runs = api.client.get(
        f"/v1/workspaces/{kw.world.workspace_id}/sources/{kw.source_id}/runs"
    ).json()["items"]

    assert [run["trigger"] for run in runs] == [RunTrigger.HARNESS.value]


def test_review_while_a_sync_runs_leaves_it_pending(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(api, kw, "src-faturamento.R001")

    first = _patch(api, kw, item_id, {"action": "approve"})
    second = _patch(api, kw, item_id, {"title": "Nota pede CNPJ"})

    assert (first.status_code, second.status_code) == (200, 200)
    assert len(kw.overrides.starter.started) == 1
    assert _source(api, kw.source_id).sync_pending is True


def test_edit_title_and_content_writes_edited(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(api, kw, "src-faturamento.R001", evidence_changed=True)
    content = {**RULE_CONTENT, "enunciado": "Sem CNPJ, sem nota.", "mensagem": None}

    response = _patch(api, kw, item_id, {"title": "  Nota pede CNPJ ", "content": content})
    title_only = _patch(api, kw, item_id, {"title": "Outro"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["edited"] == {"title": "Nota pede CNPJ", "content": content}
    assert body["title"] == "Nota fiscal exige CNPJ"
    assert body["content"] == RULE_CONTENT
    assert body["evidence_changed"] is False
    assert body["review_status"] == "pending"
    assert title_only.json()["edited"] == {"title": "Outro", "content": content}
    events = api.workspace_audit(kw.world.workspace_id)
    assert (
        "knowledge_item.updated",
        {
            "item_key": "src-faturamento.R001",
            "source_id": kw.source_id,
            "action": None,
            "edited": ["title", "content"],
        },
    ) in events
    assert all("Sem CNPJ" not in str(details) for _, details in events)


def test_edit_module_content_checks_evidence_indexes(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(api, kw, "src-faturamento.E001", kind=KnowledgeItemKind.MODULE)
    valid = {**MODULE_CONTENT, "objetivo": "Emite e cancela notas."}
    broken = {
        **MODULE_CONTENT,
        "faq": [{"pergunta": "Por quê?", "resposta": "Porque sim.", "evidencias": [3]}],
    }

    ok = _patch(api, kw, item_id, {"content": valid, "action": "approve"})
    bad = _patch(api, kw, item_id, {"content": broken})

    assert ok.status_code == 200, ok.text
    assert ok.json()["edited"] == {"content": valid}
    assert ok.json()["review_status"] == "approved"
    assert error_code(bad) == (422, "knowledge_content_invalid")
    assert bad.json()["error"]["details"] == [
        {"loc": ["body", "content"], "problem": "evidencias must point at an evidence of the item"}
    ]


def test_edit_with_content_of_the_wrong_shape_is_422(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(api, kw, "src-faturamento.R001")

    response = _patch(api, kw, item_id, {"content": {**RULE_CONTENT, "relevancia": "enorme"}})

    assert error_code(response) == (422, "knowledge_content_invalid")
    [problem] = response.json()["error"]["details"]
    assert problem["loc"] == ["body", "content", "relevancia"]
    assert _stored(api, item_id).edited is None
    assert kw.overrides.starter.started == []


def test_discard_then_reopen(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(
        api,
        kw,
        "src-faturamento.R001",
        review_status=KnowledgeReviewStatus.APPROVED,
        confidence=KnowledgeConfidence.REVIEWED,
    )

    discarded = _patch(api, kw, item_id, {"action": "discard"})
    reopened = _patch(api, kw, item_id, {"action": "reopen"})

    assert (discarded.json()["review_status"], discarded.json()["confidence"]) == (
        "discarded",
        "revisado",
    )
    assert (reopened.json()["review_status"], reopened.json()["confidence"]) == (
        "pending",
        "inferido",
    )


def test_review_validation_roles_and_csrf(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(api, kw, "src-faturamento.R001")

    empty = _patch(api, kw, item_id, {})
    unknown = _patch(api, kw, item_id, {"action": "approve", "extra": 1})
    no_csrf = api.client.patch(f"{kw.path}/{item_id}", json={"action": "approve"})
    missing = _patch(api, kw, str(uuid.uuid4()), {"action": "approve"})
    api.login(kw.world.users[1])
    viewer_list = api.client.get(kw.path)
    viewer_patch = _patch(api, kw, item_id, {"action": "approve"})

    assert error_code(empty) == (422, "validation_error")
    assert error_code(unknown) == (422, "validation_error")
    assert error_code(no_csrf) == (403, "csrf_failed")
    assert error_code(missing) == (404, "knowledge_item_not_found")
    assert viewer_list.status_code == 200
    assert error_code(viewer_patch) == (403, "forbidden")
    assert _stored(api, item_id).review_status is KnowledgeReviewStatus.PENDING


def test_export_zip_has_frontmatter(api: ApiEnv) -> None:
    kw = _world(api)
    _add_item(api, kw, "src-faturamento.R001")
    _add_item(api, kw, "src-faturamento.E001", kind=KnowledgeItemKind.MODULE)
    _add_item(api, kw, "src-estoque.R001", module_id=kw.other_module_id)
    _add_item(api, kw, "src-faturamento.R002", review_status=KnowledgeReviewStatus.DISCARDED)
    source_name = _source(api, kw.source_id).name

    everything = api.client.get(f"{kw.path}/export")
    one_module = api.client.get(f"{kw.path}/export", params={"module": "src-faturamento"})

    assert everything.status_code == 200
    assert everything.headers["content-type"] == "application/zip"
    assert everything.headers["content-disposition"] == (
        f"attachment; filename=\"{source_name}.zip\"; filename*=UTF-8''{source_name}.zip"
    )
    with zipfile.ZipFile(io.BytesIO(everything.content)) as archive:
        assert archive.namelist() == [
            "src-estoque/src-estoque.R001.md",
            "src-faturamento/src-faturamento.E001.md",
            "src-faturamento/src-faturamento.R001.md",
        ]
        rule = archive.read("src-faturamento/src-faturamento.R001.md").decode()
    assert rule.startswith(
        "---\n"
        'id: "src-faturamento.R001"\n'
        'tipo: "regra"\n'
        'modulo: "src-faturamento"\n'
        "fontes:\n"
        '  - arquivo: "src/faturamento/notas.ts"\n'
        "    linha_inicial: 80\n"
        "    linha_final: 82\n"
        '    simbolo: "emitirNota"\n'
        'confianca: "inferido"\n'
        'gerado_por: "harness:claude_code:sonnet"\n'
        f'commit: "{COMMIT}"\n'
        'atualizado_em: "'
    )
    assert "---\n# Nota fiscal exige CNPJ\n\nA nota só é emitida" in rule
    assert one_module.headers["content-disposition"].startswith(
        f'attachment; filename="{source_name}-src-faturamento.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(one_module.content)) as archive:
        assert [name.split("/")[0] for name in archive.namelist()] == ["src-faturamento"] * 2


def test_export_of_an_unknown_module_is_404(api: ApiEnv) -> None:
    kw = _world(api)

    response = api.client.get(f"{kw.path}/export", params={"module": "nao-existe"})

    assert error_code(response) == (404, "module_not_found")


def test_knowledge_isolated_by_workspace(api: ApiEnv) -> None:
    kw = _world(api)
    item_id = _add_item(api, kw, "src-faturamento.R001")
    other = _world(api)  # logs in the other workspace's admin
    # The other workspace's own path with the first workspace's source and item ids.
    forged_path = f"/v1/workspaces/{other.world.workspace_id}/sources/{kw.source_id}/knowledge"

    as_member_of_other = (
        api.client.get(kw.path),
        api.client.get(f"{kw.path}/export"),
        _patch(api, kw, item_id, {"action": "approve"}),
    )
    forged = (
        api.client.get(forged_path),
        api.client.get(f"{forged_path}/export"),
        api.client.patch(
            f"{other.path}/{item_id}", json={"action": "approve"}, headers=api.csrf_headers()
        ),
    )

    assert [error_code(response) for response in as_member_of_other] == [(404, "not_found")] * 3
    assert error_code(forged[0]) == (404, "source_not_found")
    assert error_code(forged[1]) == (404, "source_not_found")
    assert error_code(forged[2]) == (404, "knowledge_item_not_found")
    assert _stored(api, item_id).review_status is KnowledgeReviewStatus.PENDING
