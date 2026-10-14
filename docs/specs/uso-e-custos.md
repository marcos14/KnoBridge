# Uso e custos, painel do workspace e painel da instância

> Rascunho v0.4 · 2026-10-14 · Planos 0008 (F1.1; implementado na F2.2), 0009 (F1.1) e 0010 (F1.1)

> **Mudanças da v0.4** (plano 0010, F1.1; implementação nas F2.2, F3.2 e F4.3): canais **`mcp`** e **`widget`**: `group_by=channel` traz sempre as quatro linhas, `group_by=api_key` conta os canais `api` e `mcp`, e há o agrupamento novo `group_by=widget` ([Canais MCP e widget](#canais-mcp-e-widget)).

> **Mudanças da v0.3** (plano 0009, F1.1; implementação nas F2.2 e F3.3): uso e custos agrupam por **produto** (`group_by=product`, no lugar de `assistant`) e por **nível** (`group_by=level`) e filtram por `product_id` e `level` ([Filtros por produto e nível](#filtros-por-produto-e-nível)); o preço de cada resposta usa o modelo do nível; o checklist ganha `levels` e troca `assistant` por `product` ([produtos-e-niveis.md](produtos-e-niveis.md)).

> **Mudanças da v0.2** (F2.2): preços conferidos no catálogo do OpenRouter, com os ids `anthropic/...` acrescentados; somas sem item com preço valem zero e o aviso vem de `unpriced_*`; `channel` lista sempre os dois canais; `InstanceHealth` com `version` no topo e os textos de `detail`.

Contrato dos números do painel: o custo estimado de cada resposta do chat, as rotas de **Uso e custos** (tokens e US$ de embeddings e de chat no período, agrupados, com CSV), o **painel do workspace** da tela Início (cartões e checklist de primeiros passos) e o **painel da instância** do superadmin (contagens, falhas recentes, uso total e saúde dos serviços). Tudo é consulta agregada sobre `runs` e `messages`, sem tabela de métricas (D7 do [plano 0008](../planos/0008-telas-de-uso-e-administracao.md)).

O custo das execuções de indexação já existe ([indexacao.md](indexacao.md#custo-registrado)); o custo e o canal por resposta do chat estão em [chat.md](chat.md#custo-e-canal-por-resposta); as tabelas, em [modelo-de-dados.md](modelo-de-dados.md).

Código previsto: `backend/src/knobridge/llm/chat_pricing.py` (preços), `backend/src/knobridge/usage/` (agregações e painéis), `api/usage.py`, `api/dashboard.py` e `api/admin_dashboard.py`. Telas: `frontend/src/features/usage/`, `app/HomePage.tsx` e `features/admin`.

## Convenções

- **Valores em US$ são estimativas**, calculadas pelo KnoBridge com tabelas de preço, não a fatura do provedor. Na API, número com até 6 casas (`float`, como `runs.cost_usd` hoje); no CSV, texto com ponto decimal e 6 casas.
- **Preço desconhecido nunca vira zero.** Execução ou resposta com modelo sem preço tem `cost_usd` nulo; os totais somam só os valores conhecidos e informam quantos itens ficaram sem preço (`unpriced_runs`, `unpriced_answers`) e seus tokens, para a tela avisar "custo parcial".
- **Período semiaberto `[from, to)`**, em UTC, com datas ISO 8601 (`2026-10-01T00:00:00Z`). Sem `from`, os 30 dias antes de `to`; sem `to`, o relógio do servidor (injetado). `from >= to` dá 422 `validation_error`; período maior que 366 dias dá 422 `usage_period_too_long`.
- **Em que data cada custo cai**: embeddings, pelo `runs.finished_at` (o custo só é calculado ao fechar a execução; execuções ainda abertas não entram); chat, pelo `created_at` da mensagem do assistente.
- **Quem conta como resposta do chat**: mensagens `role = assistant` com `model` preenchido (as que chamaram o LLM: `completed`, `failed`, `interrupted`). `no_source` não chama o LLM e não tem custo; entra só na contagem de respostas do painel.
- **Isolamento**: rotas de workspace filtram por `workspace_id` e rodam no escopo do workspace (RLS); rotas da instância rodam em modo de sistema, só para superadmin. Toda consulta nova tem teste de isolamento e de número constante de statements.

## Preços do chat

`ChatPriceTable` (`llm/chat_pricing.py`), no mesmo modelo da `EmbeddingPriceTable` (`llm/pricing.py`): USD por milhão de tokens, separado em entrada e saída, chave = identificador do modelo como a configuração do nível grava (`workspace_levels.model`; até a v0.2, `assistants.model`), o mesmo que fica em `messages.model`. O custo de uma resposta é `(input_tokens × entrada + output_tokens × saída) / 1 000 000`, arredondado a 6 casas (`ROUND_HALF_UP`). Faltando o preço do modelo, `input_tokens` ou `output_tokens`, o custo é `null`.

Preços padrão (USD por 1M tokens):

| Modelo | Entrada | Saída |
|---|---|---|
| `claude-opus-5-5` e `anthropic/claude-opus-5.5` | 4,00 | 20,00 |
| `claude-opus-5` e `anthropic/claude-opus-5` | 5,00 | 25,00 |
| `claude-sonnet-5-5` e `anthropic/claude-sonnet-5.5` | 2,00 | 10,00 |
| `claude-sonnet-5` e `anthropic/claude-sonnet-5` | 2,00 | 10,00 |
| `claude-haiku-4-5` e `anthropic/claude-haiku-4.5` | 1,00 | 5,00 |
| `gpt-4.1` e `openai/gpt-4.1` | 2,00 | 8,00 |
| `gpt-4.1-mini` e `openai/gpt-4.1-mini` | 0,40 | 1,60 |
| `gpt-4.1-nano` e `openai/gpt-4.1-nano` | 0,10 | 0,40 |
| `gpt-4o` e `openai/gpt-4o` | 2,50 | 10,00 |
| `gpt-4o-mini` e `openai/gpt-4o-mini` | 0,15 | 0,60 |

Fonte: catálogo público do OpenRouter (`GET https://openrouter.ai/api/v1/models`, `pricing.prompt` e `pricing.completion` × 1 000 000), consultado em 2026-10-12 e registrado no comentário do código; os ids diretos de cada provedor usam o preço do mesmo modelo lá. O provedor `fake` não tem preço (custo `null`).

**`KNOBRIDGE_CHAT_PRICES`** sobrescreve ou acrescenta preços, em JSON, no mesmo espírito de `KNOBRIDGE_EMBEDDING_PRICES` (mapa modelo → preço), com os dois preços por modelo:

```sh
KNOBRIDGE_CHAT_PRICES='{"gpt-4.1-mini": {"input": 0.40, "output": 1.60}, "anthropic/claude-sonnet-5.5": {"input": 2, "output": 10}}'
```

Valores ≥ 0; JSON inválido, campo faltando ou negativo impede a subida (erro de settings). Entra em `.env.example`.

Mudar a tabela não recalcula o passado: o custo é gravado na resposta (`messages.cost_usd`), como o das execuções.

## Uso e custos do workspace

Owner e admin (403 `forbidden` para os demais). Tela **Uso e custos** do painel.

### `GET .../usage`

Parâmetros: `from`, `to` (período), `group_by` (obrigatório, abaixo) e, desde a v0.3, `product_id` e `level` (opcionais, [abaixo](#filtros-por-produto-e-nível)). Resposta 200 `UsageReport`:

```json
{
  "period_start": "2026-09-12T00:00:00Z",
  "period_end": "2026-10-12T00:00:00Z",
  "group_by": "product",
  "totals": {
    "embedding_tokens": 1250000, "embedding_cost_usd": 0.025, "runs": 14, "unpriced_runs": 0,
    "chat_input_tokens": 98000, "chat_output_tokens": 12000, "chat_cost_usd": 0.0584,
    "answers": 120, "unpriced_answers": 3,
    "cost_usd": 0.0834
  },
  "rows": [
    {
      "key": "6f1c…", "label": "ERP",
      "embedding_tokens": null, "embedding_cost_usd": null, "runs": null, "unpriced_runs": null,
      "chat_input_tokens": 98000, "chat_output_tokens": 12000, "chat_cost_usd": 0.0584,
      "answers": 120, "unpriced_answers": 3,
      "cost_usd": 0.0584
    }
  ]
}
```

| `group_by` | Linhas | `key` / `label` | Colunas preenchidas |
|---|---|---|---|
| `source` | Uma por fonte com execução encerrada no período | id / nome da fonte | embeddings |
| `collection` | Uma por coleção (pela fonte da execução) | id / nome da coleção | embeddings |
| `product` | Uma por produto com resposta no período (v0.3; no lugar de `assistant`, que passa a dar 422) | id / nome do produto | chat |
| `level` | `end_user`, `support` e `product_dev`, sempre as três, na ordem dos níveis (v0.3) | nível / o mesmo nome (o painel traduz) | chat |
| `channel` | `panel`, `api`, `mcp` e `widget` (v0.4; até a v0.3, só os dois primeiros) | canal / "Painel", "API", "MCP" ou "Widget" (o painel traduz) | chat |
| `api_key` | Uma por chave com resposta no período (canais `api` e `mcp`, v0.4) | id / nome da chave | chat |
| `widget` | Uma por widget com resposta no período (canal `widget`, v0.4) | id / nome do widget | chat |
| `model` | Uma por modelo (de embedding ou de chat) | modelo / modelo | as do tipo do modelo |
| `day` | Um dia UTC por linha, do primeiro ao último do período, inclusive dias vazios (com zeros) | `2026-10-01` / a mesma data | todas |

- Colunas que não se aplicam ao agrupamento vêm `null` (não zero). `cost_usd` da linha é a soma dos custos conhecidos que se aplicam; sem nenhum custo conhecido, a soma é `0` e `unpriced_runs`/`unpriced_answers` dizem quantos itens ficaram de fora. `totals` é sempre do período inteiro, com todas as colunas.
- `channel` traz sempre as quatro linhas (`panel`, `api`, `mcp` e `widget`, nessa ordem quando os custos empatam) e `level` sempre as três, com zeros quando não houve resposta; em `model`, um modelo usado nos dois papéis vem numa linha só, com os dois lados.
- Linhas ordenadas por `cost_usd` decrescente (nulos por último) e depois por `label`; em `day`, pela data; em `level`, pela ordem dos níveis. Sem paginação: o número de linhas é limitado pelo agrupamento (fontes, produtos, chaves, níveis) ou pelo período (até 367 dias).
- Fonte, coleção, produto ou chave excluídos: as execuções e conversas vão junto (cascata), então somem do relatório. Produto renomeado aparece com o nome atual. As respostas de antes da migração `0018` contam no produto que veio do assistente (mesmo id) e no nível `product_dev`.
- Número constante de statements: um para os totais e um para as linhas.

### Canais MCP e widget

Desde a v0.4 ([ADR 0009](../adr/0009-canais-mcp-e-widget.md)):

- As respostas da ferramenta `ask` do MCP ([mcp.md](mcp.md#ask)) têm `messages.channel = mcp`; as do widget ([widget.md](widget.md)), `widget`. Contam no chat como as demais (respostas com `model` preenchido), com custo pelo modelo do nível.
- `group_by=api_key` soma as respostas da chave nos canais `api` e `mcp` (pela `conversations.api_key_id`); para separar, use `group_by=channel`.
- `group_by=widget`: uma linha por widget (pela `conversations.widget_id`), com o nome atual. Widget excluído leva as conversas junto (cascata) e some do relatório.
- `search_knowledge` e `get_document` do MCP não chamam o LLM e não entram; o embedding das consultas delas não é registrado (como o "testar busca").
- Os filtros `product_id` e `level` valem para os canais novos. No widget, o nível é sempre `end_user`.
- O CSV aceita `group_by=widget`. O painel traduz os canais e mostra o agrupamento **Widget**.

### Filtros por produto e nível

Desde a v0.3, `product_id` (um produto do workspace; outro id dá linhas vazias, sem erro) e `level` (`end_user`, `support` ou `product_dev`; outro valor: 422) restringem **as respostas do chat** a esse produto e/ou nível, pelos campos `messages.product_id` e `messages.level`, sem junção.

- Embeddings não pertencem a um produto nem a um nível (uma coleção serve vários produtos e todos os níveis). Com algum desses filtros, as colunas de embeddings vêm `null` em `totals` e nas linhas, e `cost_usd` soma só o chat.
- Com `group_by` = `source` ou `collection`, que só têm embeddings, os filtros dão 422 `validation_error`.
- O CSV aceita os mesmos filtros e acrescenta ao nome do arquivo `-<nível>` quando há `level` (o produto não entra no nome).

### `GET .../usage.csv`

Mesmos parâmetros. Resposta 200 `text/csv; charset=utf-8`, com `Content-Disposition: attachment; filename="knobridge-uso-<group_by>-<from>-<to>.csv"` (datas `AAAA-MM-DD`), separador vírgula, cabeçalho na primeira linha, uma linha por `rows` e uma última linha `total`:

```text
key,label,embedding_tokens,embedding_cost_usd,runs,unpriced_runs,chat_input_tokens,chat_output_tokens,chat_cost_usd,answers,unpriced_answers,cost_usd
6f1c…,Suporte ERP,,,,,98000,12000,0.058400,120,3,0.058400
total,Total,1250000,0.025000,14,0,98000,12000,0.058400,120,3,0.083400
```

Campos nulos ficam vazios. Texto com vírgula, aspas ou quebra de linha vai entre aspas (RFC 4180). Valores que começam com `=`, `+`, `-` ou `@` ganham um `'` antes, contra injeção de fórmula em planilha. Sem BOM.

## Painel do workspace (Início)

### `GET .../dashboard`

Qualquer membro (viewer ou acima). Resposta 200 `WorkspaceDashboard`:

| Campo | Conteúdo |
|---|---|
| `month_start` | Primeiro instante do mês corrente (UTC), pelo relógio do servidor. |
| `documents` | Documentos indexados no workspace. |
| `sources` | `{total, active}`. |
| `failed_runs` | Execuções `failed` com `finished_at` nos últimos 7 dias. |
| `conversations_month` | Conversas criadas no mês (todos os canais). |
| `feedback_month` | `{up, down}` das respostas criadas no mês. |
| `cost_month` | Só para owner e admin (`null` para os demais): `{embedding_cost_usd, chat_cost_usd, cost_usd, partial}`, com `partial = true` quando houve item sem preço. |
| `checklist` | Lista abaixo. |

Número constante de statements (um para os cartões, um para o checklist).

### Checklist de primeiros passos

Itens na ordem do fluxo, cada um `{"key", "done"}`. O painel mostra os pendentes, com o link da tela; esconde os feitos; e esconde a lista inteira quando todos estão feitos. O link só aparece para quem tem o papel mínimo da tela ([autenticacao.md](autenticacao.md#telas-do-painel)); para os outros, o item diz que é preciso pedir a um administrador.

| `key` | Feito quando | Tela | Papel da tela |
|---|---|---|---|
| `provider` | Existe ao menos uma credencial de provedor. | Provedores | editor |
| `collection` | Existe ao menos uma coleção. | Coleções | editor |
| `source` | Existe ao menos uma fonte com uma execução `succeeded`. | Fontes | editor |
| `levels` | O nível `end_user` tem credencial e modelo no workspace (v0.3). | Configurações > Níveis de resposta | admin |
| `product` | Existe ao menos um produto ativo ligado a uma coleção (v0.3; até a v0.2, `assistant`). | Produtos | editor |
| `chat` | Existe ao menos uma resposta `completed` com citação no workspace. | Chat | viewer |

## Painel da instância (Administração)

Superadmin (403 `forbidden` para os demais), em modo de sistema.

### `GET /v1/admin/dashboard`

Parâmetros: `from`, `to` (período do uso; mesmas regras de cima). Resposta 200 `InstanceDashboard`:

| Campo | Conteúdo |
|---|---|
| `workspaces` | `{total, active, suspended}`. |
| `users` | `{total, suspended, superadmins, active_30d}`; `active_30d` = usuários não suspensos com sessão vista (`sessions.last_seen_at`) nos últimos 30 dias. |
| `failed_runs_7d` | Execuções `failed` nos últimos 7 dias, na instância. |
| `failed_answers_7d` | Respostas do chat `failed` nos últimos 7 dias. |
| `recent_failures` | As 10 execuções `failed` mais recentes: `{run_id, workspace_id, workspace_name, source_id, source_name, error, finished_at}` (`error` é o `runs.error`, já sem conteúdo). |
| `usage` | Totais do período no formato de `totals` acima, somando todos os workspaces, e `by_workspace`: até 10 workspaces de maior custo, `{workspace_id, workspace_name, cost_usd, embedding_tokens, chat_input_tokens, chat_output_tokens}`. |

### `GET /v1/admin/health`

Separado do painel para a tela carregar os números sem esperar as checagens. Resposta 200 `InstanceHealth` (sempre 200; o estado vai no corpo):

| Serviço | Checagem | Estados |
|---|---|---|
| `api` | A própria resposta; traz a `version`. | `ok` |
| `database` | `SELECT 1` (o mesmo `ping` de `/v1/health/ready`). | `ok`, `error` |
| `temporal` | Descrição do namespace pelo cliente Temporal. | `ok`, `error` |
| `worker` | Descrição da fila de tarefas do worker (`DescribeTaskQueue`): `ok` se algum poller foi visto nos últimos 60 s, `error` se não há poller recente, `unknown` se o Temporal está fora. | `ok`, `error`, `unknown` |

Corpo: `{"version", "api", "database", "temporal", "worker"}`. Cada item: `{"status", "checked_at", "detail"}`, com `detail` curto e nosso, nunca a mensagem do driver: `null` em `ok`; `database unreachable`, `temporal unreachable`, `task queue unreadable`, `no worker polling the task queue`, `check timed out` em `error`; `temporal down` no worker `unknown`. As checagens rodam em paralelo, cada uma com timeout de 2 s (timeout = `error`). Falhas são logadas só pelo tipo da exceção.

## Papéis e auditoria

| Rota | Quem |
|---|---|
| `GET .../usage`, `GET .../usage.csv` | admin |
| `GET .../dashboard` | viewer (`cost_month` só para admin) |
| `GET /v1/admin/dashboard`, `GET /v1/admin/health` | superadmin |

`...` = `/v1/workspaces/{workspace_id}`. São leituras: nada é auditado.

## Referências

- Anthropic, modelos e preços: <https://docs.claude.com/en/docs/about-claude/models/overview>
- OpenAI, preços: <https://openai.com/api/pricing/>
- RFC 4180 (CSV): <https://www.rfc-editor.org/rfc/rfc4180>
- OWASP, CSV Injection: <https://owasp.org/www-community/attacks/CSV_Injection>
- Temporal, filas de tarefas e pollers: <https://docs.temporal.io/task-queue>
