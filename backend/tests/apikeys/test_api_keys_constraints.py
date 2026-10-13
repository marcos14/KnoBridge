"""``api_keys`` against real Postgres: unique prefix in the instance, unique name in the
workspace, the ``CHECK``s and what happens when the creator, a key or the workspace goes."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from apikeys_support import SessionFactory, new_key, run_db, seed
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from knobridge.apikeys.models import ApiKey
from knobridge.conversations.models import Conversation
from knobridge.core.db import system_session
from knobridge.tenancy.models import User, Workspace

pytestmark = pytest.mark.integration


def _insert(app_database_url: str, build: Callable[[uuid.UUID], ApiKey]) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(build(seeded.workspace_id))
            await db.flush()

    run_db(app_database_url, scenario)


def test_api_key_defaults_to_every_assistant_and_not_revoked(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> ApiKey:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            key = new_key(seeded.workspace_id)
            db.add(key)
            await db.flush()
            await db.refresh(key)
            return key

    key = run_db(app_database_url, scenario)

    assert key.assistant_ids is None
    assert key.last_used_at is None
    assert key.revoked_at is None


def test_api_key_prefix_is_unique_in_the_instance(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            db.add(new_key(other.workspace_id, prefix=own.key_prefix))
            await db.flush()

    with pytest.raises(IntegrityError, match="uq_api_keys_key_prefix"):
        run_db(app_database_url, scenario)


def test_api_key_name_is_unique_in_the_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(new_key(seeded.workspace_id, name="ERP"))
            await db.flush()
            db.add(new_key(seeded.workspace_id, name="ERP"))
            await db.flush()

    with pytest.raises(IntegrityError, match="uq_api_keys_workspace_id_name"):
        run_db(app_database_url, scenario)


def test_api_key_name_repeats_across_workspaces(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> int:
        own, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            db.add_all(
                [new_key(own.workspace_id, name="ERP"), new_key(other.workspace_id, name="ERP")]
            )
            await db.flush()
            return len(
                (
                    await db.scalars(
                        select(ApiKey.id).where(
                            ApiKey.name == "ERP",
                            ApiKey.workspace_id.in_([own.workspace_id, other.workspace_id]),
                        )
                    )
                ).all()
            )

    assert run_db(app_database_url, scenario) == 2


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("name", "", "ck_api_keys_name_not_empty"),
        ("key_prefix", "ABCD1234", "ck_api_keys_key_prefix_format"),
        ("key_prefix", "abc123", "ck_api_keys_key_prefix_format"),
        ("key_hash", "z" * 64, "ck_api_keys_key_hash_format"),
        ("assistant_ids", [], "ck_api_keys_product_ids_size"),
        ("assistant_ids", [uuid.uuid4() for _ in range(101)], "ck_api_keys_product_ids_size"),
        ("assistant_ids", [uuid.uuid4(), None], "ck_api_keys_product_ids_size"),
    ],
)
def test_api_key_checks_refuse_invalid_values(
    app_database_url: str, field: str, value: object, constraint: str
) -> None:
    def build(workspace_id: uuid.UUID) -> ApiKey:
        key = new_key(workspace_id)
        setattr(key, field, value)
        return key

    with pytest.raises(IntegrityError, match=constraint):
        _insert(app_database_url, build)


def test_api_key_accepts_a_scope_of_one_hundred_assistants(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> int:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            key = new_key(seeded.workspace_id, assistant_ids=[uuid.uuid4() for _ in range(100)])
            db.add(key)
            await db.flush()
            await db.refresh(key)
            return len(key.assistant_ids or [])

    assert run_db(app_database_url, scenario) == 100


def test_api_key_keeps_creator_null_when_the_user_is_deleted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> uuid.UUID | None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(User).where(User.id == seeded.user_id))
            return await db.scalar(select(ApiKey.created_by).where(ApiKey.id == seeded.key_id))

    assert run_db(app_database_url, scenario) is None


def test_api_key_with_conversations_cannot_be_deleted(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(ApiKey).where(ApiKey.id == seeded.key_id))

    with pytest.raises(IntegrityError, match="fk_conversations_workspace_id_api_keys"):
        run_db(app_database_url, scenario)


def test_deleting_the_workspace_deletes_keys_and_their_conversations(
    app_database_url: str,
) -> None:
    async def scenario(factory: SessionFactory) -> tuple[int, int]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Workspace).where(Workspace.id == seeded.workspace_id))
            keys = len(
                (await db.scalars(select(ApiKey.id).where(ApiKey.id == seeded.key_id))).all()
            )
            conversations = len(
                (
                    await db.scalars(
                        select(Conversation.id).where(Conversation.id == seeded.conversation_id)
                    )
                ).all()
            )
            return keys, conversations

    assert run_db(app_database_url, scenario) == (0, 0)
