# frontend/src/features/members/

**Função**: gestão das pessoas do workspace em `/w/:workspaceId/members`. Todo membro lê a lista; owner e admin alteram papéis, removem membros, convidam e cuidam dos convites pendentes.

**Entra aqui**:

- `MembersPage.tsx`: `h1`, botão "Convidar" e abas "Membros" / "Convites pendentes" (abas e botão só para owner/admin; viewer e editor veem só a lista, sem ações). Depois de convidar, mostra a confirmação e abre a aba de convites.
- `MembersList.tsx`: busca (com espera de digitação), filtros, ordenação e paginação no servidor (20 por página), com o estado na query string (`useListSearch`, `ListToolbar`) (busca por nome ou e-mail, filtro de papel, ordenação por nome, e-mail, papel e entrada), papel editável por `RoleSelect` e "Remover" com `ConfirmDialog`. Na linha do próprio usuário a remoção vira "Sair do workspace" e leva a `/`.
- `InvitesList.tsx`: convites pendentes paginados pela API (validade relativa ou "Expirado"), "Reenviar" e "Revogar" com confirmação.
- `InviteDialog.tsx`: diálogo com e-mail e papel (padrão editor), react-hook-form + zod.
- `RoleSelect.tsx`: seletor de papel; papéis acima do papel de quem usa aparecem desabilitados.

**Não entra aqui**: chamadas de API (`lib/api/members.ts`, `lib/api/invites.ts`), regras de papel (`lib/roles.ts`: `canHandleRole`, `canManageWorkspace`), tabela e confirmação genéricas (`components/DataTable.tsx`, `components/ConfirmDialog.tsx`), nome do workspace (`features/settings/`), aceite de convite pelo convidado (`features/auth/`), textos (`i18n/locales/`, chaves `members.*`).

**Convenções locais**:

- A UI espelha as regras do backend: admin não convida nem gerencia owner, ninguém concede papel acima do seu (opções desabilitadas, ações ocultas). Mesmo assim os erros da API (`last_owner`, `role_not_allowed`, `already_member`, `invitation_pending`) aparecem no `FormAlert` pelo `code`.
- Mudança que atinge o próprio usuário (papel ou saída) recarrega `me`, porque menu e guardas dependem dele.
- Confirmações de sucesso em `role="status"`; o `ApiStatus` do cabeçalho também é `status`, então os testes procuram pelo texto.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Testes pela árvore real (`renderWithProviders({ path: "/w/<id>/members" })`) com MSW: `memberStore()` e `inviteStore()` para mudanças que persistem entre requisições, `membersRecorder()` para busca, filtro e ordenação, `changeMemberRoleFails`, `removeMemberFails`, `createInviteFails`, `resendInviteFails`, `revokeInviteFails` para erros.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`/v1/workspaces/{workspace_id}/members`, `/invites`).
