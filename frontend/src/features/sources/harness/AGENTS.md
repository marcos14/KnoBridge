# frontend/src/features/sources/harness/

**Função**: o corpo do detalhe de uma fonte do tipo runner (`/w/:workspaceId/sources/:sourceId`): abas **Módulos**, **Tarefas** e **Indexação** (execuções e documentos de `../`). Qualquer membro lê; owner, admin e editor criam e editam módulos, ligam e desligam, rodam e cancelam tarefas.

**Entra aqui**:

- `RunnerSourceTabs.tsx` + `tabs.ts`: as abas, com a aberta em `?tab=` (`parseRunnerSourceTab`; desconhecida ou ausente abre a primeira). Aba nova (ex.: Conhecimento, F4.3) = um id em `RUNNER_SOURCE_TABS`, o rótulo em `harness.tabs.<id>` e o conteúdo no `switch` de `RunnerSourceTabs`.
- `ModulesTab.tsx`: lista inteira de `useHarnessModules` filtrada (título, chave ou padrão) e paginada no navegador (50 por página): seleção (só módulos ligados), título com "Sugerido"/"Manual", chave, padrões (3 e "+N"), arquivos e linhas, último commit mapeado (7 caracteres), última tarefa, ligar/desligar e editar; `ModuleDialog.tsx` (criar/editar com react-hook-form + zod; chave só na criação); `RunModulesBar.tsx` (executor: padrão da fonte, Claude Code ou Codex; modelo opcional; mostra quantas tarefas entraram e os pulados com o motivo: `already_queued`, `module_disabled`, código desconhecido como veio).
- `JobsTab.tsx`: tarefas paginadas no servidor (20 por página) com status, gatilho, executor e modelo, criação, duração, custo, tokens, aceitos/rejeitados, "Detalhes" e "Cancelar" (`ConfirmDialog`, só tarefa ativa); `JobDetailPanel.tsx` (a escolhida, a mais recente por padrão: commit, tentativas, início, fim, "não antes de", erro e rejeições por motivo, numa página de até 300).
- `RunnerSetupHint.tsx`: estado vazio das duas abas: o que falta, a presença do runner da fonte (só para quem lê runners: owner, admin e editor) e, se ele não estiver online, os comandos para subi-lo (`lib/runnerSetup.ts`, `CopyButton`).
- `HarnessJobStatusBadge.tsx`; `harnessFormat.ts` (SHA curto, duração, tokens, filtro, leitura defensiva das fontes citadas e agrupamento das rejeições) e `moduleForm.ts` (limites do backend, validação dos padrões, valores e corpos de `POST`/`PATCH`), com teste.

**Não entra aqui**: chamadas de API (`lib/api/harness.ts`), cabeçalho e execuções da fonte (`../`), revisão de conhecimento (F4.3), textos (`i18n/locales/`, chaves `harness.*`).

**Convenções locais**:

- Ao vivo: os hooks de `lib/api/harness.ts` refazem a consulta a cada `HARNESS_POLL_INTERVAL_MS` (5 s) enquanto houver tarefa ativa (`queued`, `leased`, `running`, `deferred`, os mesmos do `already_queued` do servidor) e param quando nada está ativo; módulos seguem o `last_job_status`.
- O agrupamento por motivo conta a página carregada (até 300, o máximo da API).
- Padrões de módulo: um por linha, gitwildmatch; o cliente confere forma (até 50, até 300 caracteres, caminho relativo POSIX) e o servidor valida de novo (422 `validation_error`, 409 `module_key_taken`).
- Contagens com `formatCount` e custo com `formatUsd` de `../format.ts` (pt-BR).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/sources/<RUNNER_SOURCE_ID>?tab=jobs" })`) com `sourceStore([makeRunnerSource()])` e `harnessStore(modules, { jobs, rejections, forceSkip })` de `@/test/handlers` (fábricas em `@/test/harnessFactories`); polling com `vi.useFakeTimers({ shouldAdvanceTime: true })`, `finishJob` e `vi.advanceTimersByTimeAsync(HARNESS_POLL_INTERVAL_MS)`.

**Leia também**: [../AGENTS.md](../AGENTS.md); `docs/specs/runner.md` (API de sessão, estados da tarefa); `docs/specs/harness.md` (sugestão de módulos, verificação mecânica).
