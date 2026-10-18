# frontend/src/features/providers/

**Função**: credenciais de provedores de LLM do workspace em `/w/:workspaceId/providers` (owner, admin e editor; viewer não vê o item de menu e recebe 403 na rota). Lista, cadastro, edição, teste de conexão e exclusão.

**Entra aqui**:

- `ProvidersPage.tsx`: `h1`, "Novo provedor", busca (com espera de digitação), filtros, ordenação e paginação no servidor (20 por página), com o estado na query string (`useListSearch`, `ListToolbar`): busca por nome, filtro de tipo e ordenação por nome e datas; vazia, o próximo passo; tabela com nome, tipo, URL base (ou "Padrão do provedor"), chave mascarada (`key_hint`) e as ações "Testar conexão", "Editar" e "Excluir" (com `ConfirmDialog`). O resultado de "Testar conexão" aparece na linha do provedor, junto do botão, pelo `TestResult` de `components/` (ícone e cor; `role="status"` no sucesso, `role="alert"` com o motivo na falha, sem tirar o foco do botão; some quando outro teste começa), e a mensagem completa repete no topo sem anúncio (`FormAlert` com `quiet`, decisão D31 do plano 0011). As demais mensagens ficam no topo pelo `FormAlert` (sucesso na variante `success`).
- `ProviderDialog.tsx`: diálogo de criar/editar com react-hook-form + zod: tipo (travado na edição, o backend não o muda), nome, URL base opcional e chave (campo de senha). Na edição a chave é opcional e a dica mostra só o `key_hint` atual.
- `providerForm.ts`: schema, valores iniciais e corpos de `POST`/`PATCH` (funções puras, com teste).

**Não entra aqui**: chamadas de API (`lib/api/providers.ts`), produtos (`features/products/`), níveis de resposta (`features/settings/`), textos (`i18n/locales/`, chaves `providers.*`; erros em `apiErrors.*`).

**Convenções locais**:

- A chave nunca volta para a tela: o formulário é reiniciado ao abrir e ao fechar o diálogo, e depois de salvar só aparece o `key_hint` que a API devolve. Edição com a chave em branco não a envia (mantém a atual); URL base em branco na edição envia `null` (limpa).
- O teste de conexão responde 200 com `{ok, error}`: a falha do provedor vira mensagem pelo `error.code` (`translateApiErrorCode`); erro da própria API (403, 404) vem por `translateApiError`.
- Excluir provedor usado por assistente responde 409 `provider_in_use`, mostrado no `FormAlert`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/providers" })`) com MSW: `providerStore(initial, { inUse, testResults })` (mudanças persistem; `created`, `changes`, `deleted`, `tested`), `failedTest(code)`, `providersAs`, `providersRecorder` (busca, filtros e ordenação pela query string gravada), `providersServerError`, `createProviderFails`, `updateProviderFails`, `deleteProviderFails`, `testProviderFails`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`/v1/workspaces/{workspace_id}/providers`).
