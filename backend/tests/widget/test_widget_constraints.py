"""Defaults, uniqueness, ``CHECK``s and foreign keys of ``widgets``, the widget owner of a
conversation and the visitor's feedback, against real Postgres."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from widget_support import Seeded, SessionFactory, new_widget, run_db, seed

from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Feedback,
    FeedbackRating,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.core.db import system_session
from knobridge.levels.level import ResponseLevel
from knobridge.products.models import Product
from knobridge.tenancy.models import User
from knobridge.widget.models import Widget, WidgetMode, WidgetPosition, WidgetTheme

pytestmark = pytest.mark.integration


def widget_conversation(seeded: Seeded, **fields: object) -> Conversation:
    values: dict[str, object] = {
        "widget_id": seeded.widget_id,
        "visitor_token_hash": "a" * 64,
        "channel": ConversationChannel.WIDGET,
        **fields,
    }
    return Conversation(
        workspace_id=seeded.workspace_id,
        product_id=seeded.product_id,
        level=ResponseLevel.END_USER,
        **values,
    )


def test_widget_defaults(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> Widget:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            widget = await db.get(Widget, seeded.widget_id)
            assert widget is not None
            return widget

    widget = run_db(app_database_url, scenario)

    assert widget.active is True
    assert (widget.mode, widget.position, widget.theme) == (
        WidgetMode.BUBBLE,
        WidgetPosition.BOTTOM_RIGHT,
        WidgetTheme.AUTO,
    )
    assert widget.primary_color == "#2563eb"
    assert widget.title is None
    assert widget.greeting == "Olá! Como posso ajudar?"
    assert widget.placeholder == "Escreva sua pergunta"
    assert (widget.feedback_enabled, widget.ticket_enabled) == (True, True)
    assert (widget.messages_per_ip_per_hour, widget.messages_per_day) == (30, 1000)
    assert widget.signing_secret_ciphertext is None


def _insert(database_url: str, **fields: object) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(new_widget(seeded.workspace_id, seeded.product_id, **fields))

    run_db(database_url, scenario)


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"public_key": "kbp_UPPERCASE00000000000000"},
        {"public_key": "kbk_abcdefghijklmnopqrstuvwx"},
        {"allowed_origins": []},
        {"allowed_origins": [f"https://s{n}.example" for n in range(51)]},
        {"allowed_origins": ["https://a.example", None]},
        {"primary_color": "#2563EB"},
        {"primary_color": "blue"},
        {"messages_per_ip_per_hour": 0},
        {"messages_per_ip_per_hour": 1001},
        {"messages_per_day": 0},
        {"messages_per_day": 100_001},
        {"signing_secret_ciphertext": "v1.x"},
    ],
)
def test_widget_checks_refuse_invalid_rows(
    app_database_url: str, fields: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError):
        _insert(app_database_url, **fields)


def test_widget_public_key_unique_in_instance(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        one, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            db.add(new_widget(other.workspace_id, other.product_id, public_key=one.public_key))

    with pytest.raises(IntegrityError, match="uq_widgets_public_key"):
        run_db(app_database_url, scenario)


def test_widget_name_unique_per_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        one, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            # Another workspace may repeat the name.
            db.add(new_widget(other.workspace_id, other.product_id, name="Site"))
            db.add(new_widget(one.workspace_id, one.product_id, name="Site"))
        async with system_session(factory) as db:
            db.add(new_widget(one.workspace_id, one.product_id, name="Site"))

    with pytest.raises(IntegrityError, match="uq_widgets_workspace_id_name"):
        run_db(app_database_url, scenario)


def test_widget_refuses_product_of_other_workspace(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        one, other = await seed(factory), await seed(factory)
        async with system_session(factory) as db:
            db.add(new_widget(one.workspace_id, other.product_id))

    with pytest.raises(IntegrityError, match="fk_widgets_workspace_id_products"):
        run_db(app_database_url, scenario)


def test_widget_deleted_with_its_product(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> Widget | None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            await db.execute(delete(Product).where(Product.id == seeded.product_id))
        async with system_session(factory) as db:
            return await db.get(Widget, seeded.widget_id)

    assert run_db(app_database_url, scenario) is None


def test_widget_conversation_deleted_with_the_widget(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> int:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(widget_conversation(seeded))
        async with system_session(factory) as db:
            await db.execute(delete(Widget).where(Widget.id == seeded.widget_id))
        async with system_session(factory) as db:
            count = await db.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.workspace_id == seeded.workspace_id)
            )
            return count or 0

    assert run_db(app_database_url, scenario) == 0


@pytest.mark.parametrize(
    "fields",
    [
        {"visitor_token_hash": None},
        {"widget_id": None},
        {"channel": ConversationChannel.PANEL},
    ],
)
def test_widget_conversation_checks(app_database_url: str, fields: dict[str, object]) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(widget_conversation(seeded, **fields))

    with pytest.raises(IntegrityError):
        run_db(app_database_url, scenario)


def test_widget_conversation_has_one_owner(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Ana")
            db.add(user)
            await db.flush()
            db.add(widget_conversation(seeded, user_id=user.id))

    with pytest.raises(IntegrityError, match="ck_conversations_one_owner"):
        run_db(app_database_url, scenario)


def test_widget_conversation_keeps_a_signed_identity(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> tuple[str | None, str | None]:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            conversation = widget_conversation(
                seeded,
                visitor_external_id="cliente-42",
                visitor_name="Ana Souza",
                visitor_email="ana@exemplo.com.br",
            )
            db.add(conversation)
            await db.flush()
            return conversation.visitor_name, conversation.visitor_email

    assert run_db(app_database_url, scenario) == ("Ana Souza", "ana@exemplo.com.br")


def test_visitor_identity_requires_its_sub(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            db.add(widget_conversation(seeded, visitor_external_id=None, visitor_name="Ana"))

    with pytest.raises(IntegrityError, match="ck_conversations_visitor_only_widget"):
        run_db(app_database_url, scenario)


def test_visitor_feedback_one_per_message(app_database_url: str) -> None:
    async def scenario(factory: SessionFactory) -> None:
        seeded = await seed(factory)
        async with system_session(factory) as db:
            conversation = widget_conversation(seeded)
            db.add(conversation)
            await db.flush()
            message = Message(
                workspace_id=seeded.workspace_id,
                conversation_id=conversation.id,
                position=0,
                role=MessageRole.ASSISTANT,
                content="Resposta",
                status=MessageStatus.COMPLETED,
                product_id=seeded.product_id,
                level=ResponseLevel.END_USER,
                channel=ConversationChannel.WIDGET,
            )
            db.add(message)
            await db.flush()
            for rating in (FeedbackRating.UP, FeedbackRating.DOWN):
                db.add(
                    Feedback(
                        workspace_id=seeded.workspace_id,
                        message_id=message.id,
                        user_id=None,
                        rating=rating,
                    )
                )
                await db.flush()

    with pytest.raises(IntegrityError, match="uq_feedback_message_id_visitor"):
        run_db(app_database_url, scenario)
