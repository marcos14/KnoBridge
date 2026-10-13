# frontend/src/features/apikeys/

**Função**: chaves de API do workspace em `/w/:workspaceId/api-keys` (owner e admin; editor e viewer não veem o item de menu e recebem 403 na rota). Lista, criação com a chave mostrada uma única vez, edição de nome e escopo, revogação e exemplos de uso da API pública.

**Entra aqui**:

- `ApiKeysPage.tsx`: `h1`, "Nova chave", tabela paginada no navegador (20 por página; a lista inteira vem de `useApiKeys`) com nome e prefixo (`kbk_<prefixo>_…`), escopo ("Todos os assistentes", os nomes dos escolhidos, a contagem enquanto a lista de assistentes não carrega, ou "Nenhum assistente" quando todos foram excluídos), criada em (e por quem), último uso (tempo relativo ou "Nunca usada"), estado (ativa ou revogada) e, só nas ativas, "Editar" e "Revogar" (com `ConfirmDialog`); abaixo, `ApiKeyExamples`.
- `ApiKeyDialog.tsx`: criar ou editar (react-hook-form + zod): nome e escopo (rádio "todos os assistentes ativos" ou "só os escolhidos", com a lista de assistentes do workspace, inativos marcados). Depois do `POST`, a visão da chave com `CopyButton`; na edição, só os campos alterados vão no `PATCH`, e sem mudança nada é enviado.
- `ApiKeyExamples.tsx`: "Como usar", com `curl` da REST própria e Python e JavaScript com o SDK oficial da OpenAI, cada um com `CopyButton`; servidor `window.location.origin`, modelo = nome do primeiro assistente ativo (sem nenhum, marcadores).
- `apiKeyForm.ts`: schema do formulário, valores iniciais, corpo do `POST` e diferença para o `PATCH` (`product_ids: null` = todos). O `POST` manda `max_level` (obrigatório na API) com `API_KEY_DEFAULT_MAX_LEVEL` = `product_dev`, o alcance que as chaves sempre tiveram, até a F3.3 do plano 0009 trazer a escolha do nível no formulário.
- `usageExamples.ts`: os textos dos exemplos (`restCurlExample`, `openAiPythonExample`, `openAiJavaScriptExample`, `apiBaseUrl`) e `API_KEY_VARIABLE` (`KNOBRIDGE_API_KEY`).

**Não entra aqui**: chamadas de API (`lib/api/apiKeys.ts`), produtos (`lib/api/products.ts`), o botão de copiar (`components/CopyButton.tsx`), textos (`i18n/locales/`, chaves `apiKeys.*`; erros `apiErrors.api_key_*`).

**Convenções locais**:

- A chave só existe no estado do diálogo: abrir e fechar o diálogo a descartam, e nenhuma consulta a guarda. Os exemplos nunca levam a chave: leem `KNOBRIDGE_API_KEY` do ambiente.
- Revogar é irreversível; chave revogada não tem ações (editar responderia 409 `api_key_revoked`). Não há exclusão.
- As citações dos exemplos vêm de `message.citations` (REST) e do campo `knobridge` (compatível com OpenAI), como em `docs/specs/api-publica.md`.

**Como testar**: de `frontend/`, `pnpm vitest run src/features/apikeys --coverage.enabled=true --coverage.include='src/features/apikeys/**'`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/api-keys" })`) com MSW: `apiKeyStore(initial, assistantIds)` (`created`, `changes`, `revoked`), `apiKeysAs`, `apiKeysServerError`, `apiKeyActionFails(action, status, code)`; clipboard pelo stub do `userEvent.setup()`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/api-publica.md`; [ADR 0007](../../../../docs/adr/0007-chaves-e-api-publica.md).
