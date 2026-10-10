# backend/src/knobridge/tenancy/

**Função**: identidade e tenancy. Usuários da instância, workspaces e memberships (papel do usuário em cada workspace). Mais tarde: autenticação e-mail/senha, sessões, convites, API keys e RBAC.

**Entra aqui**:
- `models.py`: modelos ORM `User` (identidade da instância, sem `workspace_id` e sem RLS; e-mail único sem diferenciar maiúsculas pelo índice `uq_users_email_lower`), `Workspace` (slug único, status) e `Membership` (única por `workspace_id` + `user_id`, papel `owner`/`admin`/`editor`/`viewer`), e os `StrEnum` `AuthProvider`, `UserStatus`, `Theme`, `WorkspaceStatus`, `Role`.
- Futuramente: serviços e repositórios de tenancy (sem routers, que ficam em `api/`).

**Não entra aqui**: Base ORM e mixins (`core/models.py`), sessão de banco e escopo de RLS (`core/db.py`), routers e schemas da API (`api/`), migrações (`backend/migrations/`).

**Convenções locais**:
- `workspaces` e `memberships` têm RLS forçada (`ENABLE` + `FORCE`). Toda consulta a elas roda em `scoped_session(factory, workspace_id=, user_id=)`; `system_session` só para setup, superadmin e login. Regras das políticas no [ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md).
- O `workspace_id` passado ao escopo só seleciona: quem chama já validou a membership do usuário autenticado.
- Enums são gravados como `VARCHAR` + `CHECK` (`str_enum` de `core/models.py`); valor novo exige migração que troque o `CHECK`.
- Mudou modelo: migração nova na mesma entrega e `docs/specs/modelo-de-dados.md` atualizado. O teste `test_migrations_match_orm_models` falha se modelo e migração divergirem.

**Como testar**: de `backend/`, `uv run pytest tests/tenancy` (Postgres real via testcontainers; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md); [modelo de dados](../../../../docs/specs/modelo-de-dados.md); [core/AGENTS.md](../core/AGENTS.md); [tests/tenancy/AGENTS.md](../../../tests/tenancy/AGENTS.md).
