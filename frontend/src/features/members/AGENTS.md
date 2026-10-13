# frontend/src/features/members/

**Função**: gestão das pessoas do workspace em `/w/:workspaceId/members`. Todo membro lê a lista; owner e admin alteram papéis, o nível máximo de cada membro em cada produto, removem membros, convidam e cuidam dos convites pendentes.

**Entra aqui**:

- `MembersPage.tsx`: `h1`, botão "Convidar" e abas "Membros" / "Níveis por produto" / "Convites pendentes" (abas e botão só para owner/admin; viewer e editor veem só a lista, sem ações). Depois de convidar, mostra a confirmação e abre a aba de convites.
- `MembersList.tsx`: busca (com espera de digitação), filtros, ordenação e paginação no servidor (20 por página), com o estado na query string (`useListSearch`, `ListToolbar`) (busca por nome ou e-mail, filtro de papel, ordenação por nome, e-mail, papel e entrada), papel editável por `RoleSelect` e "Remover" com `ConfirmDialog`. Na linha do próprio usuário a remoção vira "Sair do workspace" e leva a `/`.
- `memberListSearch.ts`: `MEMBER_SORTS` e `MEMBER_LIST`, a busca, o filtro de papel e as ordenações da lista de membros e da tabela de níveis (o mesmo estado na URL nas duas abas).
- `MemberLevelsList.tsx` (owner e admin): a tabela membro × produto de `GET .../member-levels`, uma coluna por produto (inativo marcado), com a mesma busca, filtro, ordenação e paginação da lista. Cada célula é um `MemberLevelSelect` com "Padrão do papel: <nível>" (sem valor gravado; owner e admin `product_dev`, editor e leitor `end_user`) ou um dos três níveis; escolher grava só aquele produto (`PUT .../product-levels`), "Padrão do papel" manda `null`. Quem tem papel acima do de quem edita fica desabilitado (`canHandleRole`, como `role_not_allowed`). Sem produtos, o aviso de onde eles vêm.
- `MemberLevelSelect.tsx`: seletor de nível máximo de um membro ou de um convite num produto, com a opção do padrão do papel (`DEFAULT_LEVEL`).
- `InvitesList.tsx`: convites pendentes paginados pela API (validade relativa ou "Expirado"), "Reenviar" e "Revogar" com confirmação.
- `InviteDialog.tsx`: diálogo com e-mail, papel (padrão editor) e, opcional, o nível por produto (um `MemberLevelSelect` por produto de `useProducts`, começando no padrão do papel escolhido; só os produtos com nível escolhido vão em `product_levels`, e sem nenhum o campo não vai), react-hook-form + zod. Falha ao carregar os produtos não impede o convite.
- `RoleSelect.tsx`: seletor de papel; papéis acima do papel de quem usa aparecem desabilitados.

**Não entra aqui**: chamadas de API (`lib/api/members.ts`, `lib/api/memberLevels.ts`, `lib/api/invites.ts`, `lib/api/products.ts`), regras de papel (`lib/roles.ts`: `canHandleRole`, `canManageWorkspace`), padrão de nível por papel (`lib/responseLevels.ts`: `defaultMaxLevel`), tabela e confirmação genéricas (`components/DataTable.tsx`, `components/ConfirmDialog.tsx`), nome do workspace (`features/settings/`), aceite de convite pelo convidado (`features/auth/`), textos (`i18n/locales/`, chaves `members.*`; nomes dos níveis em `workspaceSettings.levels.names.*`).

**Convenções locais**:

- A UI espelha as regras do backend: admin não convida nem gerencia owner, ninguém concede papel acima do seu (opções desabilitadas, ações ocultas), admin não edita o nível de quem tem papel acima. Mesmo assim os erros da API (`last_owner`, `role_not_allowed`, `already_member`, `invitation_pending`, `member_level_product_invalid`, `invite_product_invalid`) aparecem no `FormAlert` pelo `code`.
- Mudança que atinge o próprio usuário (papel, nível ou saída) recarrega `me`, porque menu, guardas e o chat dependem dele.
- Confirmações de sucesso em `role="status"`; o `ApiStatus` do cabeçalho também é `status`, então os testes procuram pelo texto.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Testes pela árvore real (`renderWithProviders({ path: "/w/<id>/members" })`) com MSW: `memberStore()` e `inviteStore()` para mudanças que persistem entre requisições, `membersRecorder()` para busca, filtro e ordenação, `memberLevelStore()` (tabela de níveis que muda; `changes`, `queries`), `memberLevelsAs`, `memberLevelsServerError`, `setMemberLevelFails`, `changeMemberRoleFails`, `removeMemberFails`, `createInviteFails`, `resendInviteFails`, `revokeInviteFails` para erros; fábricas da tabela em `@/test/levelFactories` (`makeMemberLevels`, `makeProductRefs`).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/produtos-e-niveis.md` ("Nível por membro e produto"); `docs/specs/openapi.json` (`/v1/workspaces/{workspace_id}/members`, `/member-levels`, `/members/{user_id}/product-levels`, `/invites`).
