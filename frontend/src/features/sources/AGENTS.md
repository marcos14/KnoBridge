# frontend/src/features/sources/

**Função**: fontes do workspace em `/w/:workspaceId/sources` e o detalhe de uma fonte em `/w/:workspaceId/sources/:sourceId` (qualquer membro). Owner, admin e editor criam, editam, excluem, testam a conexão, sincronizam e cancelam; viewer vê lista e detalhe sem nenhuma ação de escrita.

**Entra aqui**:

- `SourcesPage.tsx`: layout das duas rotas (lê `:sourceId` com `useMatch`, como coleções) e decide se o papel gerencia (`hasRole(role, "editor")`).
- `SourcesList.tsx`: `h1`, "Nova fonte" (só com coleção; sem nenhuma, aviso com link para `/collections`), tabela paginada no navegador (20 por página) com nome (link para o detalhe), origem, tipo, coleção, última execução (`RunStatusBadge` + tempo relativo), próxima agendada (`NextRun`) e as ações "Sincronizar agora"/"Cancelar sincronização" (`SyncButton`), "Editar" e "Excluir" (`ConfirmDialog`).
- `SourceDialog.tsx` + `LocationFields.tsx` + `ScheduleFields.tsx`: criar/editar com react-hook-form + zod. Coleção e tipo só na criação; Git por clone no servidor (caminho absoluto, dica com o `/sources` do compose) ou URL https pública, branch e commits iniciais (0–5000, padrão 200); pasta pelo caminho; globs (um por linha); agendamento com "sincronizar automaticamente", cron com botões de agendamentos prontos e a leitura em pt-BR; ativa.
- `SourceDetail.tsx`: voltar, configuração, próxima execução, "Testar conexão" (`{ok, error}` com 200 também na falha), sincronizar/cancelar e editar; `RunsSection.tsx` (execuções paginadas no servidor, 10 por página: status, gatilho, início, novos/alterados/removidos/com erro, trechos, tokens, custo, duração; "Ver erros" escolhe a execução, a mais recente por padrão), `RunErrorsPanel.tsx` (falha geral e erros por documento paginados no servidor, 20 por página) e `DocumentsSection.tsx` (documentos paginados no servidor com busca por caminho, `path_match=contains`, e filtro de tipo).
- `RunStatusBadge.tsx`, `NextRun.tsx`, `RelativeTime.tsx`, `Feedback.tsx`, `SyncButton.tsx`: peças pequenas das duas telas.
- `cron.ts`, `format.ts`, `sourceForm.ts`: funções puras com teste (forma do cron, leitura dos formatos comuns, custo, contagens, duração, schema, valores iniciais e corpos de `POST`/`PATCH`).

**Não entra aqui**: chamadas de API (`lib/api/sources.ts`, `lib/api/collections.ts`), coleções (`features/collections/`), textos (`i18n/locales/`, chaves `sources.*`; erros em `apiErrors.*`).

**Convenções locais**:

- Status ao vivo: os hooks de `lib/api/sources.ts` refazem a consulta com `refetchInterval` (`RUN_POLL_INTERVAL_MS`) enquanto houver execução `queued`/`running` e param quando ela termina. Uma consulta de polling que falha mantém os dados na tela; só a primeira carga com falha mostra o erro.
- Cron: o cliente só confere os cinco campos (`isCronShape`) e exige expressão com o agendamento ligado; quem valida é o servidor (`source_schedule_invalid`). Formatos fora de `describeCron` aparecem como "expressão personalizada". Tudo em UTC.
- `PATCH` manda todos os campos editáveis (`config` inteiro; cron vazio vira `schedule_cron: null`), nunca `kind` nem `collection_id`.
- Custo: 4 a 6 casas abaixo de um centavo, 2 a 4 acima; `null` vira "—".

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/sources" })`) com MSW: `sourceStore(initial, { runs, errors, documents, testResults })` (POST com 409 `source_name_taken`, PATCH, DELETE, teste, sync com 409 `source_inactive`/`sync_already_running`, cancel com 409 `sync_not_running`; `finishRun(sourceId, status)` simula o worker; `created`, `changes`, `deleted`, `tested`, `synced`, `cancelled`, `documentQueries`, `reads`), `sourcesAs`, `sourceActionFails(action, status, code)` e os `*ServerError`. Polling: `vi.useFakeTimers({ shouldAdvanceTime: true })` e `vi.advanceTimersByTimeAsync(RUN_POLL_INTERVAL_MS)` só nesses testes, sem sleep.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../collections/AGENTS.md](../collections/AGENTS.md); `docs/specs/openapi.json` (`/v1/workspaces/{workspace_id}/sources`, `/runs/{run_id}`).
