# frontend/src/test/handlers/

**Função**: handlers MSW que simulam a API nos testes, um arquivo por recurso, tipados pelo `schema.gen.ts`.

**Entra aqui**:

- `index.ts`: reexporta tudo e define `handlers`, os padrões do servidor (caminho feliz: instância configurada, usuário logado, API pronta).
- `errors.ts`: `apiErrorResponse(status, code, details?)`, resposta no formato de erro padrão.
- `health.ts`: `healthReadyOk` (padrão), `healthReadyUnavailable`, `healthReadyNetworkError`, `healthReadyPending`.
- `setup.ts`: `setupStatusDone` e `setupOk` (padrão), `setupStatusNeeded`, `setupStatusServerError`, `setupAlreadyCompleted`.
- `auth.ts`: `meOk`, `updateProfileOk` (`PATCH /v1/me`, aplica o corpo ao usuário padrão), `loginOk`, `logoutOk`, `csrfOk` (padrão), `meAs(me)`, `meUnauthenticated`, `meServerError`, `updateProfileCsrfFailed`, `loginInvalidCredentials`, `logoutUnauthenticated`, `logoutCsrfFailed`.

- `recovery.ts`: `forgotPasswordOk`, `resetPasswordOk` e `verifyEmailOk` (padrão, 204), `forgotPasswordServerError`, `resetPasswordInvalidToken`, `resetPasswordWeak`, `verifyEmailInvalidToken`, `verifyEmailServerError`.
- `invites.ts`: `invitationPreviewOk` e `acceptInvitationOk` (padrão: convite de editor para `bruno@example.test`, sem conta; o aceite devolve o `me` do convidado já membro), `invitationPreviewAs(preview)`, `invitationPreviewInvalidToken`, `acceptInvitationLoginRequired`, `acceptInvitationEmailMismatch`, `acceptInvitationInvalidToken`, `acceptInvitationAlreadyMember`.
- `account.ts`: `sessionsOk` (lista padrão: esta sessão e um celular, paginada por `limit`/`offset`), `revokeSessionOk`, `changePasswordOk` e `resendVerificationOk` (padrão), `sessionsAs(sessions)`, `sessionStore(initial)` (GET + DELETE com estado: a sessão revogada some da próxima listagem; `revoked` guarda os ids), `sessionsServerError`, `revokeSessionCsrfFailed`, `changePasswordInvalidCurrent`, `changePasswordWeak`, `resendVerificationAlreadyVerified`, `resendVerificationTooMany(seconds)`.
- `members.ts`: membros, convites e nome do workspace (`/v1/workspaces/{id}`, `/members`, `/invites`). Padrões sem estado: `membersOk`, `changeMemberRoleOk`, `removeMemberOk`, `invitesOk`, `createInviteOk`, `revokeInviteOk`, `resendInviteOk`, `renameWorkspaceOk`. Com estado, criados por teste: `memberStore(initial)` (PATCH/DELETE mudam o próximo GET; `changes`, `removed`) e `inviteStore(initial)` (POST/DELETE/resend; `created`, `revoked`, `resent`). Variações: `membersAs`, `invitesAs`, `membersServerError`, `invitesServerError` e `<ação>Fails(status, code)` para cada mutação.
- `audit.ts`: auditoria do workspace (`"workspace"`) e da instância (`"instance"`). Padrões `workspaceAuditOk` e `instanceAuditOk` (lista de `makeAuditEvents`, paginada, filtros ignorados); `auditAs(scope, events)`, `auditRecorder(scope, events)` (guarda a query string de cada requisição em `queries`), `auditServerError(scope)`.
- `admin.ts`: `/v1/admin/workspaces` e `/v1/admin/users`. Padrões em `adminHandlers` (listas com busca por `q`, mutações respondendo com a linha alterada). Com estado: `adminWorkspaceStore(initial)` (POST com 409 `slug_taken` para identificador em uso, PATCH; `created`, `changes`, `queries`) e `adminUserStore(initial)` (PATCH; `changes`, `queries`). Variações: `adminWorkspacesAs`, `adminUsersAs`, `adminWorkspacesServerError`, `adminUsersServerError`, `createWorkspaceFails`, `updateWorkspaceFails`, `updateUserFails`.
- `page.ts`: `page(request, rows)` (uma página honrando `limit`/`offset`) e `matchesQuery(request, ...texts)` (busca `q` sem diferenciar maiúsculas), usados pelos handlers de listas.
- `record.ts`: `recordingPost(path, respond)` (guarda os corpos JSON recebidos, para afirmar o que a tela enviou) e `pendingPost(path)` (nunca responde, para ver o estado de envio).

**Não entra aqui**: fábricas de dados (`../factories.ts`), testes, dados reais.

**Convenções locais**:

- Caminhos casam qualquer origem (`*/v1/...`), para não depender da `baseUrl`.
- Um handler padrão por endpoint usado pelo app (entra em `<recurso>Handlers` e em `handlers`); variações exportadas com nome que diz o cenário, para `server.use(...)`.
- Corpos de sucesso vêm de `../factories.ts`; erros, de `apiErrorResponse` com o `code` real do backend.
- Recurso novo: arquivo novo aqui e uma linha em `index.ts`.

**Como testar**: exercitada indiretamente por `pnpm test -- --coverage`, de `frontend/`.

**Leia também**: [../AGENTS.md](../AGENTS.md); `docs/specs/openapi.json`.
