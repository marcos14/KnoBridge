# frontend/src/features/sources/tickets/

**Função**: o corpo do detalhe de uma fonte do tipo `tickets` (`/w/:workspaceId/sources/:sourceId`) para owner, admin e editor: abas **Integração**, **Upload**, **Prévia** e **Indexação** (execuções e documentos de `../`). Viewer vê só o cabeçalho e as execuções e documentos, sem abas.

**Entra aqui**:

- `TicketsSourceTabs.tsx` + `tabs.ts`: as abas, com a aberta em `?tab=` (`parseTicketsSourceTab`; desconhecida ou ausente abre a primeira). Aba nova = um id em `TICKETS_SOURCE_TABS`, o rótulo em `tickets.tabs.<id>` e o conteúdo no `switch`.
- `IntegrationTab.tsx`: token de envio e exemplos de `POST /v1/ingest/tickets` (`curl` e Python só com a biblioteca padrão, de `ingestExamples.ts`) com a origem do painel (`window.location.origin`) e o token lido da variável `KNOBRIDGE_INGEST_TOKEN`, nunca embutido; `CopyButton` em cada um. `IngestTokenDialog.tsx` (owner e admin): confirma que um token atual deixa de valer, gera e mostra o token uma única vez com "Copiar token"; fechar o diálogo descarta o token. Editor vê só os exemplos e o aviso de que owner ou admin gera o token.
- `UploadTab.tsx`: arquivo `.json`/`.jsonl` (o cliente confere arquivo escolhido, extensão e 50 MiB; o servidor confere de novo), envio em `multipart/form-data` e `UploadReport.tsx` (total, formato, o que aconteceu com a sincronização, contagens por status e os itens recusados em `DataTable` paginada no navegador, 20 por página: linha (`.jsonl`) ou posição (`.json`), chamado, erro conhecido traduzido ou a mensagem do servidor, problemas `campo: problema` e a linha ou posição do primeiro em `duplicate_in_batch`; aviso de lista cortada em 1000).
- `PreviewTab.tsx`: colar um chamado em JSON (vazio, JSON inválido ou não objeto são recusados antes de enviar), ver o título, se anonimizou e se incluiu notas internas, os marcadores aplicados com a contagem e o Markdown; 422 com os problemas do chamado.
- `TicketsSummary.tsx`: linhas do cabeçalho (origem, anonimização, notas internas, status indexados).
- `ticketFormat.ts` (limite e extensões do upload, `uploadFileProblem`, `ticketProblems`, `uploadErrorPosition`, `duplicateOf`, `parsePastedTicket`) e `ingestExamples.ts`, funções puras com teste.

**Não entra aqui**: chamadas de API (`lib/api/tickets.ts`), campos da fonte no formulário (`../TicketsFields.tsx`, `../ticketsSourceForm.ts`), citação de chamado no chat (`components/CitationSheet.tsx`, `components/AssistantMessage.tsx`, `lib/citationLocation.ts`), textos (`i18n/locales/`, chaves `tickets.*`).

**Convenções locais**:

- Não há rota de resumo da caixa de entrada no OpenAPI (`GET .../tickets/summary` está na spec, mas não no contrato gerado): a tela não mostra o prefixo do token nem as contagens da caixa de entrada. "Testar conexão" diz se a fonte tem token (`ingest_token_missing`).
- O token só existe no estado do diálogo; nada o guarda em cache, URL ou `localStorage`.
- O upload recarrega a fonte e as execuções (a sincronização pode ter começado); prévia e token não mudam nada em cache.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/sources/<TICKETS_SOURCE_ID>?tab=upload" })`) com `sourceStore([makeTicketsSource()])` e `ticketStore({ token, report, preview })` de `@/test/handlers` (fábricas em `@/test/ticketFactories`); papéis com `meAs(makeMe({ workspaces: [makeWorkspace({ role })] }))`. Sob jsdom o `fetch` do Node não lê o `File` do jsdom (envia vazio): o handler confere só a parte `file` e o teste espia `FormData.prototype.append`.

**Leia também**: [../AGENTS.md](../AGENTS.md); `docs/specs/chamados.md` ("Envio pela API", "Upload no painel", "Prévia do chamado", "Fonte do tipo tickets").
