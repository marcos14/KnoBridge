"""Review and export of the knowledge items of a runner source (docs/specs/harness.md, "Revisão e
exportação"), under ``/v1/workspaces/{workspace_id}/sources/{source_id}/knowledge``.

- ``GET ...`` (any member): items by key, filters ``module``, ``review_status``, ``confidence``
  and ``kind``; paginated.
- ``PATCH .../{item_id}`` (editor+, with CSRF): edit the title and/or content (validated like a
  result, evidence never edited), ``approve`` (``revisado``), ``discard`` or ``reopen``; audited
  as ``knowledge_item.updated`` and, after the commit, the source sync is asked for (it starts
  now, or when the running one ends).
- ``GET .../export?module=`` (any member): a zip with one ``.md`` per item not discarded.

Logic in ``harness/knowledge.py``, ``harness/knowledge_export.py`` and the content shapes of
``api/runner_result_wire.py``.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Self
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from pydantic import ValidationError as PydanticValidationError

from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    WorkspaceContext,
    WorkspaceContextDep,
    require_role,
)
from knobridge.api.runner_result_wire import ModuleContent, RuleContent
from knobridge.api.runner_results import SourceSyncDep
from knobridge.api.runner_wire import ModuleKey
from knobridge.audit.models import JSONValue
from knobridge.core.errors import ValidationError
from knobridge.harness.knowledge import (
    ItemView,
    KnowledgeFilter,
    KnowledgeService,
    ReviewAction,
    ReviewChange,
)
from knobridge.harness.knowledge_export import export_zip
from knobridge.harness.models import (
    KnowledgeConfidence,
    KnowledgeItem,
    KnowledgeItemKind,
    KnowledgeReviewStatus,
)
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]
_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {
        "description": "Workspace, source (`source_not_found`) or module (`module_not_found`) "
        "not found, or caller is not a member."
    },
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below editor, workspace suspended or CSRF failure."},
    404: {"description": "Workspace or item (`knowledge_item_not_found`) not found."},
    422: {
        "description": "Invalid body (`validation_error`) or content that breaks the shape of "
        "the item kind (`knowledge_content_invalid`, details `[{loc, problem}]`)."
    },
}


class KnowledgeContentInvalidError(ValidationError):
    code = "knowledge_content_invalid"


class KnowledgeEvidenceOut(BaseModel):
    path: str
    start_line: int
    end_line: int
    symbol: str | None = None
    excerpt: str | None = None
    excerpt_truncated: bool = False
    excerpt_omitted: str | None = None
    redacted: bool = False


class KnowledgeItemOut(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    module_id: uuid.UUID
    module_key: str
    key: str
    kind: KnowledgeItemKind
    title: str
    # Shapes of docs/specs/harness.md by ``kind``; ``object`` keeps the OpenAPI non-recursive.
    content: dict[str, object]
    # ``{"title"?, "content"?}`` written in review; null while untouched.
    edited: dict[str, object] | None
    evidence: list[KnowledgeEvidenceOut]
    confidence: KnowledgeConfidence
    review_status: KnowledgeReviewStatus
    evidence_changed: bool
    commit_sha: str
    generated_by: str
    job_id: uuid.UUID | None
    updated_at: datetime


class KnowledgeItemPage(BaseModel):
    items: list[KnowledgeItemOut]
    total: int
    limit: int
    offset: int


class KnowledgeItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: ReviewAction | None = None
    title: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    # Whole content of the item kind (the shapes of the result), replacing the previous edit.
    content: dict[str, object] | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> Self:
        if self.action is None and self.title is None and self.content is None:
            raise ValueError("at least one of action, title or content is required")
        return self


def item_out(view: ItemView) -> KnowledgeItemOut:
    item = view.item
    return KnowledgeItemOut(
        id=item.id,
        source_id=item.source_id,
        module_id=item.module_id,
        module_key=view.module_key,
        key=item.key,
        kind=item.kind,
        title=item.title,
        content=dict(item.content),
        edited=None if item.edited is None else dict(item.edited),
        evidence=[
            KnowledgeEvidenceOut.model_validate(entry)
            for entry in item.evidence
            if isinstance(entry, dict)
        ],
        confidence=item.confidence,
        review_status=item.review_status,
        evidence_changed=item.evidence_changed,
        commit_sha=item.commit_sha,
        generated_by=item.generated_by,
        job_id=item.job_id,
        updated_at=item.updated_at,
    )


def validated_content(item: KnowledgeItem, content: dict[str, object]) -> dict[str, JSONValue]:
    """The edited content in the shape of the item's kind, as a result would carry it."""
    model = RuleContent if item.kind is KnowledgeItemKind.RULE else ModuleContent
    try:
        parsed = model.model_validate(content)
    except PydanticValidationError as exc:
        problems: list[JSONValue] = [
            {"loc": ["body", "content", *error["loc"]], "problem": error["msg"]}
            for error in exc.errors()
        ]
        raise KnowledgeContentInvalidError(
            "The content breaks the shape of the item.", details=problems
        ) from exc
    if isinstance(parsed, ModuleContent):
        entries = (*parsed.fluxo_principal, *parsed.mensagens, *parsed.faq)
        if any(index >= len(item.evidence) for entry in entries for index in entry.evidencias):
            raise KnowledgeContentInvalidError(
                "The content breaks the shape of the item.",
                details=[
                    {
                        "loc": ["body", "content"],
                        "problem": "evidencias must point at an evidence of the item",
                    }
                ],
            )
    dumped: dict[str, JSONValue] = parsed.model_dump(mode="json")
    return dumped


def _disposition(name: str) -> str:
    fallback = _UNSAFE_FILENAME.sub("_", name).strip("_") or "knowledge.zip"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"


def get_knowledge_service(clock: ClockDep) -> KnowledgeService:
    return KnowledgeService(clock)


KnowledgeServiceDep = Annotated[KnowledgeService, Depends(get_knowledge_service)]

router = APIRouter(prefix="/workspaces/{workspace_id}/sources/{source_id}", tags=["harness"])


@router.get("/knowledge", responses=_ERRORS)
async def list_knowledge_items(
    source_id: uuid.UUID,
    context: WorkspaceContextDep,
    service: KnowledgeServiceDep,
    module: ModuleKey | None = None,
    review_status: KnowledgeReviewStatus | None = None,
    confidence: KnowledgeConfidence | None = None,
    kind: KnowledgeItemKind | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KnowledgeItemPage:
    """Knowledge items of the source by key, discarded ones included unless filtered."""
    views, total = await service.list_items(
        context.db,
        workspace_id=context.workspace_id,
        source_id=source_id,
        filters=KnowledgeFilter(module, review_status, confidence, kind),
        limit=limit,
        offset=offset,
    )
    return KnowledgeItemPage(
        items=[item_out(view) for view in views], total=total, limit=limit, offset=offset
    )


@router.get(
    "/knowledge/export",
    response_class=Response,
    responses={
        200: {"description": "Zip of `.md` files.", "content": {"application/zip": {}}},
        **_ERRORS,
    },
)
async def export_knowledge(
    source_id: uuid.UUID,
    context: WorkspaceContextDep,
    service: KnowledgeServiceDep,
    module: ModuleKey | None = None,
) -> Response:
    """The items not discarded (of ``module``, when given) as ``<module>/<item>.md`` files."""
    source, entries = await service.export_entries(
        context.db, workspace_id=context.workspace_id, source_id=source_id, module=module
    )
    name = f"{source.name}.zip" if module is None else f"{source.name}-{module}.zip"
    return Response(
        content=export_zip(entries),
        media_type="application/zip",
        headers={"Content-Disposition": _disposition(name)},
    )


@router.patch("/knowledge/{item_id}", dependencies=[Depends(require_csrf)], responses=_WRITE_ERRORS)
async def review_knowledge_item(
    source_id: uuid.UUID,
    item_id: uuid.UUID,
    body: KnowledgeItemPatch,
    context: EditorContext,
    service: KnowledgeServiceDep,
    sync: SourceSyncDep,
    background: BackgroundTasks,
    ip: ClientIpDep,
) -> KnowledgeItemOut:
    """Edit, approve, discard or reopen the item; the source sync follows the commit."""
    view = await service.get(
        context.db, workspace_id=context.workspace_id, source_id=source_id, item_id=item_id
    )
    change = ReviewChange(
        action=body.action,
        title=body.title,
        content=None if body.content is None else validated_content(view.item, body.content),
    )
    await service.review(context.db, view, change, actor_id=context.current.user.id, ip=ip)
    # Background tasks run after the response, so after the commit the sync must see.
    background.add_task(sync, workspace_id=context.workspace_id, source_id=source_id)
    return item_out(view)
