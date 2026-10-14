# Usar a API: produtos no seu sistema

> Rascunho v0.2 · 2026-10-13 · Em uso (planos 0008 e 0009)
>
> **Mudanças da v0.2** (plano 0009, F4.1): os assistentes viram **produtos** e cada pergunta tem um **nível de resposta**. A chave ganha escopo por produto e **nível máximo** (o painel pré-seleciona Usuário final); a REST recebe `product_id` e `level`; na API compatível com OpenAI, `model` é `produto` ou `produto:nível`; nível acima do máximo da chave dá 403 `level_not_allowed`. Quem usava o nome ou o id do assistente continua funcionando ([Integrações anteriores](#integrações-anteriores-à-v02)).

Passo a passo para chamar os produtos de um sistema externo (portal, ERP, bot, script) com uma chave de API: pela API REST de conversa do KnoBridge ou pela API compatível com OpenAI, com o SDK oficial da OpenAI em Python ou JavaScript. As respostas seguem as mesmas regras do chat do painel: citam as fontes e, sem fonte, dizem que não sabem (regra 8).

Contrato completo (formatos, erros, limites) em [api-publica.md](../specs/api-publica.md); decisões de arquitetura no [ADR 0007](../adr/0007-chaves-e-api-publica.md) e no [ADR 0008](../adr/0008-produtos-e-niveis.md) (produtos e níveis, com o passo a passo em [produtos-e-niveis.md](produtos-e-niveis.md)). Custos em [uso-e-custos.md](../specs/uso-e-custos.md).

A mesma chave conecta assistentes de código (Claude Code, Cursor, Codex) pelo servidor MCP: [conectar-pelo-mcp.md](conectar-pelo-mcp.md). Para pôr o chat num site ou sistema sem chave no navegador, use o widget: [embutir-o-widget.md](embutir-o-widget.md).

## Pré-requisitos

- A stack rodando ([subir-ambiente.md](subir-ambiente.md)) e um produto **ativo** que responda com fontes no chat do painel, com os níveis de resposta configurados ([produtos-e-niveis.md](produtos-e-niveis.md), [indexar-uma-fonte.md](indexar-uma-fonte.md)). Em desenvolvimento, o provedor `fake` serve: ele responde `Fake reply to: <pergunta>`, mas as citações são reais.
- Papel **owner** ou **admin** no workspace (ou o superadmin que entrou nele pela administração), para criar a chave.
- A URL da instância. Nos exemplos, `http://localhost:5173`, o painel do compose: o nginx dele encaminha `/v1` para a API. Em produção, use o endereço do painel com HTTPS.
- Para os exemplos com SDK: Python com `pip install openai`, ou Node.js 22+ com `npm install openai`.

## Passos

### 1. Criar a chave no painel

1. No workspace, vá em **Chaves de API** e clique em **Nova chave**.
2. Em **Nome**, identifique quem vai usar a chave (ex.: `Portal do cliente`). O nome é único no workspace.
3. Em **Produtos**, escolha o escopo:
   - **Todos os produtos ativos, inclusive os criados depois** (padrão);
   - **Só os produtos escolhidos**: marque um ou mais.
4. Em **Nível máximo**, escolha até que nível a chave pergunta, em qualquer produto do escopo: **Usuário final** (pré-selecionado; nunca código nem SQL), **Suporte** ou **Desenvolvimento e produto**. Sem nível na requisição, vale este. Para um portal de clientes, mantenha Usuário final; suba só para integrações internas.
5. Clique em **Salvar**. A chave aparece **uma única vez**, no formato `kbk_<prefixo>_<segredo>`. Clique em **Copiar chave** e guarde-a num cofre ou numa variável de ambiente; depois, **Concluído**.

A lista mostra o nome, o escopo, o **Nível máximo**, quem criou, o **Último uso** e o estado. **Editar** muda o nome, o escopo e o nível máximo, que valem na próxima requisição (inclusive em conversas já abertas num nível acima, que passam a recusar perguntas). Do segredo, só fica o prefixo: perdeu a chave, crie outra e revogue a antiga. Abaixo da lista, **Como usar** traz os exemplos desta página já com a URL da instância, o nome de um produto e o nível escolhido em **Nível dos exemplos**.

Nos exemplos, a chave vem da variável `KNOBRIDGE_API_KEY`. Nunca a escreva no código nem a commite:

```bash
export KNOBRIDGE_API_KEY=kbk_...      # PowerShell: $env:KNOBRIDGE_API_KEY = "kbk_..."
export KNOBRIDGE_URL=http://localhost:5173
```

Toda requisição leva o header `Authorization: Bearer $KNOBRIDGE_API_KEY`. A chave só abre a API pública: não entra no painel, e o cookie do painel não abre a API.

### 2. Descobrir o produto e os níveis

A API REST identifica o produto pelo **id** e recebe o nível no campo `level`. A compatível com OpenAI recebe os dois no campo `model`: `<produto>` ou `<produto>:<nível>`, onde `<produto>` é o **nome exato** (diferencia maiúsculas) ou o id, e `<nível>` é `end_user`, `support` ou `product_dev`. Sem nível, vale o nível máximo da chave. A lista de modelos mostra, para cada produto que a chave alcança, o produto sozinho e uma entrada por nível até o máximo dela:

```bash
curl -s $KNOBRIDGE_URL/v1/models -H "Authorization: Bearer $KNOBRIDGE_API_KEY"
```

Com uma chave de nível máximo Suporte e o produto `ERP`:

```json
{"object": "list", "data": [
  {"id": "ERP", "object": "model", "created": 1791857979, "owned_by": "knobridge", "knobridge": {"product_id": "abc381c7-…", "level": "support", "level_explicit": false, "description": ""}},
  {"id": "ERP:end_user", "object": "model", "created": 1791857979, "owned_by": "knobridge", "knobridge": {"product_id": "abc381c7-…", "level": "end_user", "level_explicit": true, "description": ""}},
  {"id": "ERP:support", "object": "model", "created": 1791857979, "owned_by": "knobridge", "knobridge": {"product_id": "abc381c7-…", "level": "support", "level_explicit": true, "description": ""}}
]}
```

Renomear o produto quebra quem usa o nome; o id é estável. O nível decide as fontes (só trechos com nível mínimo igual ou abaixo), as instruções e o modelo da resposta ([produtos-e-niveis.md](produtos-e-niveis.md#os-três-níveis)).

### 3. API REST: conversa com histórico no KnoBridge

Use a REST quando quiser que o KnoBridge guarde a conversa: cada pergunta vê as 10 mensagens anteriores dela.

**Criar a conversa:**

```bash
curl -s $KNOBRIDGE_URL/v1/conversations \
  -H "Authorization: Bearer $KNOBRIDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"product_id": "abc381c7-…", "level": "end_user"}'
```

A resposta (201) traz o `id` da conversa, com `product_id`, `level` e `"channel": "api"`. `level` é opcional: sem ele, vale o nível máximo da chave. O nível fica fixo na conversa; para outro nível, crie outra conversa. Nível acima do máximo da chave dá 403 `level_not_allowed`.

**Perguntar, com a resposta inteira em JSON** (`stream: false`, o padrão):

```bash
curl -s $KNOBRIDGE_URL/v1/conversations/<id>/messages \
  -H "Authorization: Bearer $KNOBRIDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"content": "Como registrar a sangria do caixa?", "stream": false}'
```

```json
{
  "user_message_id": "…",
  "message": {
    "id": "…", "role": "assistant", "status": "completed",
    "content": "Abra o menu Caixa e escolha Sangria… [1]",
    "citations": [{"index": 1, "title": "fechamento-de-caixa.md", "uri": "fechamento-de-caixa.md#L5-L9", "kind": "file", "snippet": "…", "start_line": 5, "end_line": 9, "…": "…"}],
    "model": "gpt-4.1-mini", "input_tokens": 812, "output_tokens": 64, "cost_usd": 0.000427, "channel": "api"
  }
}
```

Os marcadores `[1]`, `[2]`… do texto apontam para `citations[].index`. `status` é `completed`, `no_source` (sem fonte: `citations` vazio e o texto é a mensagem de "sem fonte" do produto) ou `failed` (o provedor falhou no meio; o HTTP continua 200, com `error_code` e o texto parcial).

**Perguntar com streaming** (`stream: true`): a resposta é SSE, com os mesmos eventos do chat do painel ([chat-sse.md](../specs/chat-sse.md)): `citations` primeiro, um `delta` por pedaço do texto e `done` (ou `error`) no fim.

```bash
curl -sN $KNOBRIDGE_URL/v1/conversations/<id>/messages \
  -H "Authorization: Bearer $KNOBRIDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"content": "E o fechamento do caixa?", "stream": true}'
```

```text
event: citations
data: {"message_id": "…", "user_message_id": "…", "citations": [{"index": 1, "title": "fechamento-de-caixa.md", …}]}

event: delta
data: {"text": "Para fechar "}

event: done
data: {"message_id": "…", "status": "completed", "model": "gpt-4.1-mini", "input_tokens": 253, "output_tokens": 8, "cost_usd": 0.000114, …}
```

**Ler a conversa** (mensagens paginadas, na ordem; `messages_limit` até 200, `messages_offset`):

```bash
curl -s "$KNOBRIDGE_URL/v1/conversations/<id>?messages_limit=50" \
  -H "Authorization: Bearer $KNOBRIDGE_API_KEY"
```

A conversa é da chave que a criou: outra chave, mesmo do mesmo workspace, recebe 404. Listar e excluir conversas, avaliar respostas e abrir chamado pela API ainda não existem.

### 4. API compatível com OpenAI

Use esta quando o seu sistema já fala Chat Completions (SDKs oficiais, clientes de chat, ferramentas de automação). Aponte o `base_url` para `<instância>/v1`, use a chave como `api_key` e o produto (com ou sem nível) como `model`. Cada chamada cria uma conversa nova no KnoBridge com a pergunta e a resposta; o histórico que você manda em `messages` serve de contexto, mas não é gravado. Mensagens `system` e `developer` são ignoradas: quem manda são as instruções do nível e o texto do produto.

**curl:**

```bash
curl -s $KNOBRIDGE_URL/v1/chat/completions \
  -H "Authorization: Bearer $KNOBRIDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "ERP:end_user", "messages": [{"role": "user", "content": "Como registrar a sangria do caixa?"}]}'
```

```json
{
  "id": "chatcmpl-…", "object": "chat.completion", "model": "ERP:end_user",
  "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Abra o menu Caixa… [1]\n\nFontes:\n[1] fechamento-de-caixa.md (fechamento-de-caixa.md#L5-L9)", "refusal": null}}],
  "usage": {"prompt_tokens": 226, "completion_tokens": 9, "total_tokens": 235},
  "knobridge": {"conversation_id": "…", "message_id": "…", "status": "completed", "citations": [{"index": 1, "title": "fechamento-de-caixa.md", "uri": "fechamento-de-caixa.md#L5-L9", "…": "…"}], "cost_usd": 0.000427}
}
```

As citações vêm em dois lugares:

- **no texto**: o rodapé `Fontes:` com uma linha `[n] título (uri)` por citação, para clientes que só mostram o conteúdo;
- **no campo extra `knobridge`**: `citations` (a mesma lista da REST), `status` (`completed` ou `no_source`), `conversation_id`, `message_id` e `cost_usd`.

Para receber só o texto do modelo, sem o rodapé, mande `"knobridge": {"append_sources": false}` no corpo. A resposta gravada no KnoBridge nunca tem o rodapé.

**Python (SDK oficial):**

```python
import os

from openai import OpenAI

client = OpenAI(
    base_url=os.environ["KNOBRIDGE_URL"] + "/v1",
    api_key=os.environ["KNOBRIDGE_API_KEY"],
    max_retries=0,  # cada repetição viraria uma conversa nova
)

answer = client.chat.completions.create(
    model="ERP:end_user",
    messages=[{"role": "user", "content": "Como registrar a sangria do caixa?"}],
)
print(answer.choices[0].message.content)
for citation in answer.model_extra["knobridge"]["citations"]:
    print(citation["index"], citation["title"], citation["uri"])

# Streaming, sem o rodapé de fontes (campo extra vai em extra_body).
stream = client.chat.completions.create(
    model="ERP:end_user",
    messages=[{"role": "user", "content": "Como registrar a sangria do caixa?"}],
    stream=True,
    extra_body={"knobridge": {"append_sources": False}},
)
for chunk in stream:
    extra = (chunk.model_extra or {}).get("knobridge") or {}
    if "citations" in extra:  # o primeiro chunk traz as citações, antes do texto
        print("Fontes:", [c["title"] for c in extra["citations"]])
    if chunk.choices:
        print(chunk.choices[0].delta.content or "", end="")
print()
```

**JavaScript (Node.js, SDK oficial, módulos ES):**

```js
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: `${process.env.KNOBRIDGE_URL}/v1`,
  apiKey: process.env.KNOBRIDGE_API_KEY,
  maxRetries: 0, // cada repetição viraria uma conversa nova
});

const answer = await client.chat.completions.create({
  model: "ERP:end_user",
  messages: [{ role: "user", content: "Como registrar a sangria do caixa?" }],
});
console.log(answer.choices[0].message.content);
console.log(answer.knobridge.citations); // campo extra, fora dos tipos do SDK

// Streaming, sem o rodapé de fontes (campos extras vão direto no corpo).
const stream = await client.chat.completions.create({
  model: "ERP:end_user",
  messages: [{ role: "user", content: "Como registrar a sangria do caixa?" }],
  stream: true,
  knobridge: { append_sources: false },
});
for await (const chunk of stream) {
  if (chunk.knobridge?.citations) console.log("Fontes:", chunk.knobridge.citations);
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}
```

Em TypeScript, o campo `knobridge` não está nos tipos do SDK: leia com um cast (`(answer as unknown as { knobridge: … }).knobridge`).

No streaming, o primeiro chunk traz `knobridge.citations` (antes do texto), os seguintes trazem o texto, o rodapé vem num chunk próprio (se ligado) e o último traz `finish_reason: "stop"` e `knobridge.status` e `cost_usd`. Com `stream_options: {"include_usage": true}`, um chunk final sem `choices` traz o `usage`.

Parâmetros como `temperature`, `max_tokens`, `tools` e `seed` são aceitos e ignorados (a configuração do nível e do produto decide); `n` maior que 1, `response_format` JSON, imagens e áudio são recusados com 400. Lista completa em [api-publica.md](../specs/api-publica.md#post-v1chatcompletions).

### 5. Acompanhar o uso e o custo

- **Uso e custos** (owner/admin): agrupe por **Canal** para ver as respostas da API separadas das do painel, por **Chave de API** para ver cada chave, ou por **Produto** e **Nível**. Os valores em US$ são estimativas do KnoBridge. Modelos sem preço cadastrado (como o `fake`) entram nas contagens e no aviso **Custo parcial**; para acrescentar preços, veja `KNOBRIDGE_CHAT_PRICES` no `.env.example` e em [uso-e-custos.md](../specs/uso-e-custos.md#preços-do-chat).
- **Chaves de API**: a coluna **Último uso** é atualizada no máximo uma vez por minuto.

## Como verificar

- `curl -s $KNOBRIDGE_URL/v1/models -H "Authorization: Bearer $KNOBRIDGE_API_KEY"` lista o produto e as entradas `produto:nível` até o nível máximo da chave.
- Uma pergunta sobre o conteúdo indexado volta com `knobridge.status: "completed"` e ao menos uma citação; uma pergunta sem relação volta com `"no_source"`, sem citações, e o texto de "sem fonte".
- Um `model` com nível acima do máximo da chave (ex.: `ERP:support` numa chave Usuário final) é recusado com 403 `level_not_allowed`.
- Em **Uso e custos**, agrupado por **Canal**, a linha **API** conta as respostas.

## Como desfazer: revogar a chave

Em **Chaves de API**, clique em **Revogar** na linha da chave e confirme. Ela deixa de valer na próxima requisição (401 `invalid_api_key`) e não volta: para reabrir o acesso, crie outra. As conversas feitas com ela continuam gravadas, e as respostas continuam contadas em **Uso e custos**. Para trocar uma chave sem parar o sistema, crie a nova, troque no sistema e só então revogue a antiga.

## Limites

- Pergunta de até 8000 caracteres; até 200 mensagens por pedido na API compatível com OpenAI, das quais as 10 mais recentes antes da pergunta viram histórico.
- Corpo de até 1 MiB em `/v1/chat/completions`, 64 KiB ao perguntar na REST e 4 KiB ao criar conversa (413 `payload_too_large`).
- Sem limite de requisições nem cota por chave nesta versão: acompanhe o custo em **Uso e custos**.
- Os SDKs da OpenAI repetem sozinhos erros 429 e 5xx, e cada repetição vira uma conversa nova; por isso os exemplos usam `max_retries=0` / `maxRetries: 0`. Se quiser repetir, controle no seu código.

## Erros comuns

A REST responde no formato do KnoBridge (`{"error": {"code", "message", "details"}}`); `/v1/models` e `/v1/chat/completions`, no da OpenAI (`{"error": {"message", "type", "param", "code"}}`), que os SDKs transformam em exceções (`AuthenticationError`, `NotFoundError`, `BadRequestError`…).

| Sintoma | Causa e solução |
|---|---|
| 401 `invalid_api_key` | Header ausente, sem `Bearer`, chave incompleta ou revogada. Confira a variável e o estado da chave no painel. |
| 403 `workspace_suspended` | O workspace foi suspenso na administração da instância. |
| 403 `level_not_allowed` | O nível pedido (no `model` ou em `level`) está acima do nível máximo da chave, ou o máximo baixou depois de criada a conversa. Use um nível até o máximo ou peça a um admin para subir o da chave. |
| 400 `level_not_configured` (409 na REST) | O nível não tem credencial e modelo no workspace. Um admin configura em **Configurações > Níveis de resposta**. |
| 404 `model_not_found` (ou `not_found` na REST) | Nome do produto diferente (maiúsculas contam), produto inativo ou excluído, ou fora do escopo da chave. Rode `GET /v1/models` para ver o que a chave alcança. |
| 404 numa conversa que existe | Ela foi criada por outra chave. |
| 409 `product_inactive` (REST) | O produto foi desativado depois de criada a conversa. |
| 400 `invalid_messages` | A última mensagem não é `user` com texto. |
| 400 `unsupported_parameter` ou `unsupported_content` | `n > 1`, `response_format` JSON, imagem, áudio ou arquivo. |
| 429, 502 ou 503 `provider_*` | O provedor de LLM ou de embedding recusou, limitou ou está fora do ar. Confira o provedor em **Provedores > Testar conexão**. |
| Sempre `no_source` | O produto não tem coleção ligada, a busca não encontra trechos ou os trechos estão acima do nível pedido (ex.: código num pedido em `end_user`). Teste a mesma pergunta no chat do painel e use **Testar busca** na coleção ([indexar-uma-fonte.md](indexar-uma-fonte.md#problemas-comuns)). |
| O SDK fica sem resposta no streaming | Um proxy entre o cliente e o KnoBridge está acumulando a resposta. O KnoBridge manda `X-Accel-Buffering: no`; em outros proxies, desligue o buffer para `/v1`. |

## Integrações anteriores à v0.2

Os assistentes viraram produtos com o **mesmo id e o mesmo nome**, então quem já usava a API continua funcionando:

- `model` com o nome ou o id do antigo assistente vale como o produto, sem nível (vale o máximo da chave);
- `assistant_id` em `POST /v1/conversations` é aceito como sinônimo obsoleto de `product_id` (mandar os dois é 422), e a resposta repete `assistant_id`;
- as chaves existentes ficaram com nível máximo **Desenvolvimento e produto**, porque até então toda resposta usava todas as fontes. Revise cada uma em **Chaves de API** e baixe o nível das que não precisam de código.

Os campos obsoletos saem numa versão futura, anunciada no `CHANGELOG.md`.
