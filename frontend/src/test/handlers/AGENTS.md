# frontend/src/test/handlers/

**Função**: handlers MSW que simulam a API nos testes, um arquivo por recurso, tipados pelo `schema.gen.ts`.

**Entra aqui**:

- `index.ts`: reexporta tudo e define `handlers`, os padrões do servidor (caminho feliz: instância configurada, usuário logado, API pronta).
- `errors.ts`: `apiErrorResponse(status, code, details?)`, resposta no formato de erro padrão.
- `health.ts`: `healthReadyOk` (padrão), `healthReadyUnavailable`, `healthReadyNetworkError`, `healthReadyPending`.
- `setup.ts`: `setupStatusDone` e `setupOk` (padrão), `setupStatusNeeded`, `setupStatusServerError`, `setupAlreadyCompleted`.
- `auth.ts`: `meOk`, `updateProfileOk` (`PATCH /v1/me`, aplica o corpo ao usuário padrão), `loginOk`, `logoutOk`, `csrfOk` (padrão), `meAs(me)`, `meUnauthenticated`, `meServerError`, `updateProfileCsrfFailed`, `loginInvalidCredentials`, `logoutUnauthenticated`, `logoutCsrfFailed`.

**Não entra aqui**: fábricas de dados (`../factories.ts`), testes, dados reais.

**Convenções locais**:

- Caminhos casam qualquer origem (`*/v1/...`), para não depender da `baseUrl`.
- Um handler padrão por endpoint usado pelo app (entra em `<recurso>Handlers` e em `handlers`); variações exportadas com nome que diz o cenário, para `server.use(...)`.
- Corpos de sucesso vêm de `../factories.ts`; erros, de `apiErrorResponse` com o `code` real do backend.
- Recurso novo: arquivo novo aqui e uma linha em `index.ts`.

**Como testar**: exercitada indiretamente por `pnpm test -- --coverage`, de `frontend/`.

**Leia também**: [../AGENTS.md](../AGENTS.md); `docs/specs/openapi.json`.
