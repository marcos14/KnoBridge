# frontend/src/lib/

**Função**: código sem interface. Utilitários puros e, em `api/`, o acesso ao backend.

**Entra aqui**:

- `utils.ts`: `cn()` (junta classes e resolve conflitos do Tailwind), usado pelos componentes do shadcn/ui e pelos nossos.
- `storage.ts`: `readStoredItem`/`writeStoredItem`/`removeStoredItem`, acesso ao `localStorage` (padrão) ou ao `sessionStorage` (`"session"`, só a aba atual) que nunca lança (janela privada, dados bloqueados → "nada guardado"). Só para conveniências do navegador (tema, último workspace, convite pendente durante o login).
- `theme.ts`: `Theme`, `THEMES`, `resolveTheme`, `applyTheme` (classe `dark` e `color-scheme` no `<html>`), `storeTheme`. A chave `knobridge-theme` é lida também pelo script inline do `index.html` (primeiro paint): mude os dois juntos.
- `lastWorkspace.ts`: último workspace usado (`localStorage`) e `pickWorkspace` (último, se ainda membro e ativo; senão o primeiro ativo; senão o primeiro).
- `initials.ts`: iniciais para o avatar.
- `roles.ts`: papéis do workspace (`ROLES`, do mais ao menos privilegiado; `hasRole`; `canManageWorkspace`, owner ou admin; `canHandleRole`, quem pode conceder um papel ou gerenciar quem o tem, espelhando o `role_not_allowed` do backend; `findWorkspace`).
- `pagination.ts`: paginação por `offset` (`pageRange` para o "1–20 de 45", `clampOffset` para voltar à última página válida, `pageOf` para listas paginadas no navegador, `parseOffset` para o `offset` lido da URL).
- `schemas.ts`: campos zod dos formulários (`nameField`, `workspaceNameField`, `optionalSlugField` (identificador de workspace opcional, `SLUG_PATTERN`/`SLUG_MAX_LENGTH` do backend), `emailField`, `newPasswordFields` + `withMatchingPasswords`), com os limites do backend (`PASSWORD_MIN_LENGTH` 12, `PASSWORD_MAX_LENGTH` 1024, `NAME_MAX_LENGTH`, `EMAIL_MAX_LENGTH`); mensagens via `t` (chaves `auth.validation.*` e `workspaceSettings.nameRequired`).
- `auditActions.ts`: `AUDIT_ACTIONS` (todas as ações do contrato, num `Record<AuditAction, true>` para o typecheck acusar ação nova sem entrada) e `isAuditAction`.
- `auditFilters.ts`: filtros da auditoria na query string (`parseAuditSearch`, que descarta valor que a API recusaria; `auditSearchParams`), `toAuditQuery` (dias inclusivos → `[início de "De", início do dia seguinte a "Até")` no fuso do navegador), `hasAuditFilters` e `formatDetailValue` (valor de `details` para leitura).
- `conversationFilters.ts`: filtros da tela de conversas na query string (`parseConversationSearch`, `conversationSearchParams`: `assistant`, `user`, `channel` (`panel` ou `api`, com `CONVERSATION_CHANNELS` e `parseChannel`), `from`, `to`, `negative=1`, `offset`), `toConversationsQuery`, `toCreationPeriod` (o mesmo período semiaberto, para a lista e os totais) e `hasConversationFilters`.
- `listSearch.ts`: estado das listagens na query string (`?q=`, filtros, `sort`, `offset`): `ListSearchSpec` (validador por filtro e ordenações, a primeira é a padrão), `parseListSearch` (descarta valor que a API recusaria), `listSearchParams` (padrões não deixam rastro), `hasListCriteria`, `normalizeQuery` (sem espaços nas pontas, até `QUERY_MAX_LENGTH` = 200), `oneOf`, `isBooleanFilter`/`booleanFilter` e `sortLabelKey` (rótulo i18n de cada ordenação em `listToolbar.sorts.*`).
- `days.ts`: dias `YYYY-MM-DD` dos filtros de período (`validDay`, `dayStart`: meia-noite local como instante UTC ISO; `dayPeriod(from, to)`: dias inclusivos → `[início, fim)`).
- `uuid.ts`: `isUuid`, para descartar id malformado vindo da URL.
- `citationMarkers.ts`: plugin remark que troca `[n]` de uma citação existente por link `#citation-n` (`remarkCitationMarkers`, `citationIndexFromHref`) e `isWebUri` (só `http(s)` vira link).
- `citationLocation.ts`: onde uma citação aponta (`citationSource`: `knowledge` (v0.5) com a chave do item tirada de `knowledge:<chave>`, o selo `inferido`/`revisado` e as evidências; `ticket` (v0.6) com número, status (`TicketStatus`), data e qual data é (`resolved`/`updated`) e o link só quando é `http(s)`; `commit` com SHA curto de 7, autor e data (v0.4, `null` antes), `file` com caminho, linhas, símbolo e linguagem, ou `legacy` para respostas gravadas antes da v0.3), `lineRange` e `citationLines` (`L10–L20`, `L10`), `evidenceLocation` (uma evidência de conhecimento como `caminho:L80–L92`, usada pelo chat e pela revisão), `citationLocation` (linha curta da lista de fontes; no conhecimento, a primeira evidência e "+N"; no chamado, `null`, porque número e status são texto traduzido pela interface), `webUrl` (o link só quando é `http(s)`, senão `null`; também usado pelo estado do pedido de chamado no chat), `citationDate` (o dia de uma data ISO em pt-BR, ou o texto como veio) e `commitAuthorship` ("Ana Souza · 1 de out. de 2026", só a parte conhecida, data não reconhecida como veio).
- `firstSteps.ts`: `pendingSteps(checklist, workspaceId, role)`, os passos pendentes do checklist do Início na ordem da API, cada um com o link da tela ou `undefined` quando o papel não faz o passo (editor para provedor, coleção, fonte e assistente; viewer para o chat, como em `docs/specs/uso-e-custos.md`).
- `serviceHealth.ts`: `serviceDetailKey(detail)`, a chave i18n de cada `detail` conhecido de `GET /v1/admin/health` (desconhecido aparece como veio).
- `intl.ts`: `formatRelativeTime(date, now, locale)` ("há 5 minutos", "em 2 horas"), `formatDateTime(date, locale, timeZone?)`, `formatDate(date, locale, timeZone?)` (só o dia) e `languageName(tag, locale)`, com `Intl`. O "agora" é sempre parâmetro (nos componentes, de `useClock()`).
- `userAgent.ts`: `summarizeUserAgent` (navegador e sistema de um `User-Agent`, ou `null`).
- `runnerStatus.ts`: presença de um runner (`runnerStatus(runner, now)`: `revoked`, `online` com `last_seen_at` até `ONLINE_WINDOW_MS` (90 s, a janela do servidor) antes de `now`, senão `offline`), `isHarnessExecutor` e `executorState` (`ready`, `notAuthenticated`, `unavailable`). Usado pela tela de runners e pelo formulário da fonte runner.
- `runnerSetup.ts`: `runnerSetupCommands(serverUrl, repository)`, as linhas que instalam e configuram o runner (sem o token), usadas pelo cadastro de runner e pelo estado vazio da fonte runner.
- `numberFormat.ts`: `formatUsd` (US$ com 4 a 6 casas abaixo de um centavo, "—" para preço desconhecido) e `formatCount`, usados pelas fontes e por uso e custos.
- `usagePeriod.ts`: período e agrupamento da tela de uso na query string (`parseUsageSearch`, `usageSearchParams`: `period`, `from`, `to`, `group`), `presetDays` (este mês, mês passado, últimos 30 dias, em dias UTC), `searchDays` e `usagePeriod` (dias inclusivos → `[meia-noite UTC, meia-noite UTC do dia seguinte)`).
- `download.ts`: `attachmentFilename(header)` (nome do arquivo de um `Content-Disposition`: `filename*` UTF-8 quando decodifica, senão `filename`; sem pastas nem caracteres que o sistema de arquivos recusa) e `saveBlob(blob, nome)` (download pelo navegador com uma URL de objeto temporária), usados pela exportação do conhecimento e do CSV de uso.
- `api/`: cliente gerado do OpenAPI e hooks TanStack Query (ver [api/AGENTS.md](api/AGENTS.md)).
- Futuramente: funções puras de domínio usadas por várias features (formatação, validação, transformação do grafo do canvas).

**Não entra aqui**: componentes React (`components/` ou `features/`), textos de interface (`i18n/`), helpers de teste (`test/`).

**Convenções locais**:

- Funções puras, pequenas e tipadas; sem estado global nem efeitos colaterais na importação (exceção: a instância `apiClient`). Efeitos no navegador (`localStorage`, `<html>`) só em funções chamadas explicitamente.
- Cobertura de 100% esperada: cada função com teste ao lado (`*.test.ts`).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../AGENTS.md](../../AGENTS.md).
