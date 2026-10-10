# frontend/src/lib/

**Função**: código sem interface. Utilitários puros e, em `api/`, o acesso ao backend.

**Entra aqui**:

- `utils.ts`: `cn()` (junta classes e resolve conflitos do Tailwind), usado pelos componentes do shadcn/ui e pelos nossos.
- `storage.ts`: `readStoredItem`/`writeStoredItem`/`removeStoredItem`, acesso ao `localStorage` (padrão) ou ao `sessionStorage` (`"session"`, só a aba atual) que nunca lança (janela privada, dados bloqueados → "nada guardado"). Só para conveniências do navegador (tema, último workspace, convite pendente durante o login).
- `theme.ts`: `Theme`, `THEMES`, `resolveTheme`, `applyTheme` (classe `dark` e `color-scheme` no `<html>`), `storeTheme`. A chave `knobridge-theme` é lida também pelo script inline do `index.html` (primeiro paint): mude os dois juntos.
- `lastWorkspace.ts`: último workspace usado (`localStorage`) e `pickWorkspace` (último, se ainda membro e ativo; senão o primeiro ativo; senão o primeiro).
- `initials.ts`: iniciais para o avatar.
- `roles.ts`: papéis do workspace (`ROLES`, do mais ao menos privilegiado; `hasRole`; `canManageWorkspace`, owner ou admin; `canHandleRole`, quem pode conceder um papel ou gerenciar quem o tem, espelhando o `role_not_allowed` do backend; `findWorkspace`).
- `pagination.ts`: paginação por `offset` (`pageRange` para o "1–20 de 45", `clampOffset` para voltar à última página válida, `pageOf` para listas paginadas no navegador).
- `schemas.ts`: campos zod dos formulários (`nameField`, `workspaceNameField`, `optionalSlugField` (identificador de workspace opcional, `SLUG_PATTERN`/`SLUG_MAX_LENGTH` do backend), `emailField`, `newPasswordFields` + `withMatchingPasswords`), com os limites do backend (`PASSWORD_MIN_LENGTH` 12, `PASSWORD_MAX_LENGTH` 1024, `NAME_MAX_LENGTH`, `EMAIL_MAX_LENGTH`); mensagens via `t` (chaves `auth.validation.*` e `workspaceSettings.nameRequired`).
- `auditActions.ts`: `AUDIT_ACTIONS` (todas as ações do contrato, num `Record<AuditAction, true>` para o typecheck acusar ação nova sem entrada) e `isAuditAction`.
- `auditFilters.ts`: filtros da auditoria na query string (`parseAuditSearch`, que descarta valor que a API recusaria; `auditSearchParams`), `toAuditQuery` (dias inclusivos → `[início de "De", início do dia seguinte a "Até")` no fuso do navegador), `hasAuditFilters` e `formatDetailValue` (valor de `details` para leitura).
- `intl.ts`: `formatRelativeTime(date, now, locale)` ("há 5 minutos", "em 2 horas"), `formatDateTime(date, locale, timeZone?)` e `languageName(tag, locale)`, com `Intl`. O "agora" é sempre parâmetro (nos componentes, de `useClock()`).
- `userAgent.ts`: `summarizeUserAgent` (navegador e sistema de um `User-Agent`, ou `null`).
- `api/`: cliente gerado do OpenAPI e hooks TanStack Query (ver [api/AGENTS.md](api/AGENTS.md)).
- Futuramente: funções puras de domínio usadas por várias features (formatação, validação, transformação do grafo do canvas).

**Não entra aqui**: componentes React (`components/` ou `features/`), textos de interface (`i18n/`), helpers de teste (`test/`).

**Convenções locais**:

- Funções puras, pequenas e tipadas; sem estado global nem efeitos colaterais na importação (exceção: a instância `apiClient`). Efeitos no navegador (`localStorage`, `<html>`) só em funções chamadas explicitamente.
- Cobertura de 100% esperada: cada função com teste ao lado (`*.test.ts`).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../AGENTS.md](../../AGENTS.md).
