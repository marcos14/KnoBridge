# Cards de desenvolvimento

> Rascunho v0.2 · 2026-10-13 · Plano 0009, F1.1 (v0.1); v0.2, F2.3: implementado, com os detalhes do Markdown e dos marcadores fixados abaixo

Como cards de desenvolvimento (itens de Jira, Azure DevOps, GitHub Issues, Trello ou qualquer ferramenta) entram no KnoBridge e viram fonte do chat no nível **desenvolvimento e produto**. Os cards seguem **o mesmo caminho dos chamados** (D5 do [plano 0009](../planos/0009-produtos-e-niveis.md)): formato padrão do KnoBridge, envio por push com token ou upload, caixa de entrada com a regra do `updated_at`, conector interno no workflow de ingestão e apagamento do bruto. Esta spec só descreve **o que difere**; todo o resto é o de [chamados.md](chamados.md), lendo "card" onde lá está "chamado". Os níveis estão em [produtos-e-niveis.md](produtos-e-niveis.md).

Código: o pacote `backend/src/knobridge/tickets/` tem o tipo card (formato em `card_wire.py`, Markdown em `card_markdown.py`, o que difere entre chamado e card em `push.py`, conector `cards` ao lado do `tickets` em `connector.py`); validação, caixa de entrada, upload e prévia são as dos chamados com o tipo card (`ingest.py`, `ingest_sync.py`, `upload.py`). Rotas em `api/ingest.py` (`/v1/ingest/cards`), `api/card_uploads.py` (upload e prévia) e `api/ingest_tokens.py` (resumo); citação em `retrieval/context.py`; regra do prompt em `conversations/prompt.py`. Telas do painel (F3.2): a fonte `cards` é criada e editada como a de chamados, com as mesmas abas Integração (token e exemplos de `/v1/ingest/cards`), Upload, Prévia e Indexação, em `frontend/src/features/sources/push/`; ela não é reindexada.

## O que é igual aos chamados

| Assunto | Regra (em [chamados.md](chamados.md)) |
|---|---|
| Convenções de JSON, textos, instantes e erros | [Convenções](chamados.md#convenções) |
| Token de envio `kbi_…`, um por fonte, gerado em `POST .../sources/{sid}/ingest-token` | [Token de envio](chamados.md#token-de-envio) |
| Corpo do envio (`items`, `op: upsert`/`delete`, até 100 itens, 5 MiB), resposta 202 por item, códigos de erro | [`POST /v1/ingest/tickets`](chamados.md#post-v1ingesttickets), com `card` no lugar de `ticket` no item `upsert` |
| Idempotência, hash canônico, lápides e a regra do `updated_at` | [Idempotência](chamados.md#idempotência-e-regra-do-updated_at) |
| Upload `.json`/`.jsonl` (até 50 MiB, em fluxo, lotes de 100) e prévia | [Upload no painel](chamados.md#upload-no-painel), [Prévia](chamados.md#prévia-do-chamado) |
| Caixa de entrada, estados, disparo da sincronização, fechamento do item e apagamento do bruto | [Caixa de entrada](chamados.md#caixa-de-entrada); a mesma tabela `ticket_inbox` guarda as entradas das fontes `cards`, porque o tipo da fonte define o schema do payload |
| Anonimização (regras, marcadores, nomes declarados) | [Anonimização](chamados.md#anonimização), com os campos da tabela [Onde se aplica](#anonimização) abaixo |

## O que difere

### Rotas

| Rota | Autenticação | Igual a |
|---|---|---|
| `POST /v1/ingest/cards` | token `kbi_…` de uma fonte `cards` | `POST /v1/ingest/tickets` |
| `POST /v1/workspaces/{wid}/sources/{sid}/cards/upload` | sessão, CSRF, editor | `.../tickets/upload` |
| `POST /v1/workspaces/{wid}/sources/{sid}/cards/preview` | sessão, CSRF, editor | `.../tickets/preview` |
| `GET /v1/workspaces/{wid}/sources/{sid}/cards/summary` | sessão, viewer | `.../tickets/summary` |

- Token de uma fonte `tickets` em `/v1/ingest/cards` (ou de uma fonte `cards` em `/v1/ingest/tickets`): 409 `source_kind_mismatch` com `details = {"expected", "actual"}`; nada é gravado.
- As rotas de upload, prévia e resumo com uma fonte de outro tipo: 404 `source_not_found`.
- Nomes no OpenAPI: `CardIn`, `CardCommentIn`, `CardPersonIn`, `CardSprintIn`, `CardLinkIn`, `CardDescriptionIn`, `CardAttachmentIn`, `CardUpsertItemIn`, `CardDeleteItemIn`, `CardIngestIn`, `CardPreviewIn` e `CardPreviewOut` (com `markers` em `TicketPreviewMarker` e `include_comments` no lugar de `include_internal_notes`), além dos enums `CardType`, `CardStatus` e `CardLinkKind`; as respostas por item, de upload e de resumo reaproveitam os schemas dos chamados (`TicketIngestOut`, `TicketUploadOut`, `TicketsSummaryOut`). `CardsSourceConfig`, como `TicketsSourceConfig`, não vira schema: a API recebe e devolve `config` como objeto.
- Auditoria do upload: `source.cards_uploaded`, com os mesmos `details` de `source.tickets_uploaded`.

### Formato do card (`CardIn`)

| Campo | Tipo | Obrigatório | Regras |
|---|---|---|---|
| `external_id` | texto | sim | Id estável na ferramenta de origem, 1 a 200 caracteres, sem caractere de controle. Chave do card na fonte. |
| `number` | texto ou `null` | não | Número exibido (`"PROJ-123"`, `"#482"`), 1 a 50 caracteres. Sem ele, a citação mostra o `external_id`. |
| `title` | texto | sim | 1 a 500 caracteres. |
| `type` | `feature`, `bug`, `task`, `story`, `epic` ou `other` | sim | Tipo normalizado. |
| `status` | `backlog`, `in_progress`, `done` ou `cancelled` | sim | Status normalizado (tabela abaixo). |
| `original_status` | texto ou `null` | não | Status como a ferramenta chama, até 100 caracteres. |
| `original_type` | texto ou `null` | não | Tipo como a ferramenta chama, até 100 caracteres. |
| `priority` | texto ou `null` | não | Livre, até 50 caracteres. |
| `product` | texto ou `null` | não | Produto, módulo ou componente, até 200 caracteres. |
| `tags` | lista de textos | não | Rótulos, até 50, cada um de 1 a 100 caracteres, sem repetição. Padrão `[]`. |
| `url` | texto ou `null` | não | Link do card na ferramenta: `http` ou `https`, até 2000 caracteres. |
| `description` | objeto ou `null` | não | `{body, body_format}`: 1 a 100 000 caracteres; `body_format` `text`, `markdown` ou `html` (padrão `text`). |
| `acceptance_criteria` | objeto ou `null` | não | Mesmo formato de `description`. |
| `sprint` | objeto ou `null` | não | `{name, start_at, end_at}`: `name` de 1 a 200 caracteres, datas opcionais (instantes). `end_at` não pode ser anterior a `start_at`. |
| `release` | texto ou `null` | não | Versão ou entrega em que o card saiu ou vai sair (`"12.5"`), até 100 caracteres. |
| `parent_external_id` | texto ou `null` | não | `external_id` do card pai (épico), mesmas regras do `external_id`. |
| `links` | lista | não | Até 100 ligações (abaixo). Padrão `[]`. |
| `reporter` | objeto ou `null` | não | `{name, email}` de quem abriu (mesmos limites dos chamados). |
| `assignees` | lista | não | Até 20 responsáveis, cada um `{name, email}`. Padrão `[]`. |
| `comments` | lista | não | Até 500 comentários (abaixo). Padrão `[]`. |
| `attachments` | lista | não | Até 100 `{name}` (1 a 255 caracteres). Só os nomes. Padrão `[]`. |
| `custom_fields` | objeto | não | Como nos chamados. |
| `created_at` | instante | sim | Criação. |
| `updated_at` | instante | sim | Última alteração na origem. Decide a idempotência. Não pode ser anterior a `created_at`. |
| `done_at` | instante ou `null` | não | Quando chegou a `done` (ou `cancelled`). |

Cada ligação (`CardLinkIn`):

| Campo | Tipo | Obrigatório | Regras |
|---|---|---|---|
| `kind` | `card`, `ticket`, `commit`, `pull_request` ou `url` | sim | O que está do outro lado. |
| `target` | texto | sim | 1 a 200 caracteres: `external_id` ou número do card, número do chamado, SHA do commit (7 a 64 hex), número do PR, ou um rótulo para `url`. |
| `relation` | texto ou `null` | não | Como a ferramenta chama a ligação (`"bloqueia"`, `"duplica"`, `"relaciona"`, `"corrige"`), até 100 caracteres. |
| `url` | texto ou `null` | não | `http` ou `https`, até 2000 caracteres; obrigatório quando `kind = url`. |

Cada comentário (`CardCommentIn`): `id` (opcional), `author_name` (opcional, até 200, anonimizado), `body` (1 a 100 000), `body_format` (padrão `text`) e `created_at` (instante). Não há `role` nem nota interna: todo comentário de card é interno por natureza e o nível mínimo da fonte já o protege.

Limite: um card serializado tem no máximo 1 MiB (`card_too_large`). Problemas extras de validação, além dos dos chamados: `sprint_end_before_start`, `link_url_required`, `invalid_sha`.

### Status e tipo normalizados

| `status` | Significado | Na citação |
|---|---|---|
| `backlog` | Ainda não começou (backlog, a fazer, novo). | Backlog |
| `in_progress` | Em andamento (desenvolvimento, revisão, teste). | Em andamento |
| `done` | Concluído e entregue. | Concluído |
| `cancelled` | Cancelado ou descartado. | Cancelado |

| `type` | Na citação |
|---|---|
| `feature` | Funcionalidade |
| `bug` | Bug |
| `task` | Tarefa |
| `story` | História |
| `epic` | Épico |
| `other` | Outro |

### Fonte do tipo `cards`

`sources.kind = cards`, nível mínimo padrão **`product_dev`** ([produtos-e-niveis.md](produtos-e-niveis.md#padrões-por-tipo)). `CardsSourceConfig`, campos desconhecidos recusados (422 `source_config_invalid`):

| Campo | Tipo | Regras |
|---|---|---|
| `anonymize` | booleano | Padrão `true`. Cards copiam trechos de chamados com dados de clientes; desligue só se a ferramenta não guarda dado pessoal. |
| `include_comments` | booleano | Padrão `true`. |
| `statuses` | lista | Subconjunto não vazio de `backlog`, `in_progress`, `done`, `cancelled`. Padrão: os quatro. |

Globs não se aplicam (como nos chamados). Testar conexão, sincronizar e excluir: como em [Fonte do tipo tickets](chamados.md#fonte-do-tipo-tickets).

### Anonimização

Aplica-se a `title`, `original_status`, `original_type`, `priority`, `product`, `tags`, `description`, `acceptance_criteria`, `sprint.name`, `release`, `relation` e `target` das ligações `url`, corpo dos comentários, `author_name`, valores texto de `custom_fields` e nomes dos anexos. Não se aplica a `external_id`, `number`, `type`, `status`, datas, `parent_external_id`, `target` das ligações `card`, `ticket`, `commit` e `pull_request` (identificadores) e `url`. `reporter` e `assignees` nunca são renderizados: servem só para descobrir os nomes a trocar (marcadores `[RELATOR]` e `[RESPONSAVEL_n]`).

Nomes declarados, com as regras de comparação dos chamados: `reporter.name` → `[RELATOR]`; `assignees[].name` e depois os `author_name` dos comentários ainda não declarados → `[RESPONSAVEL_1]`, `[RESPONSAVEL_2]`… na ordem da primeira aparição. Nome completo e primeiro nome (3 letras ou mais) são trocados. Comentário sem autor (ou com autor vazio) aparece como `**Comentário · <instante>**`.

### Conector interno `cards`

Igual ao conector `tickets` ([Conector interno tickets](chamados.md#conector-interno-tickets)), com o cursor `{"kind": "cards", "version": 1}` e o documento:

- `natural_key` = `external_id`, `kind = card`, `title` = título (anonimizado se for o caso), `uri = card:<external_id>`;
- `content_hash` = SHA-256 do Markdown e dos metadados de citação.

`documents.kind` e `run_items.document_kind` aceitam `card`; `runs.trigger` usa o mesmo `ingest`.

### Markdown do card

```markdown
# Card PROJ-123: Permitir nota fiscal de exportação

- Tipo: Funcionalidade (original: Story)
- Status: Concluído (original: Done)
- Prioridade: alta
- Produto: Faturamento
- Sprint: Sprint 42 (2026-09-15 a 2026-09-29)
- Versão: 12.5
- Card pai: PROJ-100
- Tags: nfe, exportação
- Criado em: 2026-09-01T12:00:00Z
- Atualizado em: 2026-09-29T18:00:00Z
- Concluído em: 2026-09-29T17:40:00Z

## Descrição

Emitir nota fiscal para cliente do exterior, sem CNPJ.

## Critérios de aceite

- A nota de exportação sai sem CNPJ quando o cliente é estrangeiro.

## Ligações

- Chamado 48213 (relaciona)
- Commit 3f9c2a1 (corrige)
- PR 482

## Comentários

**[RESPONSAVEL_1] · 2026-09-20T10:00:00Z**

Implementado no fluxo de emissão; falta o teste de rejeição.

## Campos adicionais

- equipe: fiscal

## Anexos

- layout-nfe-exportacao.png
```

Regras: só as linhas e seções com valor; status e tipo em pt-BR com `(original: …)` quando diferente (sem diferenciar maiúsculas); instantes em UTC com `Z`; corpos convertidos e títulos ATX dos corpos viram negrito, como nos chamados; comentários em ordem de `created_at` (empate pela posição), só com `include_comments`.

- **Sprint**: o nome e as datas como dias UTC (`AAAA-MM-DD`): `(início a fim)` com as duas, `(desde início)` só com o início, `(até fim)` só com o fim, e só o nome sem datas.
- **Conclusão**: `Concluído em` com `done_at`; num card `cancelled`, a linha é `Cancelado em`.
- **Ligações**: `- <Tipo> <alvo> (<relação>)`, com `Card`, `Chamado`, `Commit`, `PR` ou `Link`; a ligação `url` termina com `: <url>`. O `url` das outras ligações não é renderizado.

**Chunking**: por títulos. A lista de metadados vai com o primeiro trecho, junto com a `## Descrição` e os `## Critérios de aceite` quando cabem em `MAX_TOKENS` (o trecho fica com `section: description`); senão, cada seção é um trecho. `## Comentários` se divide por linhas com sobreposição se passar do limite. Texto embedado com o cabeçalho `card: <number ou external_id> · <title>`, `status: <status>` e `section: <seção>`. `meta` de cada trecho: `kind` (`card`), `external_id`, `card_number`, `title`, `card_type`, `card_status`, `original_status`, `sprint` (nome ou `null`), `release`, `date` (`done_at` se houver, senão `updated_at`), `date_kind` (`done` ou `updated`), `url`, `headings` e `section` (`description`, `acceptance`, `links`, `comments`, `fields` ou `attachments`).

### No chat

Só perguntas no nível `product_dev` recebem cards, pelo nível mínimo padrão da fonte; o admin pode baixá-lo ([produtos-e-niveis.md](produtos-e-niveis.md#quem-muda-e-o-que-acontece)).

- **Contexto enviado ao LLM**: o conteúdo de cada fonte de card vem precedido da linha `Card <número> · <tipo> · <status em pt-BR> · sprint <nome> · <data> · seção <Seção>` (sem a parte da sprint quando não há). A linha não entra na citação.
- **Regra fixa do prompt** ([chat.md](chat.md#regra-de-citações-regra-8-do-agentsmd)): "Em cards de desenvolvimento, diga o status e a sprint quando os citar; só afirme que algo foi entregue se o card estiver concluído ou se outra fonte mostrar a entrega".

### Citação `kind: card`

Formato no fio em [chat-sse.md](chat-sse.md#citations) (v0.9):

| Campo | Valor |
|---|---|
| `kind` | `card` |
| `title` | Título do card (anonimizado, se for o caso). |
| `uri` | `card:<external_id>`. |
| `snippet` | Até 300 caracteres do trecho, sem o cabeçalho de embedding. |
| `document_id` | Id do documento. |
| `card_number` | `number`, ou `external_id` sem ele. |
| `card_type` | `feature`, `bug`, `task`, `story`, `epic` ou `other`. |
| `card_status` | `backlog`, `in_progress`, `done` ou `cancelled`. |
| `card_sprint` | Nome da sprint, ou `null`. |
| `date` | `done_at` se houver, senão `updated_at` (ISO 8601 UTC). |
| `card_date_kind` | `done` ou `updated`. |
| `url` | Link do card na origem, ou `null`. O painel só o mostra como link se for `http` ou `https`. |
| Demais campos de localização e de chamado | `null`. |

## Referências

- [chamados.md](chamados.md), de onde vêm o envio, a caixa de entrada e a anonimização.
- JSON Schema 2020-12: <https://json-schema.org/draft/2020-12/json-schema-core>
