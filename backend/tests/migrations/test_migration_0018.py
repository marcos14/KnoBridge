"""Migration ``0018``: assistants become products and the response levels arrive, up and down
against real Postgres, with seeded data.

The database is owned by the application role (not a superuser), as in deployment, so the data
steps run under forced RLS and must switch to system mode themselves. The seed is written by
the superuser at ``0017``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Generator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
_NEW_TABLES = ("products", "product_collections", "workspace_levels", "member_product_levels")


@dataclass(frozen=True)
class Databases:
    owner: str  # the application role, owner of the tables (runs the migrations)
    admin: str  # the superuser, for the seed and the checks


def _config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    config.attributes["database_url"] = database_url
    return config


async def _superuser(database_url: str, statements: Sequence[str]) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


@pytest.fixture
def databases(postgres_url: str, app_database_url: str) -> Generator[Databases]:
    """A new database owned by the application role, migrated to ``0017``."""
    name = f"knobridge_m0018_{uuid.uuid4().hex[:12]}"
    owner_url = make_url(app_database_url)
    admin = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    owner = owner_url.set(database=name).render_as_string(hide_password=False)
    asyncio.run(_superuser(postgres_url, [f"CREATE DATABASE {name} OWNER {owner_url.username}"]))
    asyncio.run(_superuser(admin, ["CREATE EXTENSION IF NOT EXISTS vector"]))
    command.upgrade(_config(owner), "0017")
    yield Databases(owner=owner, admin=admin)
    asyncio.run(_superuser(postgres_url, [f"DROP DATABASE {name} WITH (FORCE)"]))


def _execute(database_url: str, statements: Sequence[tuple[str, Mapping[str, object]]]) -> None:
    async def run() -> None:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                for statement, params in statements:
                    await connection.execute(text(statement), dict(params))
        finally:
            await engine.dispose()

    asyncio.run(run())


def _rows(
    database_url: str, query: str, params: Mapping[str, object] | None = None
) -> list[tuple[object, ...]]:
    async def run() -> list[tuple[object, ...]]:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text(query), dict(params or {}))
                return [tuple(row) for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(run())


@dataclass
class Seed:
    """Ids of the seeded rows, by a readable name."""

    ids: dict[str, uuid.UUID] = field(default_factory=dict[str, uuid.UUID])

    def __getitem__(self, name: str) -> uuid.UUID:
        if name not in self.ids:
            self.ids[name] = uuid.uuid4()
        return self.ids[name]


def _seed_statements(seed: Seed) -> list[tuple[str, Mapping[str, object]]]:
    """Three workspaces at ``0017``.

    ``w1``: two credentials; assistants ``erp`` (one answer with a model), ``portal`` named
    ``Portal:support`` (two answers with a model, a webhook with a secret, a ticket request)
    and ``taken`` already named ``Portal - support``; a collection bound to ``erp``; a key
    scoped to ``erp`` and ``portal``; folder, runner, tickets and git sources with documents
    and chunks. ``w2``: no assistant. ``w3``: two assistants without answers.
    """
    s = seed
    statements: list[tuple[str, Mapping[str, object]]] = []

    def add(sql: str, **params: object) -> None:
        statements.append((sql, params))

    add(
        "INSERT INTO users (id, email, name) VALUES (:id, :email, 'Ana')",
        id=s["user"],
        email=f"{s['user'].hex[:12]}@example.test",
    )
    for ws in ("w1", "w2", "w3"):
        add(
            "INSERT INTO workspaces (id, name, slug) VALUES (:id, :name, :slug)",
            id=s[ws],
            name=ws,
            slug=f"{ws}-{s[ws].hex[:12]}",
        )
        add(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES (:ws, :user, 'owner')",
            ws=s[ws],
            user=s["user"],
        )
    for credential, ws in (("c1", "w1"), ("c2", "w1"), ("c3", "w3")):
        add(
            "INSERT INTO provider_credentials (id, workspace_id, name, kind, key_ciphertext,"
            " key_last4) VALUES (:id, :ws, :name, 'fake', 'v1.x', '1234')",
            id=s[credential],
            ws=s[ws],
            name=credential,
        )
    assistants = (
        ("erp", "w1", "ERP", "c1", "m-erp", 0.3, "2026-01-01"),
        ("portal", "w1", "Portal:support", "c2", "m-portal", 0.7, "2026-01-02"),
        ("taken", "w1", "Portal - support", "c1", "m-taken", 0.2, "2026-01-03"),
        ("old", "w3", "Antigo", "c3", "m-old", 0.4, "2026-01-01"),
        ("new", "w3", "Novo", "c3", "m-new", 0.5, "2026-02-01"),
    )
    for key, ws, name, credential, model, temperature, created in assistants:
        add(
            "INSERT INTO assistants (id, workspace_id, name, description, system_prompt,"
            " credential_id, model, temperature, language, tone, no_source_message, created_at)"
            " VALUES (:id, :ws, :name, '', :prompt, :credential, :model, :temperature, 'pt-BR',"
            " 'neutral', 'Sem fonte.', :created)",
            id=s[key],
            ws=s[ws],
            name=name,
            prompt=f"Prompt {name}",
            credential=s[credential],
            model=model,
            temperature=temperature,
            created=datetime.fromisoformat(created).replace(tzinfo=UTC),
        )
    add(
        "UPDATE assistants SET ticket_webhook_url = 'https://hooks.example.test/k',"
        " ticket_webhook_secret_ciphertext = 'v1.secret', ticket_webhook_secret_created_at = now()"
        " WHERE id = :id",
        id=s["portal"],
    )
    add(
        "INSERT INTO collections (id, workspace_id, name, description, credential_id,"
        " embedding_model, embedding_dimension) VALUES (:id, :ws, 'K', '', :c, 'emb', 1536)",
        id=s["collection"],
        ws=s["w1"],
        c=s["c1"],
    )
    add(
        "INSERT INTO assistant_collections (workspace_id, assistant_id, collection_id)"
        " VALUES (:ws, :assistant, :collection)",
        ws=s["w1"],
        assistant=s["erp"],
        collection=s["collection"],
    )
    # Conversations: ``erp`` answered once with a model, ``portal`` twice (plus a question and
    # a "no source" answer, which have no model).
    answers = (("conv_erp", "erp", ["m-erp"]), ("conv_portal", "portal", ["m", "m", None, None]))
    for conversation, assistant, models in answers:
        add(
            "INSERT INTO conversations (id, workspace_id, assistant_id, user_id, channel)"
            " VALUES (:id, :ws, :assistant, :user, 'panel')",
            id=s[conversation],
            ws=s["w1"],
            assistant=s[assistant],
            user=s["user"],
        )
        for position, model in enumerate(models):
            add(
                "INSERT INTO messages (id, workspace_id, conversation_id, position, role,"
                " content, status, model) VALUES (:id, :ws, :conversation, :position,"
                " 'assistant', 'Texto', 'completed', :model)",
                id=s[f"{conversation}_{position}"],
                ws=s["w1"],
                conversation=s[conversation],
                position=position,
                model=model,
            )
    add(
        "INSERT INTO api_keys (id, workspace_id, name, key_prefix, key_hash, assistant_ids)"
        " VALUES (:id, :ws, 'Integração', 'abcd1234', repeat('a', 64), ARRAY[:a, :b]::uuid[])",
        id=s["key"],
        ws=s["w1"],
        a=s["erp"],
        b=s["portal"],
    )
    add(
        "INSERT INTO ticket_requests (id, workspace_id, conversation_id, message_id,"
        " assistant_id, user_id, status, error_code) VALUES (:id, :ws, :conversation,"
        " :message, :assistant, :user, 'failed', 'webhook_rejected')",
        id=s["request"],
        ws=s["w1"],
        conversation=s["conv_portal"],
        message=s["conv_portal_0"],
        assistant=s["portal"],
        user=s["user"],
    )
    for source, kind in (
        ("folder", "folder"),
        ("runner", "runner"),
        ("tickets", "tickets"),
        ("git", "git"),
    ):
        add(
            "INSERT INTO sources (id, workspace_id, collection_id, kind, name, config)"
            " VALUES (:id, :ws, :collection, :kind, :name, '{}'::jsonb)",
            id=s[source],
            ws=s["w1"],
            collection=s["collection"],
            kind=kind,
            name=source,
        )
    documents = (
        ("doc_code", "folder", "file", "app.py", "{}"),
        ("doc_guide", "folder", "file", "guia.md", "{}"),
        ("doc_inferred", "runner", "knowledge", "k1", '{"confidence": "inferido"}'),
        ("doc_reviewed", "runner", "knowledge", "k2", '{"confidence": "revisado"}'),
        ("doc_ticket", "tickets", "ticket", "t1", "{}"),
        ("doc_commit", "git", "commit", "abc", "{}"),
    )
    for document, source, kind, key, meta in documents:
        add(
            "INSERT INTO documents (id, workspace_id, source_id, natural_key, kind, title, uri,"
            " content_hash, meta) VALUES (:id, :ws, :source, :key, :kind, :key || '', :key || '',"
            " repeat('0', 64), CAST(:meta AS jsonb))",
            id=s[document],
            ws=s["w1"],
            source=s[source],
            key=key,
            kind=kind,
            meta=meta,
        )
    chunks = (
        ("chunk_code", "doc_code", '{"path": "app.py", "language": "python"}'),
        ("chunk_guide", "doc_guide", '{"headings": ["Guia"]}'),
        ("chunk_inferred", "doc_inferred", '{"headings": ["Item", "Regra"]}'),
        ("chunk_reviewed", "doc_reviewed", '{"headings": ["Item", "Regra"]}'),
        ("chunk_evidence", "doc_reviewed", '{"headings": ["Item", "Evidências"]}'),
        ("chunk_ticket", "doc_ticket", "{}"),
        ("chunk_commit", "doc_commit", "{}"),
    )
    for position, (chunk, document, meta) in enumerate(chunks):
        add(
            "INSERT INTO chunks (id, workspace_id, document_id, collection_id, position, content,"
            " meta, content_hash, embedding_model, embedding) VALUES (:id, :ws, :document,"
            " :collection, :position, 'Texto', CAST(:meta AS jsonb), repeat('0', 64), 'emb',"
            " array_fill(0.0::real, ARRAY[1536])::vector)",
            id=s[chunk],
            ws=s["w1"],
            document=s[document],
            collection=s["collection"],
            position=position,
            meta=meta,
        )
    return statements


@pytest.fixture
def seeded(databases: Databases) -> Seed:
    seed = Seed()
    _execute(databases.admin, _seed_statements(seed))
    return seed


def _by_id(rows: list[tuple[object, ...]]) -> dict[object, tuple[object, ...]]:
    return {row[0]: tuple(row[1:]) for row in rows}


def test_migration_0018_turns_assistants_into_products(databases: Databases, seeded: Seed) -> None:
    s = seeded

    command.upgrade(_config(databases.owner), "0018")
    products = _by_id(
        _rows(
            databases.admin,
            "SELECT id, name, instructions, ticket_webhook_url, ticket_webhook_secret_ciphertext"
            " FROM products",
        )
    )
    collections = _rows(
        databases.admin, "SELECT product_id, collection_id FROM product_collections"
    )
    conversations = _by_id(
        _rows(databases.admin, "SELECT id, product_id, level FROM conversations")
    )
    messages = set(_rows(databases.admin, "SELECT product_id, level FROM messages"))
    keys = _rows(databases.admin, "SELECT product_ids, max_level FROM api_keys")
    requests = _rows(databases.admin, "SELECT product_id FROM ticket_requests")
    members = _rows(databases.admin, "SELECT count(*) FROM member_product_levels")
    invitations_default = _rows(
        databases.admin,
        "SELECT column_default FROM information_schema.columns"
        " WHERE table_name = 'invitations' AND column_name = 'product_levels'",
    )

    assert products == {
        s["erp"]: ("ERP", "Prompt ERP", None, None),
        s["portal"]: (
            "Portal - support (2)",
            "Prompt Portal:support",
            "https://hooks.example.test/k",
            "v1.secret",
        ),
        s["taken"]: ("Portal - support", "Prompt Portal - support", None, None),
        s["old"]: ("Antigo", "Prompt Antigo", None, None),
        s["new"]: ("Novo", "Prompt Novo", None, None),
    }
    assert collections == [(s["erp"], s["collection"])]
    assert conversations == {
        s["conv_erp"]: (s["erp"], "product_dev"),
        s["conv_portal"]: (s["portal"], "product_dev"),
    }
    assert messages == {(s["erp"], "product_dev"), (s["portal"], "product_dev")}
    assert keys == [([s["erp"], s["portal"]], "product_dev")]
    assert requests == [(s["portal"],)]
    assert members == [(0,)]
    assert invitations_default == [("'[]'::jsonb",)]


def test_migration_0018_levels_take_the_most_used_model(databases: Databases, seeded: Seed) -> None:
    s = seeded

    command.upgrade(_config(databases.owner), "0018")
    rows = _rows(
        databases.admin,
        "SELECT workspace_id, level, credential_id, model, temperature, instructions"
        " FROM workspace_levels WHERE workspace_id = ANY(:ids) ORDER BY workspace_id, level",
        {"ids": [s["w1"], s["w2"], s["w3"]]},
    )
    by_workspace: dict[object, set[tuple[object, ...]]] = {}
    for workspace_id, *rest in rows:
        by_workspace.setdefault(workspace_id, set()).add(tuple(rest))

    def levels(
        credential: uuid.UUID | None, model: str | None, temperature: float
    ) -> set[tuple[object, ...]]:
        return {
            (level, credential, model, temperature, None)
            for level in ("end_user", "support", "product_dev")
        }

    assert by_workspace[s["w1"]] == levels(s["c2"], "m-portal", 0.7)
    assert by_workspace[s["w2"]] == levels(None, None, 0.2)
    assert by_workspace[s["w3"]] == levels(s["c3"], "m-old", 0.4)


def test_migration_0018_sets_the_minimum_levels_of_the_index(
    databases: Databases, seeded: Seed
) -> None:
    s = seeded

    command.upgrade(_config(databases.owner), "0018")
    sources = _by_id(_rows(databases.admin, "SELECT id, min_level FROM sources"))
    documents = _by_id(_rows(databases.admin, "SELECT id, min_level FROM documents"))
    chunks = _by_id(
        _rows(databases.admin, "SELECT id, min_level, meta ->> 'min_level' FROM chunks")
    )

    assert sources == {
        s["folder"]: ("end_user",),
        s["runner"]: ("end_user",),
        s["tickets"]: ("support",),
        s["git"]: ("product_dev",),
    }
    assert documents == {
        s["doc_code"]: ("product_dev",),
        s["doc_guide"]: (None,),
        s["doc_inferred"]: ("support",),
        s["doc_reviewed"]: (None,),
        s["doc_ticket"]: (None,),
        s["doc_commit"]: (None,),
    }
    assert chunks == {
        s["chunk_code"]: ("product_dev", None),
        s["chunk_guide"]: ("end_user", None),
        s["chunk_inferred"]: ("support", None),
        s["chunk_reviewed"]: ("end_user", None),
        s["chunk_evidence"]: ("support", "support"),
        s["chunk_ticket"]: ("support", None),
        s["chunk_commit"]: ("product_dev", None),
    }


def _catalog(database_url: str) -> dict[str, tuple[object, ...]]:
    rows = _rows(
        database_url,
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,"
        " (SELECT count(*) FROM pg_policies p WHERE p.tablename = c.relname)"
        " FROM pg_class c WHERE c.relkind = 'r' AND c.relname = ANY(:tables)",
        {"tables": [*_NEW_TABLES, "assistants", "assistant_collections"]},
    )
    return {str(row[0]): row[1:] for row in rows}


def _checks(database_url: str, table: str) -> dict[str, str]:
    rows = _rows(
        database_url,
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint"
        " WHERE conrelid = CAST(:table AS regclass) AND contype = 'c'",
        {"table": table},
    )
    return {str(row[0]): str(row[1]) for row in rows}


def test_migration_0018_downgrade_restores_the_assistants(
    databases: Databases, seeded: Seed
) -> None:
    s = seeded
    config = _config(databases.owner)

    command.upgrade(config, "0018")
    up = _catalog(databases.admin)
    source_kinds_up = _checks(databases.admin, "sources")["ck_sources_ck_sources_kind"]
    command.downgrade(config, "0017")
    down = _catalog(databases.admin)
    source_kinds_down = _checks(databases.admin, "sources")["ck_sources_ck_sources_kind"]
    assistants = _by_id(
        _rows(databases.admin, "SELECT id, name, system_prompt, model FROM assistants")
    )
    links = _rows(databases.admin, "SELECT assistant_id FROM assistant_collections")
    conversations = _rows(databases.admin, "SELECT DISTINCT assistant_id FROM conversations")
    keys = _rows(databases.admin, "SELECT assistant_ids FROM api_keys")
    requests = _rows(databases.admin, "SELECT assistant_id FROM ticket_requests")
    chunk_meta = _rows(
        databases.admin, "SELECT count(*) FROM chunks WHERE meta ->> 'min_level' IS NOT NULL"
    )
    command.upgrade(config, "0018")

    assert up == {
        "products": (True, True, 4),
        "product_collections": (True, True, 1),
        "workspace_levels": (True, True, 1),
        "member_product_levels": (True, True, 1),
    }
    assert "'cards'" in source_kinds_up
    assert down == {"assistants": (True, True, 4), "assistant_collections": (True, True, 1)}
    assert "'cards'" not in source_kinds_down
    assert assistants[s["portal"]] == ("Portal - support (2)", "Prompt Portal:support", "m-portal")
    assert links == [(s["erp"],)]
    assert set(conversations) == {(s["erp"],), (s["portal"],)}
    assert keys == [([s["erp"], s["portal"]],)]
    assert requests == [(s["portal"],)]
    assert chunk_meta == [(0,)]


_LOSSY = (
    (
        "a product was created after the migration",
        "INSERT INTO products (workspace_id, name, description, instructions, credential_id,"
        " model, temperature, language, tone, no_source_message)"
        " VALUES (:w1, 'Novo produto', '', '', :c1, 'm', 0.2, 'pt-BR', 'neutral', 'Sem fonte.')",
        "DELETE FROM products WHERE name = 'Novo produto'",
    ),
    (
        "a conversation has a level below product_dev",
        "UPDATE conversations SET level = 'support' WHERE id = :conv_erp",
        "UPDATE conversations SET level = 'product_dev'",
    ),
    (
        "an API key has a maximum level below product_dev",
        "UPDATE api_keys SET max_level = 'end_user' WHERE id = :key",
        "UPDATE api_keys SET max_level = 'product_dev'",
    ),
    (
        "a member has a recorded level",
        "INSERT INTO member_product_levels (workspace_id, product_id, user_id, max_level)"
        " VALUES (:w1, :erp, :user, 'support')",
        "DELETE FROM member_product_levels",
    ),
    (
        "an invitation has product levels",
        "INSERT INTO user_tokens (id, user_id, purpose, token_hash, expires_at, workspace_id)"
        " VALUES (:token, NULL, 'invitation', repeat('b', 64), now() + interval '1 day', :w1);"
        "INSERT INTO invitations (workspace_id, email, role, token_id, expires_at,"
        " product_levels) VALUES (:w1, 'novo@example.test', 'viewer', :token,"
        " now() + interval '1 day', CAST(:levels AS jsonb))",
        "DELETE FROM invitations; DELETE FROM user_tokens",
    ),
    (
        "a cards source exists",
        "INSERT INTO sources (workspace_id, collection_id, kind, name, config, min_level)"
        " VALUES (:w1, :collection, 'cards', 'Cards', '{}'::jsonb, 'product_dev')",
        "DELETE FROM sources WHERE kind = 'cards'",
    ),
)


def _statements(sql: str, seed: Seed) -> list[tuple[str, Mapping[str, object]]]:
    params: dict[str, object] = {
        name: seed[name]
        for name in ("w1", "c1", "conv_erp", "key", "erp", "user", "collection", "token")
    }
    params["levels"] = f'[{{"product_id": "{seed["erp"]}", "max_level": "support"}}]'
    out: list[tuple[str, Mapping[str, object]]] = []
    for statement in sql.split(";"):
        names = {name for name in params if f":{name}" in statement}
        out.append((statement, {name: params[name] for name in names}))
    return out


def test_migration_0018_downgrade_refuses_what_the_assistants_cannot_hold(
    databases: Databases, seeded: Seed
) -> None:
    config = _config(databases.owner)
    command.upgrade(config, "0018")
    refused: list[str] = []

    for reason, add, remove in _LOSSY:
        _execute(databases.admin, _statements(add, seeded))
        with pytest.raises(DBAPIError) as error:
            command.downgrade(config, "0017")
        refused.append(reason if reason in str(error.value) else str(error.value))
        _execute(databases.admin, _statements(remove, seeded))

    assert refused == [reason for reason, _, _ in _LOSSY]
