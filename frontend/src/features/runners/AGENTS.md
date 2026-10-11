# frontend/src/features/runners/

**Função**: runners locais do harness de código em `/w/:workspaceId/runners` (owner e admin; editor e viewer não veem o item de menu e recebem 403 na rota). Lista com presença, cadastro com o token mostrado uma única vez, revogação e exclusão.

**Entra aqui**:

- `RunnersPage.tsx`: `h1`, "Novo runner", tabela paginada no navegador (20 por página; a lista inteira vem de `useRunners`, que recarrega a cada 30 s) com nome e prefixo do token (`kbr_<prefixo>_…`), status (`runnerStatus` de `lib/runnerStatus.ts`: online, offline ou revogado), último contato (tempo relativo ou "Nunca conectou"), versão, executores (versão; "sem login" ou "indisponível"; nome desconhecido aparece como veio), repositórios (branch e "alterações locais") e as ações "Revogar" (só runner ativo) e "Excluir", ambas com `ConfirmDialog`.
- `CreateRunnerDialog.tsx`: nome (react-hook-form + zod, 1 a 200 caracteres) e, depois do `POST`, a visão do token: o token, os comandos de instalação e configuração (`runnerSetup.ts`, com `window.location.origin` como URL do servidor) e um `CopyButton` para cada um.
- `CopyButton.tsx`: copia pelo `navigator.clipboard` e diz "Copiado." ou pede a cópia manual quando o navegador bloqueia.
- `runnerSetup.ts`: `runnerSetupCommands(serverUrl, repository)` (função pura, com teste).

**Não entra aqui**: chamadas de API (`lib/api/runners.ts`), presença e estado dos executores, que a fonte também usa (`lib/runnerStatus.ts`), o formulário da fonte do tipo runner (`features/sources/`), textos (`i18n/locales/`, chaves `runners.*`; erros em `apiErrors.*`).

**Convenções locais**:

- O token só existe no estado do diálogo: abrir e fechar o diálogo o descartam, e nenhuma consulta o guarda. Os comandos copiáveis não levam o token (o `configure` pede no terminal, fora do histórico do shell).
- Status pelo `last_seen_at` com a janela de 90 s do servidor (`ONLINE_WINDOW_MS`) e o relógio de `useClock()`, para a lista envelhecer entre as recargas.
- Revogar é irreversível (o painel nunca manda `revoked: false`); excluir runner usado por fonte responde 409 `runner_in_use`, mostrado no `FormAlert`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/runners" })`) com MSW: `runnerStore(initial, { inUse })` (`created`, `changes`, `deleted`), `runnersAs`, `runnersServerError`, `runnerActionFails(action, status, code)`; clipboard pelo stub do `userEvent.setup()` (`navigator.clipboard.readText()`).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/runner.md` (token, API de sessão do painel); `runner/README.md`.
