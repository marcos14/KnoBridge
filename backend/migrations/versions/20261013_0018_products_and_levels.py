"""Turn assistants into products and add the response levels.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-13 00:00:00

Contract in docs/specs/produtos-e-niveis.md, decision in docs/adr/0008-produtos-e-niveis.md.

- ``assistants`` becomes ``products`` with the same ids (``system_prompt`` is now
  ``instructions``), ``assistant_collections`` becomes ``product_collections``, and
  ``conversations``, ``ticket_requests`` and ``api_keys`` point at the product with the same
  values. Webhook secrets are not re-encrypted: their associated data keeps the old
  ``assistant_ticket_webhook:<workspace_id>:<id>`` label, and the id did not change. A product
  name cannot end in ``:<level>`` (it is a ``model`` of the OpenAI-compatible API): such names
  get ``" - <level>"`` instead.
- ``credential_id``, ``model`` and ``temperature`` stay on ``products`` for now (plan 0009,
  F1.2): the chat still reads them until it reads the level configuration.
- ``workspace_levels``: three rows per workspace, with the credential, model and temperature of
  the most used assistant of the workspace (most answers with a model; ties by the oldest, then
  the id); none without assistants. Instructions stay ``NULL`` (the default text).
- ``member_product_levels``: empty; a member without a row has the default of the role.
- Conversations, their messages and the API keys get ``product_dev``: until now every answer
  used every source.
- ``sources.min_level`` by kind; ``documents.min_level`` for code in folders (``product_dev``)
  and inferred knowledge (``support``); ``chunks.meta.min_level`` = ``support`` in the evidence
  section of knowledge; ``chunks.min_level`` = the highest of the three.
- ``sources.kind`` accepts ``cards`` and ``documents.kind``/``run_items.document_kind``
  accept ``card`` (docs/specs/cards.md); ``invitations.product_levels`` keeps the levels of an
  invitation.

The migration role owns the tables, which have forced RLS, so data steps run in system mode
(``app.system`` local to the transaction). The downgrade fails while anything the old schema
cannot hold exists: a product created after the migration, a conversation or key below
``product_dev``, a recorded member level, an invitation with levels or a ``cards`` source.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
_SYSTEM = "coalesce(current_setting('app.system', true), '') = 'on'"
_POLICY = f"workspace_id = {_WORKSPACE} OR {_SYSTEM}"
_LEVELS = "'end_user', 'support', 'product_dev'"
_LEVEL_SUFFIX = ":(end_user|support|product_dev)$"
_NEW_TABLES = ("workspace_levels", "member_product_levels")

# (old, new) names of what ``assistants`` and ``assistant_collections`` own.
_PRODUCT_CONSTRAINTS = (
    ("pk_assistants", "pk_products"),
    ("uq_assistants_workspace_id_name", "uq_products_workspace_id_name"),
    ("uq_assistants_workspace_id_id", "uq_products_workspace_id_id"),
    ("fk_assistants_workspace_id_workspaces", "fk_products_workspace_id_workspaces"),
    (
        "fk_assistants_workspace_id_provider_credentials",
        "fk_products_workspace_id_provider_credentials",
    ),
    ("ck_assistants_ck_assistants_tone", "ck_products_tone"),
    ("ck_assistants_ck_assistants_temperature_range", "ck_products_temperature_range"),
    (
        "ck_assistants_ck_assistants_no_source_message_not_empty",
        "ck_products_no_source_message_not_empty",
    ),
    ("ck_assistants_ck_assistants_min_similarity_range", "ck_products_min_similarity_range"),
    ("ck_assistants_ticket_webhook_url_scheme", "ck_products_ticket_webhook_url_scheme"),
    ("ck_assistants_ticket_webhook_secret_dated", "ck_products_ticket_webhook_secret_dated"),
)
_COLLECTION_CONSTRAINTS = (
    ("pk_assistant_collections", "pk_product_collections"),
    (
        "fk_assistant_collections_workspace_id_workspaces",
        "fk_product_collections_workspace_id_workspaces",
    ),
    (
        "fk_assistant_collections_workspace_id_assistants",
        "fk_product_collections_workspace_id_products",
    ),
    (
        "fk_assistant_collections_workspace_id_collections",
        "fk_product_collections_workspace_id_collections",
    ),
)
_PRODUCT_POLICIES = ("select", "insert", "update", "delete")


def _system_mode(*, on: bool) -> None:
    value = "on" if on else ""
    op.execute(f"SELECT set_config('app.system', '{value}', true)")


def _rank(expression: str) -> str:
    """Position of a level (1 to 3; ``NULL`` for ``NULL``), so ``GREATEST`` orders levels."""
    return f"array_position(ARRAY[{_LEVELS}]::text[], {expression})"


def _rename_products(*, forward: bool) -> None:
    old, new = ("assistants", "products") if forward else ("products", "assistants")
    op.rename_table(old, new)
    op.alter_column(
        new,
        "system_prompt" if forward else "instructions",
        new_column_name="instructions" if forward else "system_prompt",
    )
    for before, after in _PRODUCT_CONSTRAINTS:
        source, target = (before, after) if forward else (after, before)
        op.execute(f"ALTER TABLE {new} RENAME CONSTRAINT {source} TO {target}")
    for action in _PRODUCT_POLICIES:
        op.execute(f"ALTER POLICY {old}_{action} ON {new} RENAME TO {new}_{action}")


def _rename_collections(*, forward: bool) -> None:
    old, new = (
        ("assistant_collections", "product_collections")
        if forward
        else ("product_collections", "assistant_collections")
    )
    op.rename_table(old, new)
    op.alter_column(
        new,
        "assistant_id" if forward else "product_id",
        new_column_name="product_id" if forward else "assistant_id",
    )
    for before, after in _COLLECTION_CONSTRAINTS:
        source, target = (before, after) if forward else (after, before)
        op.execute(f"ALTER TABLE {new} RENAME CONSTRAINT {source} TO {target}")
    index = "ix_{}_workspace_id_collection_id"
    op.execute(f"ALTER INDEX {index.format(old)} RENAME TO {index.format(new)}")
    op.execute(f"ALTER POLICY {old}_workspace ON {new} RENAME TO {new}_workspace")


def _rename_references(*, forward: bool) -> None:
    """The columns that point at the product keep their values under the new names."""
    for table, column in (("conversations", "assistant_id"), ("ticket_requests", "assistant_id")):
        op.alter_column(
            table,
            column if forward else "product_id",
            new_column_name="product_id" if forward else column,
        )
        before, after = f"fk_{table}_workspace_id_assistants", f"fk_{table}_workspace_id_products"
        source, target = (before, after) if forward else (after, before)
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {source} TO {target}")
    op.alter_column(
        "api_keys",
        "assistant_ids" if forward else "product_ids",
        new_column_name="product_ids" if forward else "assistant_ids",
    )
    before, after = "ck_api_keys_assistant_ids_size", "ck_api_keys_product_ids_size"
    source, target = (before, after) if forward else (after, before)
    op.execute(f"ALTER TABLE api_keys RENAME CONSTRAINT {source} TO {target}")


def _rename_level_suffixes() -> None:
    """``ERP:support`` becomes ``ERP - support`` (or ``... (2)`` if that name is taken)."""
    op.execute(
        f"""
        DO $$
        DECLARE
            item record;
            suffix text;
            base text;
            candidate text;
            attempt integer;
        BEGIN
            FOR item IN
                SELECT id, workspace_id, name FROM products
                WHERE name ~ '{_LEVEL_SUFFIX}' ORDER BY created_at, id
            LOOP
                suffix := ' - ' || substring(item.name FROM '{_LEVEL_SUFFIX}');
                base := left(regexp_replace(item.name, '{_LEVEL_SUFFIX}', ''),
                             200 - length(suffix)) || suffix;
                candidate := base;
                attempt := 1;
                WHILE EXISTS (
                    SELECT 1 FROM products
                    WHERE workspace_id = item.workspace_id AND name = candidate
                ) LOOP
                    attempt := attempt + 1;
                    candidate := left(base, 200 - length(' (' || attempt || ')'))
                                 || ' (' || attempt || ')';
                END LOOP;
                UPDATE products SET name = candidate WHERE id = item.id;
            END LOOP;
        END $$
        """  # noqa: S608 - constant fragments, no input
    )
    op.create_check_constraint("name_without_level", "products", f"name !~ '{_LEVEL_SUFFIX}'")


def _add_level_column(table: str, column: str, *, fill: str | None, nullable: bool) -> None:
    op.add_column(table, sa.Column(column, sa.String(32), nullable=True))
    if fill is not None:
        op.execute(f"UPDATE {table} SET {column} = {fill}")  # noqa: S608 - constant fragments
    if not nullable:
        op.alter_column(table, column, existing_type=sa.String(32), nullable=False)
    op.create_check_constraint(column, table, f"{column} IN ({_LEVELS})")


def _add_conversation_levels() -> None:
    _add_level_column("conversations", "level", fill="'product_dev'", nullable=False)
    op.add_column("messages", sa.Column("product_id", sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE messages SET product_id = c.product_id FROM conversations c"
        " WHERE c.id = messages.conversation_id"
    )
    op.alter_column("messages", "product_id", existing_type=sa.Uuid(), nullable=False)
    _add_level_column("messages", "level", fill="'product_dev'", nullable=False)
    _add_level_column("api_keys", "max_level", fill="'product_dev'", nullable=False)


def _create_workspace_levels() -> None:
    op.create_table(
        "workspace_levels",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.String(32), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("temperature", sa.Float(), server_default=sa.text("0.2"), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"level IN ({_LEVELS})", name="level"),
        sa.CheckConstraint(
            "(credential_id IS NULL) = (model IS NULL)", name="model_with_credential"
        ),
        sa.CheckConstraint("temperature >= 0.0 AND temperature <= 2.0", name="temperature_range"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_workspace_levels_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["provider_credentials.workspace_id", "provider_credentials.id"],
            name="fk_workspace_levels_workspace_id_provider_credentials",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "level", name="pk_workspace_levels"),
    )
    op.create_index(
        "ix_workspace_levels_workspace_id_credential_id",
        "workspace_levels",
        ["workspace_id", "credential_id"],
    )
    # The model of the most used assistant (answers that called the LLM) on all three levels.
    op.execute(
        f"""
        INSERT INTO workspace_levels (workspace_id, level, credential_id, model, temperature)
        SELECT w.id, l.level, top.credential_id, top.model, coalesce(top.temperature, 0.2)
        FROM workspaces w
        CROSS JOIN unnest(ARRAY[{_LEVELS}]::text[]) AS l(level)
        LEFT JOIN LATERAL (
            SELECT p.credential_id, p.model, p.temperature
            FROM products p
            WHERE p.workspace_id = w.id
            ORDER BY (
                SELECT count(*) FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE c.product_id = p.id AND m.model IS NOT NULL
            ) DESC, p.created_at, p.id
            LIMIT 1
        ) top ON true
        """  # noqa: S608 - constant fragments, no input
    )


def _create_member_product_levels() -> None:
    op.create_table(
        "member_product_levels",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("max_level", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"max_level IN ({_LEVELS})", name="max_level"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_member_product_levels_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "product_id"],
            ["products.workspace_id", "products.id"],
            name="fk_member_product_levels_workspace_id_products",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            name="fk_member_product_levels_workspace_id_memberships",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("product_id", "user_id", name="pk_member_product_levels"),
    )
    op.create_index(
        "ix_member_product_levels_workspace_id_user_id",
        "member_product_levels",
        ["workspace_id", "user_id"],
    )


def _add_index_levels() -> None:
    _add_level_column(
        "sources",
        "min_level",
        fill=(
            "CASE kind WHEN 'folder' THEN 'end_user' WHEN 'runner' THEN 'end_user'"
            " WHEN 'tickets' THEN 'support' ELSE 'product_dev' END"
        ),
        nullable=False,
    )
    _add_level_column("documents", "min_level", fill=None, nullable=True)
    # Code in a folder (its chunks carry the language) is for development only.
    op.execute(
        "UPDATE documents d SET min_level = 'product_dev' FROM sources s"
        " WHERE s.id = d.source_id AND s.kind = 'folder' AND EXISTS ("
        "SELECT 1 FROM chunks c WHERE c.document_id = d.id AND c.meta ->> 'language' IS NOT NULL)"
    )
    op.execute(
        "UPDATE documents SET min_level = 'support'"
        " WHERE kind = 'knowledge' AND meta ->> 'confidence' = 'inferido'"
    )
    # The evidence of a knowledge item (paths and code excerpts) is for support up.
    op.execute(
        """UPDATE chunks c SET meta = c.meta || '{"min_level": "support"}'::jsonb"""
        " FROM documents d WHERE d.id = c.document_id AND d.kind = 'knowledge'"
        """ AND c.meta -> 'headings' @> '["Evidências"]'::jsonb"""
    )
    # New chunks default to the highest level: one written without a level is never shown low.
    op.add_column(
        "chunks",
        sa.Column("min_level", sa.String(32), server_default="product_dev", nullable=False),
    )
    op.create_check_constraint("min_level", "chunks", f"min_level IN ({_LEVELS})")
    highest = (
        f"(ARRAY[{_LEVELS}]::text[])[GREATEST({_rank('s.min_level')}, {_rank('d.min_level')},"
        f" {_rank("c.meta ->> 'min_level'")})]"
    )
    update = f"UPDATE chunks c SET min_level = {highest}"  # noqa: S608 - constant fragments
    op.execute(
        f"{update} FROM documents d JOIN sources s ON s.id = d.source_id"
        f" WHERE d.id = c.document_id AND {highest} <> c.min_level"
    )


def _drop_index_levels() -> None:
    op.drop_constraint("min_level", "chunks", type_="check")
    op.drop_column("chunks", "min_level")
    op.execute("UPDATE chunks SET meta = meta - 'min_level' WHERE meta ->> 'min_level' IS NOT NULL")
    for table in ("documents", "sources"):
        op.drop_constraint("min_level", table, type_="check")
        op.drop_column(table, "min_level")


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def _set_card_kinds(*, cards: bool) -> None:
    source_kinds = "'git', 'folder', 'runner', 'tickets'" + (", 'cards'" if cards else "")
    document_kinds = "'file', 'commit', 'knowledge', 'ticket'" + (", 'card'" if cards else "")
    _replace_check("sources", "ck_sources_kind", f"kind IN ({source_kinds})")
    _replace_check("documents", "ck_documents_kind", f"kind IN ({document_kinds})")
    _replace_check(
        "run_items", "ck_run_items_document_kind", f"document_kind IN ({document_kinds})"
    )


def _add_invitation_levels() -> None:
    op.add_column(
        "invitations",
        sa.Column(
            "product_levels",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "product_levels_is_array", "invitations", "jsonb_typeof(product_levels) = 'array'"
    )


def upgrade() -> None:
    _system_mode(on=True)
    _rename_products(forward=True)
    _rename_collections(forward=True)
    _rename_references(forward=True)
    _rename_level_suffixes()
    _add_conversation_levels()
    _create_workspace_levels()
    _create_member_product_levels()
    for table in _NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_workspace ON {table} USING ({_POLICY}) WITH CHECK ({_POLICY})"
        )
    _add_index_levels()
    _set_card_kinds(cards=True)
    _add_invitation_levels()
    _system_mode(on=False)


_REFUSALS = (
    (
        "a product was created after the migration",
        "SELECT 1 FROM products p WHERE p.created_at >= (SELECT min(l.created_at)"
        " FROM workspace_levels l WHERE l.workspace_id = p.workspace_id)",
    ),
    (
        "a conversation has a level below product_dev",
        "SELECT 1 FROM conversations WHERE level <> 'product_dev'",
    ),
    (
        "an API key has a maximum level below product_dev",
        "SELECT 1 FROM api_keys WHERE max_level <> 'product_dev'",
    ),
    ("a member has a recorded level", "SELECT 1 FROM member_product_levels"),
    (
        "an invitation has product levels",
        "SELECT 1 FROM invitations WHERE product_levels <> '[]'::jsonb",
    ),
    ("a cards source exists", "SELECT 1 FROM sources WHERE kind = 'cards'"),
)


def _refuse_lossy_downgrade() -> None:
    checks = "\n".join(
        f"IF EXISTS ({query}) THEN RAISE EXCEPTION 'cannot downgrade 0018: {reason}'; END IF;"
        for reason, query in _REFUSALS
    )
    op.execute(f"DO $$ BEGIN\n{checks}\nEND $$")


def downgrade() -> None:
    _system_mode(on=True)
    _refuse_lossy_downgrade()
    op.drop_constraint("product_levels_is_array", "invitations", type_="check")
    op.drop_column("invitations", "product_levels")
    _set_card_kinds(cards=False)
    _drop_index_levels()
    for table in reversed(_NEW_TABLES):
        op.execute(f"DROP POLICY {table}_workspace ON {table}")
    op.drop_index(
        "ix_member_product_levels_workspace_id_user_id", table_name="member_product_levels"
    )
    op.drop_table("member_product_levels")
    op.drop_index("ix_workspace_levels_workspace_id_credential_id", table_name="workspace_levels")
    op.drop_table("workspace_levels")
    for table, column in (("api_keys", "max_level"), ("messages", "level")):
        op.drop_constraint(column, table, type_="check")
        op.drop_column(table, column)
    op.drop_column("messages", "product_id")
    op.drop_constraint("level", "conversations", type_="check")
    op.drop_column("conversations", "level")
    op.drop_constraint("name_without_level", "products", type_="check")
    _rename_references(forward=False)
    _rename_collections(forward=False)
    _rename_products(forward=False)
    _system_mode(on=False)
