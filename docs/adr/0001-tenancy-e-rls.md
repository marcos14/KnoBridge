# ADR 0001 — Tenancy e row-level security

> Status: aceito · 2026-10-10 · plano 0002 (F1.1)

## Contexto

O KnoBridge é multi-tenant desde o primeiro modelo (decisão D9 da [visão](../01-visao-do-projeto.md), regra 7 do [AGENTS.md](../../AGENTS.md)). A seção 7.7 da visão pede RBAC por workspace (owner, admin, editor, viewer), autenticação e-mail/senha com `provider` previsto para OIDC (D12) e row-level security no Postgres. Faltava decidir como usuários se relacionam com workspaces, como a aplicação informa o escopo ao banco e como tarefas da instância (primeiro setup, superadmin, login) acessam dados sem um workspace selecionado.

No deploy (`deploy/postgres/init-databases.sh`), a aplicação conecta com o papel `knobridge`, que não é superusuário e é dono do banco e das tabelas criadas pelas migrações. Dono de tabela ignora RLS, a menos que a tabela tenha `FORCE ROW LEVEL SECURITY`.

## Decisão

1. **Usuários são identidades da instância**: a tabela `users` não tem `workspace_id` nem RLS. Um usuário participa de **N workspaces** por meio de `memberships` (uma por par workspace + usuário, com `role`). A entrada em workspace é por convite (fluxo em subfase posterior).
2. **Superadmin** é um atributo do usuário (`users.is_superadmin`), não um papel de workspace. Ele administra a instância (workspaces, usuários) pelo modo de sistema.
3. **RLS forçada** (`ENABLE` + `FORCE ROW LEVEL SECURITY`) em toda tabela com dado de workspace, incluindo `workspaces` e `memberships`, na mesma migração que cria a tabela. O papel do banco usado pela aplicação nunca é superusuário nem tem `BYPASSRLS`.
4. **Escopo por transação**: a aplicação define `app.workspace_id`, `app.user_id` e `app.system` com `set_config(nome, valor, true)` (equivalente a `SET LOCAL`, com parâmetros ligados) no início de cada transação, por `scoped_session(factory, workspace_id=, user_id=)` em `knobridge.core.db`. As políticas leem `NULLIF(current_setting(..., true), '')`. Sem escopo, nada é visível (falha fechada); o escopo some no fim da transação.
5. **Políticas**:
   - `workspaces`: leitura quando é o workspace selecionado, quando o usuário do escopo é membro dele, ou em modo de sistema; escrita só no workspace selecionado ou em modo de sistema.
   - `memberships`: leitura no workspace selecionado, das memberships do próprio usuário em qualquer workspace (para listar "meus workspaces"), ou em modo de sistema; escrita só no workspace selecionado ou em modo de sistema, para que ninguém altere o próprio papel em outro workspace.
   - Tabelas de dado futuras: `workspace_id = app.workspace_id` ou modo de sistema.
6. **O `workspace_id` do escopo só seleciona**: a permissão vem da membership do usuário autenticado, validada pela aplicação antes de abrir a sessão. Nunca vem do cliente da API sem essa validação.
7. **Modo de sistema explícito**: `system_session(factory)` liga `app.system = 'on'` na transação. Uso restrito a primeiro setup, operações de superadmin e login, sempre auditado pelo serviço de auditoria quando ele existir.

## Alternativas consideradas

- **Usuário pertencente a um único workspace** (`users.workspace_id`): mais simples, mas força contas duplicadas para quem atende vários clientes e complica convite. Descartada.
- **Só filtro na aplicação, sem RLS**: um `WHERE` esquecido vaza dados entre tenants. Descartada; o filtro na aplicação continua, e a RLS é a segunda barreira.
- **RLS sem `FORCE`**: o papel da aplicação é dono das tabelas e ignoraria as políticas. Descartada.
- **Papel separado com `BYPASSRLS` para o modo de sistema**: isola melhor, mas exige segunda credencial, segundo pool e mudança no compose. Fica como evolução possível; hoje o modo de sistema é uma configuração de transação usada só por código da instância.
- **`SET` de sessão em vez de `SET LOCAL`**: o escopo vazaria para a próxima requisição que reaproveitasse a conexão do pool. Descartada.
- **Schema ou banco por tenant**: isolamento físico, mas migrações e pool multiplicados por tenant. Descartada nesta fase.

## Consequências

- Toda consulta a tabela com RLS precisa de `scoped_session` ou `system_session`; o código que esquecer recebe zero linhas (ou erro de política em escrita), nunca dado de outro workspace.
- Cada consulta nova ganha teste de isolamento contra Postgres real, rodando como o papel dono (não superusuário) e como um papel não dono (`tests/tenancy/`).
- A política de `workspaces` consulta `memberships`; por isso o downgrade remove as políticas antes das tabelas.
- Unicidade global (e-mail, slug) continua valendo acima da RLS; o erro de conflito pode revelar que um slug existe, o que é aceitável.
- Ambiente local com superusuário (ex.: o `docker run` de exemplo do `backend/README.md`) ignora RLS; o isolamento só é garantido com o papel de aplicação do compose.
- Modelo de dados em [docs/specs/modelo-de-dados.md](../specs/modelo-de-dados.md).
