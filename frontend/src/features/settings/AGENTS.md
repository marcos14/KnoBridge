# frontend/src/features/settings/

**Função**: configurações do workspace em `/w/:workspaceId/settings` (owner ou admin). Hoje só a seção "Geral": nome do workspace e identificador (slug) somente leitura.

**Entra aqui**: `WorkspaceSettingsPage.tsx` (`h1` e a seção "Geral", com o formulário do nome) e as próximas seções de configuração do workspace, uma por componente.
**Não entra aqui**: membros e convites (`features/members/`), perfil e segurança da conta (`features/account/`), chamadas de API (`lib/api/workspaces.ts`), schema do nome (`workspaceNameField` em `lib/schemas.ts`), textos (`i18n/locales/`, chaves `workspaceSettings.*`).

**Convenções locais**:

- O nome salvo vai para o cache do `me` (`useRenameWorkspace`), e o seletor de workspace o mostra na hora, sem nova busca.
- O formulário é montado com `key` do workspace: trocar de workspace recomeça com os dados do outro.
- Formulário com react-hook-form + zod, `noValidate`, erros da API pelo `code` no `FormAlert`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/settings" })`) com MSW (`renameWorkspaceOk` padrão, `renameWorkspaceFails(status, code)`).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`PATCH /v1/workspaces/{workspace_id}`).
