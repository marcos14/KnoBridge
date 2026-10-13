# Receber cards por API: da ferramenta de desenvolvimento às respostas citando cards

> Rascunho v0.1 · 2026-10-13 · Em uso (plano 0009)

Passo a passo para integrar uma ferramenta de cards de desenvolvimento (Jira, Azure DevOps, GitHub Issues, Trello ou uma ferramenta própria) ao KnoBridge, para que a equipe de desenvolvimento e produto pergunte se um problema ou pedido já foi tratado, em que status e em que sprint.

Os cards seguem **o mesmo caminho dos chamados**: o KnoBridge não busca nada na ferramenta; quem integra **empurra** os cards num formato único, por API com token ou por upload de arquivo, com a mesma caixa de entrada, a mesma idempotência e a mesma anonimização. Este guia mostra só o que muda; o resto está em [receber-chamados-por-api.md](receber-chamados-por-api.md), lendo "card" onde lá está "chamado". Contrato completo em [cards.md](../specs/cards.md).

## Pré-requisitos

- Um servidor do KnoBridge no ar ([subir-ambiente.md](subir-ambiente.md)) e um workspace onde você é **owner ou admin** (para gerar o token de envio). Editores criam a fonte, fazem upload e usam a prévia.
- Uma coleção com credencial de embedding e um produto, com os níveis de resposta configurados ([indexar-uma-fonte.md](indexar-uma-fonte.md); [produtos-e-niveis.md](produtos-e-niveis.md)).
- Do lado da ferramenta: um lugar para rodar a conversão (script agendado, automação da própria ferramenta, n8n ou outro iPaaS) com acesso HTTPS de saída até o KnoBridge.

## Passos

### 1. Criar a fonte de cards

1. Vá em **Fontes > Nova fonte**, escolha **Cards de desenvolvimento**, dê um nome (ex.: `jira-erp`) e escolha a coleção.
2. Decida a configuração (vale para os cards processados depois de cada mudança):
   - **Anonimizar** (ligado por padrão): cards costumam copiar trechos de chamados com dados de clientes. Troca e-mails, telefones, CPF, CNPJ, cartões, IPs e os nomes de relator, responsáveis e autores de comentários por marcadores (`[RELATOR]`, `[RESPONSAVEL_1]`…). Desligue só se a ferramenta não guarda dado pessoal.
   - **Incluir comentários** (ligado por padrão).
   - **Status indexados**: por padrão os quatro (`backlog`, `in_progress`, `done`, `cancelled`).
   - **Nível mínimo**: **Desenvolvimento e produto** por padrão. Só as perguntas nesse nível recebem cards; um owner ou admin pode baixar ([produtos-e-niveis.md](produtos-e-niveis.md#4-ajustar-o-nível-mínimo-das-fontes)).
3. Salve. A fonte abre com as abas **Integração**, **Upload**, **Prévia** e **Indexação**.

### 2. Gerar o token de envio

Na aba **Integração**, clique em **Gerar token**, confirme e copie o `kbi_...`, que aparece **uma única vez**. Guarde-o como segredo da integração, por exemplo em `KNOBRIDGE_INGEST_TOKEN`. O token só abre `POST /v1/ingest/cards` desta fonte: usado em `/v1/ingest/tickets` (ou o token de uma fonte de chamados aqui), a resposta é 409 `source_kind_mismatch` e nada é gravado.

### 3. Converter os cards para o formato do KnoBridge

O schema completo está em [cards.md, Formato do card](../specs/cards.md#formato-do-card-cardin). O essencial:

| Campo | Obrigatório | O que pôr |
|---|---|---|
| `external_id` | sim | O id estável do card na ferramenta. O mesmo id atualiza o mesmo card. |
| `title` | sim | Título. |
| `type` | sim | `feature`, `bug`, `task`, `story`, `epic` ou `other`; o nome original vai em `original_type`. |
| `status` | sim | `backlog`, `in_progress`, `done` ou `cancelled`; o nome original vai em `original_status`. |
| `created_at`, `updated_at` | sim | Instantes RFC 3339 **com fuso**. `updated_at` decide qual versão vale. |
| `number`, `url` | não | Número que a equipe reconhece (`PROJ-123`) e link do card. Aparecem na citação. |
| `description`, `acceptance_criteria` | não | `{body, body_format}` com `text`, `markdown` ou `html`. |
| `sprint`, `release`, `done_at` | não | Sprint (`{name, start_at, end_at}`), versão e quando foi concluído. A resposta diz o status e a sprint de cada card citado. |
| `links` | não | Ligações com chamados, commits, PRs, outros cards ou URLs. |
| `comments` | não | `author_name`, `body` e `created_at`. |
| `reporter`, `assignees` | não | Nunca aparecem no índice: servem para a anonimização saber quais nomes trocar. |

Mapeie os status da ferramenta para os quatro do KnoBridge: "a fazer" e "novo" são `backlog`; desenvolvimento, revisão e teste são `in_progress`; entregue é `done`; descartado é `cancelled`. A resposta só afirma que algo foi entregue com um card `done` ou outra fonte que mostre a entrega.

### 4. Enviar pela API

`POST /v1/ingest/cards` recebe de 1 a 100 itens, com `card` no lugar de `ticket`:

```sh
curl -X POST "https://knobridge.exemplo.com.br/v1/ingest/cards" \
  -H "Authorization: Bearer $KNOBRIDGE_INGEST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      { "op": "upsert", "card": { "external_id": "10482", "number": "PROJ-123",
        "title": "Permitir nota fiscal de exportação", "type": "feature", "status": "done",
        "original_status": "Done", "sprint": { "name": "Sprint 42" }, "release": "12.5",
        "url": "https://jira.exemplo.com.br/browse/PROJ-123",
        "description": { "body": "Emitir nota fiscal para cliente do exterior, sem CNPJ." },
        "created_at": "2026-09-01T09:00:00-03:00", "updated_at": "2026-09-29T15:00:00-03:00",
        "done_at": "2026-09-29T14:40:00-03:00" } },
      { "op": "delete", "external_id": "10399", "deleted_at": "2026-10-02T08:00:00Z" }
    ]
  }'
```

A resposta é **202** com um resultado por item (`queued`, `unchanged`, `stale` ou `rejected`), as contagens e o disparo da sincronização, exatamente como nos chamados ([receber-chamados-por-api.md, passo 4](receber-chamados-por-api.md#4-enviar-pela-api)). Reenviar é seguro; o exemplo em Python e o fluxo do n8n de lá servem trocando a URL e a chave `ticket` por `card`. A aba **Integração** mostra os exemplos de `curl` e Python já com a URL do seu servidor.

### 5. Carga histórica por upload e prévia

- **Upload**: exporte os cards em `.jsonl` (um por linha) ou `.json` (lista ou `{"items": [...]}`), com itens da API ou cards puros, até 50 MiB, e envie pela aba **Upload**. O relatório mostra os recusados por linha.
- **Prévia**: cole um card na aba **Prévia** e veja o Markdown que vai para o índice, com a anonimização e os comentários desta fonte. Nada é gravado.

### 6. Ligar a coleção ao produto e conversar

1. Ligue a coleção da fonte ao produto (**Produtos > Editar > Coleções**).
2. No **Chat**, escolha o produto e o nível **Desenvolvimento e produto** (o seu nível máximo no produto precisa chegar lá: padrão de owner e admin).
3. Pergunte, por exemplo, "A nota fiscal de exportação já foi feita?". A citação do card mostra o título, `Card <número>` e o status (Backlog, Em andamento, Concluído ou Cancelado); ao abri-la, o painel traz o tipo, a sprint, a data e o link **Abrir o card no sistema de origem** quando você envia `url`.

Nos níveis Usuário final e Suporte, a mesma pergunta não recebe o card: o filtro é feito na busca, antes do LLM.

## Como verificar

- A aba **Integração** mostra o prefixo do token atual, os cards por estado (aguardando processamento, indexados, fora dos status indexados, remoções aguardando, removidos) e o último recebimento.
- A aba **Indexação** mostra as execuções disparadas pelos envios.
- No chat, em **Desenvolvimento e produto**, uma pergunta sobre um card traz a citação com número e status; em **Usuário final**, não.

## Como desfazer

- **Parar de receber**: gere um novo token e não o entregue a ninguém, ou desative a fonte (os envios voltam 409 `source_inactive`).
- **Tirar cards do índice**: envie `delete` para cada `external_id`, ou exclua a fonte.

## Limites

Os dos chamados ([receber-chamados-por-api.md, Limites](receber-chamados-por-api.md#limites)), com um card de até 1 MiB de JSON, 500 comentários, 100 ligações, 100 anexos (só os nomes), 20 responsáveis e 50 tags. A fonte de cards não é reindexada: depois de indexado, o JSON bruto é apagado; para reprocessar, reenvie com `updated_at` mais novo.

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| 409 `source_kind_mismatch` | O token é de uma fonte de chamados (ou o envio foi para `/v1/ingest/tickets`). Use o token da fonte de cards em `/v1/ingest/cards`. |
| Item `rejected` com `sprint_end_before_start` | `sprint.end_at` anterior a `sprint.start_at`. |
| Item `rejected` com `link_url_required` | Ligação `kind: url` sem `url`. |
| Item `rejected` com `invalid_sha` | Ligação `kind: commit` com um alvo que não é um SHA de 7 a 64 hexadecimais. |
| O card não aparece no chat | Confira se ele foi indexado (aba **Integração**), se o status está entre os indexados, se a coleção está ligada ao produto e se a pergunta está no nível **Desenvolvimento e produto** (ou no nível mínimo que o admin escolheu para a fonte). |
| Os demais erros (401, 413, 422, `stale`, `sync: deferred`) | Iguais aos dos chamados: [receber-chamados-por-api.md, Problemas comuns](receber-chamados-por-api.md#problemas-comuns). |

## Referências

- Contrato: [cards.md](../specs/cards.md); envio, caixa de entrada e anonimização: [chamados.md](../specs/chamados.md); níveis: [produtos-e-niveis.md](../specs/produtos-e-niveis.md).
- Decisões de arquitetura: [ADR 0006](../adr/0006-chamados-por-push.md) e [ADR 0008](../adr/0008-produtos-e-niveis.md).
