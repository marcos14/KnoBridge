# frontend/src/features/collections/

**Função**: coleções do workspace em `/w/:workspaceId/collections` e o detalhe de uma coleção em `/w/:workspaceId/collections/:collectionId` (qualquer membro). Owner, admin e editor criam, editam e excluem; viewer vê a lista e o detalhe e pode testar a busca (a rota de busca aceita qualquer membro), sem nenhuma ação de escrita na tela.

**Entra aqui**:

- `CollectionsPage.tsx`: layout das duas rotas (lê `:collectionId` com `useMatch`, como conversas) e decide se o papel gerencia (`hasRole(role, "editor")`).
- `CollectionsList.tsx`: `h1`, "Nova coleção" (só com credencial de embedding; sem nenhuma, aviso com link para `/providers`), tabela paginada no navegador (20 por página) com nome (link para o detalhe) e descrição, credencial e modelo, fontes, documentos e trechos, e as ações "Editar" e "Excluir" (com `ConfirmDialog`; 409 `collection_in_use` no `FormAlert`).
- `CollectionDialog.tsx`: criar/editar com react-hook-form + zod: nome, descrição, credencial de embedding (só as que não são `anthropic`) e modelo. Com documentos na coleção, credencial e modelo ficam desabilitados com a dica, e o `PATCH` não os envia.
- `CollectionDetail.tsx`: voltar, nome, modelo e contagens, "Editar" (gestores), `CollectionSources.tsx` (fontes da coleção pelo filtro `collection_id` da API, com tipo, documentos e última sincronização; link para `/sources`) e `SearchPanel.tsx` ("Testar busca": consulta, similaridade mínima opcional, resultados com local, pontuações e trecho em `<pre><code class="language-…">`, estado vazio que explica o limiar).
- `collectionForm.ts` e `searchResult.ts`: funções puras com teste (schemas, corpos, modelo sugerido, travamento, local do trecho, formatação das pontuações).

**Não entra aqui**: chamadas de API (`lib/api/collections.ts`, `lib/api/sources.ts`, `lib/api/providers.ts`), cadastro e sincronização de fontes (área de fontes), textos (`i18n/locales/`, chaves `collections.*`; erros em `apiErrors.*`).

**Convenções locais**:

- Modelo sugerido pela credencial: `openai/text-embedding-3-small` (OpenRouter e Fake; o Fake aceita qualquer texto) e `text-embedding-3-small` (OpenAI direta). Trocar a credencial troca o modelo só se ele ainda for uma sugestão; modelo digitado fica. O campo oferece num `<datalist>` os modelos de `embeddingModelOptions(kind)` (OpenAI direta: `text-embedding-3-small`; OpenRouter e Fake: `OPENROUTER_EMBEDDING_MODELS`, com `google/gemini-embedding-001` e `-2`); qualquer outro id pode ser digitado.
- Viewer não lê credenciais (a API responde 403): a lista mostra só o modelo e `useProviders` fica desligado (`enabled: false`).
- Pontuações: fusão com 4 casas, vetorial com 2, texto com 3; `—` quando o braço não achou o trecho. A busca sempre envia `min_similarity` (em branco, 0,35, o padrão da API, do [ensaio](../../../../docs/pesquisa/0001-ensaio-minski.md)) e `limit` 10.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/collections" })`) com MSW: `collectionStore(initial)` (POST com 409 `collection_name_taken`, PATCH com 409 `collection_embedding_locked`, DELETE com 409 `collection_in_use` quando há fontes; `created`, `changes`, `deleted`), `collectionsAs`, `collectionsServerError`, `collectionServerError`, `createCollectionFails`, `searchRecorder(results)` (`bodies`), `searchFails`, `sourcesAs`, `sourcesServerError`, `providersAs`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../providers/AGENTS.md](../providers/AGENTS.md); `docs/specs/openapi.json` (`/v1/workspaces/{workspace_id}/collections`, `/search`, `/sources`).
