"""Level configuration of a workspace (``/v1/workspaces/{workspace_id}/levels``;
``docs/specs/produtos-e-niveis.md``, "Configuração dos níveis no workspace").

Owners and admins read the three levels and change the credential, model, temperature and
instructions of one. ``provider_id`` and ``model`` are set or cleared together (422
``validation_error``); the provider must be a credential of the workspace (422
``level_provider_invalid``). ``instructions: null`` restores the KnoBridge default text, which
every answer also carries in ``default_instructions``. ``price`` and
``estimated_cost_per_answer_usd`` (a reference answer of 4000 input and 600 output tokens) come
from the chat price table (``KNOBRIDGE_CHAT_PRICES``). ``max_steps`` (1 to 6) is the most
searches of an answer (multi-step search), with ``estimated_max_cost_per_answer_usd`` for an
answer that uses them all; ``tools_supported`` is ``false`` once the level's model refused tool
calls (changing the model or the credential clears the mark).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StringConstraints, model_validator

from knobridge.api.deps import ClientIpDep, WorkspaceContext, get_settings_from_app, require_role
from knobridge.levels.level import (
    MAX_MAX_STEPS,
    MAX_TEMPERATURE,
    MIN_MAX_STEPS,
    MIN_TEMPERATURE,
    ResponseLevel,
)
from knobridge.levels.workspace import LevelChanges, LevelView, WorkspaceLevelService
from knobridge.llm.chat_pricing import ChatPriceTable
from knobridge.llm.models import ProviderKind
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]


def get_workspace_level_service(request: Request) -> WorkspaceLevelService:
    prices = ChatPriceTable.from_settings(get_settings_from_app(request))
    return WorkspaceLevelService(request.app.state.clock, prices)


WorkspaceLevelServiceDep = Annotated[WorkspaceLevelService, Depends(get_workspace_level_service)]

# Identifier as the provider knows it: no spaces (``gpt-4.1-mini``, ``vendor/model:tag``).
ModelId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200, pattern=r"^\S+$")
]
Temperature = Annotated[float, Field(ge=MIN_TEMPERATURE, le=MAX_TEMPERATURE, allow_inf_nan=False)]
Instructions = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)]
MaxSteps = Annotated[int, Field(ge=MIN_MAX_STEPS, le=MAX_MAX_STEPS, strict=True)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below admin (`forbidden`) or workspace suspended."},
    404: {"description": "Workspace not found or caller is not a member."},
}


class LevelPrice(BaseModel):
    """USD per million tokens of the level's model."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float


class WorkspaceLevelOut(BaseModel):
    level: ResponseLevel
    provider_id: uuid.UUID | None
    provider_name: str | None
    provider_kind: ProviderKind | None
    model: str | None
    temperature: float
    # Always the effective text: the workspace's or, when it kept the default, the default.
    instructions: str
    instructions_is_default: bool
    default_instructions: str
    # Provider and model set: answers at this level can be generated.
    configured: bool
    price: LevelPrice | None
    estimated_cost_per_answer_usd: float | None
    updated_at: datetime
    # Most searches of an answer (multi-step search, plan 0011); the defaults keep the
    # fields additive in the published schema.
    max_steps: int = 1
    # A reference answer that uses every step (``null`` without a price).
    estimated_max_cost_per_answer_usd: float | None = None
    # ``false`` when the level's model refused tool calls; ``null`` while unknown.
    tools_supported: bool | None = None


class WorkspaceLevelList(BaseModel):
    items: list[WorkspaceLevelOut]


class WorkspaceLevelUpdate(BaseModel):
    """Omitted fields stay; ``provider_id`` and ``model`` null clear them (together), and
    ``instructions`` null restores the default text."""

    provider_id: uuid.UUID | None = None
    model: ModelId | None = None
    temperature: Temperature | None = None
    instructions: Instructions | None = None
    max_steps: MaxSteps | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> WorkspaceLevelUpdate:
        if not self.model_fields_set:
            raise ValueError("Give at least one field to change.")
        for name in ("temperature", "max_steps"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


def _out(view: LevelView) -> WorkspaceLevelOut:
    price = (
        None
        if view.price is None
        else LevelPrice(
            input_usd_per_mtok=float(view.price.input),
            output_usd_per_mtok=float(view.price.output),
        )
    )
    return WorkspaceLevelOut(
        level=view.level,
        provider_id=view.provider_id,
        provider_name=view.provider_name,
        provider_kind=view.provider_kind,
        model=view.model,
        temperature=view.temperature,
        instructions=view.instructions,
        instructions_is_default=view.instructions_is_default,
        default_instructions=view.default_instructions,
        configured=view.configured,
        price=price,
        estimated_cost_per_answer_usd=(
            None
            if view.estimated_cost_per_answer_usd is None
            else float(view.estimated_cost_per_answer_usd)
        ),
        updated_at=view.updated_at,
        max_steps=view.max_steps,
        estimated_max_cost_per_answer_usd=(
            None
            if view.estimated_max_cost_per_answer_usd is None
            else float(view.estimated_max_cost_per_answer_usd)
        ),
        tools_supported=view.tools_supported,
    )


router = APIRouter(prefix="/workspaces/{workspace_id}/levels", tags=["levels"])


@router.get("", responses=_ERRORS)
async def list_levels(
    context: AdminContext, levels: WorkspaceLevelServiceDep
) -> WorkspaceLevelList:
    """The three levels of the workspace, in order (``end_user``, ``support``,
    ``product_dev``)."""
    views = await levels.list_levels(context.db, workspace_id=context.workspace_id)
    return WorkspaceLevelList(items=[_out(view) for view in views])


@router.patch(
    "/{level}",
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        403: {
            "description": "Role below admin (`forbidden`), workspace suspended or CSRF failure "
            "(`csrf_failed`)."
        },
        422: {
            "description": "Invalid body or level, provider and model not set together "
            "(`validation_error`) or provider not in the workspace (`level_provider_invalid`)."
        },
    },
)
async def update_level(
    level: ResponseLevel,
    body: WorkspaceLevelUpdate,
    context: AdminContext,
    levels: WorkspaceLevelServiceDep,
    ip: ClientIpDep,
) -> WorkspaceLevelOut:
    """Change the credential, model, temperature or instructions of a level."""
    given = body.model_fields_set
    view = await levels.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        level=level,
        changes=LevelChanges(
            provider_id=body.provider_id,
            provider_id_given="provider_id" in given,
            model=body.model,
            model_given="model" in given,
            temperature=body.temperature,
            instructions=body.instructions,
            instructions_given="instructions" in given,
            max_steps=body.max_steps,
        ),
        ip=ip,
    )
    return _out(view)
