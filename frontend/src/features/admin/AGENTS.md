# frontend/src/features/admin/

**Função**: administração da instância, só para superadmin (rotas sob `RequireSuperadmin`). `/admin/workspaces` lista, cria, renomeia, suspende e reativa workspaces; `/admin/users` busca contas, suspende, reativa e concede ou remove superadmin. A auditoria da instância fica em `features/audit/`.

**Entra aqui**:

- `AdminWorkspacesPage.tsx`: busca, tabela paginada pela API (20 por página; `ADMIN_PAGE_SIZE`), "Criar workspace", "Renomear" e "Suspender"/"Reativar" com `ConfirmDialog`.
- `CreateWorkspaceDialog.tsx`: nome, identificador opcional (em branco, o backend gera) e e-mail do proprietário, que recebe o convite; erros da API (`slug_taken`) no `FormAlert` do diálogo.
- `RenameWorkspaceDialog.tsx`: novo nome (o identificador não muda).
- `AdminUsersPage.tsx`: busca, tabela paginada, "Suspender"/"Reativar" e "Tornar superadmin"/"Remover superadmin", todos com confirmação. A linha do próprio usuário não tem "Suspender".
- `SearchForm.tsx` (busca enviada com Enter ou botão), `ListState.tsx` (carregando, erro com "Tentar novamente" ou a lista) e `StatusBadge.tsx` ("Ativo"/"Suspenso").

**Não entra aqui**: chamadas de API (`lib/api/admin.ts`), regras de formulário (`lib/schemas.ts`: `workspaceNameField`, `optionalSlugField`, `emailField`), tabela e confirmação genéricas (`components/`), auditoria (`features/audit/`), textos (`i18n/locales/`, chaves `admin.*`).

**Convenções locais**:

- A busca e a paginação são do servidor (`q`, `limit`, `offset`); nova busca volta para a primeira página.
- Erros da API (`last_superadmin`, `cannot_suspend_self`, `slug_taken`, `not_found`) aparecem pelo `code` via `translateApiError`; sucesso em `role="status"`.
- Suspender ou reativar workspace de que o superadmin é membro, e mudar o próprio superadmin, recarregam `me` (feito pelos hooks de `lib/api/admin.ts`).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Testes pela árvore real (`renderWithProviders({ path: "/admin/workspaces" })`, com `meAs(makeMe({ is_superadmin: true }))`) e MSW: `adminWorkspaceStore()` e `adminUserStore()` (mudanças persistem; `created`, `changes`, `queries`), `createWorkspaceFails`, `updateWorkspaceFails`, `updateUserFails`, `adminWorkspacesServerError`, `adminUsersServerError`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`/v1/admin/workspaces`, `/v1/admin/users`).
