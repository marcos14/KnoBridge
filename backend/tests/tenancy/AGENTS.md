# backend/tests/tenancy/

**Função**: testes de `src/knobridge/tenancy/`: restrições dos modelos e isolamento por RLS contra Postgres real.

**Entra aqui**: `test_tenancy_models.py` (nome distinto de `tests/core/test_models.py`, porque os testes não são pacotes e o pytest exige basenames únicos) , `test_rbac.py` (hierarquia de papéis e `ensure_role_within`, unitário), `test_setup_service.py` (setups concorrentes sobre `empty_database_url`: um usuário e um workspace), `test_superadmin_access.py` (`effective_role` e `superadmin_access`, unitários), `test_invitations_rls.py` (RLS de `invitations`) e `test_admin_services.py` (helpers de slug, unitários, e a listagem do superadmin, que só enxerga tudo em modo de sistema). As rotas do superadmin são testadas em `tests/api/test_admin.py`; o caso do último superadmin usa `empty_api`, porque o banco compartilhado sempre tem outros superadmins. As regras de convite e membros são testadas pelas rotas, em `tests/api/test_invites.py` e `tests/api/test_members.py`. O fluxo HTTP de login, setup e `/me` é testado em `tests/api/`.
**Não entra aqui**: testes de routers (`tests/api/`), da cadeia de migrações (`tests/migrations/`), dos helpers de sessão (`tests/core/test_db.py`).

**Convenções locais**:
- Testes com banco são `@pytest.mark.integration` e usa o banco da fixture `app_database_url` (migrado até `head`, conectando como o papel dono e não superusuário, como no deploy) ou `non_owner_database_url` (papel só com privilégios de tabela).
- Testes de RLS usam a fixture `rls_database_url`, parametrizada para rodar como dono e como não dono: a política precisa barrar os dois.
- O banco é compartilhado pela sessão de testes: cada teste cria seus workspaces e usuários com slugs e e-mails únicos e não conta linhas globais (só `>=`).
- Dados de semente entram por `system_session`; as asserções de isolamento usam `scoped_session` ou uma sessão sem escopo.

**Como testar**: de `backend/`, `uv run pytest tests/tenancy` (exige Docker).

**Leia também**: [tenancy/AGENTS.md](../../src/knobridge/tenancy/AGENTS.md); [tests/AGENTS.md](../AGENTS.md); [ADR 0001](../../../docs/adr/0001-tenancy-e-rls.md).
