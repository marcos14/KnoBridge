# Receber chamados por API: do sistema de chamados às respostas citando chamados

> Rascunho v0.1 · 2026-10-12 · Em uso (plano 0005)

Passo a passo para quem vai integrar um sistema de chamados ao KnoBridge: criar a fonte e o token, converter os chamados para o formato do KnoBridge, enviar por API (com `curl`, Python ou n8n), fazer a carga histórica por upload, conferir a anonimização na prévia e, no sentido contrário, receber os pedidos de "Abrir chamado" que o chat envia quando não sabe responder.

O KnoBridge não busca chamados em nenhum sistema. Quem integra **empurra** os chamados num formato único, e qualquer sistema serve: Zendesk, GLPI, Movidesk, Jira Service Management ou um sistema próprio. Por dentro: arquitetura no [ADR 0006](../adr/0006-chamados-por-push.md), contrato completo em [chamados.md](../specs/chamados.md).

## Pré-requisitos

- Um servidor do KnoBridge no ar ([subir-ambiente.md](subir-ambiente.md)) e um workspace onde você é **owner ou admin** (para gerar o token de envio e o segredo do webhook). Editores criam a fonte, fazem upload e usam a prévia.
- Uma coleção com credencial de embedding e um assistente ([indexar-uma-fonte.md](indexar-uma-fonte.md), passos 2 e 3; [primeiro-acesso.md](primeiro-acesso.md) para o assistente).
- Do lado do sistema de chamados: um lugar para rodar a conversão (script agendado, automação do próprio sistema, n8n ou outro iPaaS) com acesso HTTPS de saída até o KnoBridge.

Sem dados reais para testar? Gere chamados sintéticos em pt-BR com o gerador do repositório, fora da pasta do repositório:

```sh
cd scripts
uv run python -m synthetic_tickets --seed 7 --tickets 300 --out ../../kb-sinteticos
```

O `tickets.jsonl` gerado tem um chamado por linha e serve para o upload do passo 6. O `gabarito.json` lista cada dado pessoal semeado e o marcador que a anonimização deve aplicar ([scripts/synthetic_tickets/AGENTS.md](../../scripts/synthetic_tickets/AGENTS.md)).

## Passos

### 1. Criar a fonte de chamados

1. Vá em **Fontes > Nova fonte**, escolha **Chamados**, dê um nome (ex.: `suporte`) e escolha a coleção.
2. Decida a configuração (dá para mudar depois, mas vale só para os chamados processados depois da mudança):
   - **Anonimizar** (ligado por padrão): troca dados pessoais por marcadores antes de indexar (passo 7).
   - **Incluir notas internas** (desligado por padrão): mensagens com `public: false` entram no índice.
   - **Status indexados**: por padrão os quatro (`open`, `pending`, `resolved`, `closed`). Chamados fora da lista ficam fora do índice.
3. Salve. A fonte abre com as abas **Integração**, **Upload**, **Prévia** e **Indexação**.

### 2. Gerar o token de envio

1. Na aba **Integração**, clique em **Gerar token** e confirme.
2. Copie o token `kbi_...`. Ele aparece **uma única vez**: o servidor guarda só o hash. Gerar outro invalida o anterior na hora.
3. Guarde o token como segredo da integração, por exemplo na variável de ambiente `KNOBRIDGE_INGEST_TOKEN`, que os exemplos abaixo usam.

O token só abre `POST /v1/ingest/tickets` dessa fonte. Ele não entra no painel nem em outra rota. A aba **Integração** também mostra exemplos prontos de `curl` e Python com a URL do seu servidor, e a situação da integração: prefixo do token atual, chamados por estado e o último recebimento.

### 3. Converter os chamados para o formato do KnoBridge

Cada chamado é um objeto JSON. O schema completo, com limites e exemplos válido e inválido, está em [chamados.md, Formato do chamado](../specs/chamados.md#formato-do-chamado). O essencial:

| Campo | Obrigatório | O que pôr |
|---|---|---|
| `external_id` | sim | O id estável do chamado no seu sistema. É a chave: o mesmo id atualiza o mesmo chamado. |
| `title` | sim | Assunto. |
| `status` | sim | Um de `open`, `pending`, `resolved`, `closed`. Mapeie os status do seu sistema para estes; o nome original vai em `original_status`. |
| `created_at`, `updated_at` | sim | Instantes RFC 3339 **com fuso** (`2026-10-01T10:00:00-03:00` ou `...Z`). `updated_at` decide qual versão vale. |
| `number`, `url` | não | Número que o usuário reconhece e link do chamado no seu sistema. Aparecem na citação. |
| `messages` | não | A conversa: `role` (`customer`, `agent` ou `system`), `body`, `body_format` (`text`, `markdown` ou `html`), `public` e `created_at`. |
| `resolution` | não | A solução final. É o que o chat mais usa: chamados resolvidos com solução respondem melhor. |
| `requester`, `assignees` | não | Nome, e-mail e empresa. Nunca aparecem no índice: servem para a anonimização saber quais nomes trocar. |

Exemplo mínimo:

```json
{
  "external_id": "4f6c2a10-0001",
  "number": "48213",
  "title": "Erro 4021 ao fechar o caixa",
  "status": "resolved",
  "created_at": "2026-09-30T14:02:00-03:00",
  "updated_at": "2026-10-01T09:15:00-03:00",
  "messages": [
    { "role": "customer", "body": "Ao fechar o caixa aparece o erro 4021.", "created_at": "2026-09-30T14:02:00-03:00" }
  ],
  "resolution": { "body": "Finalize a sangria do turno anterior e feche o caixa de novo." }
}
```

Campos desconhecidos são recusados, e a validação é estrita: booleano é `true`/`false`, número é número. Anexos vão só pelo nome (`attachments: [{"name": "print.png"}]`); o arquivo não é enviado.

### 4. Enviar pela API

`POST /v1/ingest/tickets` recebe de 1 a 100 itens por requisição. Cada item é um `upsert` (com o chamado) ou um `delete` (com o `external_id`):

```sh
curl -X POST "https://knobridge.exemplo.com.br/v1/ingest/tickets" \
  -H "Authorization: Bearer $KNOBRIDGE_INGEST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      { "op": "upsert", "ticket": { "external_id": "4f6c2a10-0001", "title": "Erro 4021 ao fechar o caixa",
        "status": "resolved", "created_at": "2026-09-30T14:02:00-03:00", "updated_at": "2026-10-01T09:15:00-03:00",
        "resolution": { "body": "Finalize a sangria do turno anterior e feche o caixa de novo." } } },
      { "op": "delete", "external_id": "4f6c2a10-0099", "deleted_at": "2026-10-02T08:00:00Z" }
    ]
  }'
```

A resposta é **202** com um resultado por item, na ordem:

```json
{
  "results": [
    { "index": 0, "op": "upsert", "external_id": "4f6c2a10-0001", "status": "queued", "error": null },
    { "index": 1, "op": "delete", "external_id": "4f6c2a10-0099", "status": "queued", "error": null }
  ],
  "counts": { "queued": 2, "unchanged": 0, "stale": 0, "rejected": 0 },
  "sync": "started",
  "run_id": "6a1f..."
}
```

| `status` do item | O que fazer |
|---|---|
| `queued` | Nada: gravado, a indexação começa sozinha (`sync`). |
| `unchanged` | Nada: o KnoBridge já tinha esse conteúdo. |
| `stale` | Nada: você mandou uma versão com `updated_at` mais antigo que a guardada (ou o chamado foi removido depois). Ela é ignorada. |
| `rejected` | Corrija o chamado e reenvie: `error.code` diz o motivo e `error.details` lista `{loc, problem}`, como `["created_at"]` com `timezone_aware`. |

Um item inválido não derruba o lote: os outros seguem. **Reenviar é sempre seguro**: o mesmo conteúdo volta `unchanged` e nada é indexado de novo. Por isso, em erro de rede, 500 ou 503, repita o lote inteiro com espera crescente.

**Remoção**: `{"op": "delete", "external_id": "...", "deleted_at": "..."}` tira o chamado do índice. A remoção vale contra envios atrasados: um `upsert` com `updated_at` anterior à remoção volta `stale`. Para trazer o chamado de volta, envie-o com `updated_at` mais novo que o `deleted_at`.

Em Python, só com a biblioteca padrão, lendo um export JSONL (um chamado por linha) em lotes de 100, com retentativa e tratamento por item:

```python
import json
import os
import time
import urllib.error
import urllib.request

URL = "https://knobridge.exemplo.com.br/v1/ingest/tickets"
TOKEN = os.environ["KNOBRIDGE_INGEST_TOKEN"]
RETRY_STATUS = {500, 502, 503, 504}


def send(items: list[dict]) -> dict:
    """Envia um lote; repete em erro de rede, 5xx e 503 (reenviar é seguro)."""
    body = json.dumps({"items": items}).encode("utf-8")
    for attempt in range(6):
        request = urllib.request.Request(
            URL,
            data=body,
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUS:
                raise  # 401 token, 409 fonte desativada, 413 lote grande, 422 corpo malformado
        except urllib.error.URLError:
            pass
        time.sleep(2**attempt)
    raise RuntimeError("KnoBridge indisponível; tente o lote de novo mais tarde")


def batches(path: str, size: int = 100):
    batch = []
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            if line.strip():
                batch.append({"op": "upsert", "ticket": json.loads(line)})
            if len(batch) == size:
                yield batch
                batch = []
    if batch:
        yield batch


for items in batches("chamados.jsonl"):
    result = send(items)
    for item in result["results"]:
        if item["status"] == "rejected":
            error = item["error"]
            print(item["external_id"], error["code"], error["details"])
    print(result["counts"], result["sync"])
```

Para uma integração contínua, envie o chamado a cada mudança (abertura, nova mensagem, solução, mudança de status) com o `updated_at` do seu sistema. Envios fora de ordem não regridem: vale sempre o de `updated_at` maior.

### 5. Exemplo com n8n

Um fluxo de três nós, descrito para você montar no editor do n8n:

1. **Webhook** (gatilho): copie a URL de produção do nó e cadastre-a como webhook no seu sistema de chamados, para os eventos de chamado criado, atualizado, resolvido e excluído. Método `POST`.
2. **Code** (JavaScript, "Run Once for Each Item"): converte o corpo recebido para um item da API do KnoBridge. Exemplo para um sistema que manda `id`, `protocolo`, `assunto`, `situacao`, `abertura`, `alteracao`, `interacoes` e `excluido`:

   ```javascript
   const t = $json.body;
   const status = { Novo: "open", "Em atendimento": "open", "Aguardando cliente": "pending",
     Resolvido: "resolved", Fechado: "closed" }[t.situacao] ?? "open";
   if (t.excluido) {
     return { json: { items: [{ op: "delete", external_id: String(t.id), deleted_at: t.alteracao }] } };
   }
   return { json: { items: [{ op: "upsert", ticket: {
     external_id: String(t.id),
     number: String(t.protocolo),
     title: t.assunto,
     status,
     original_status: t.situacao,
     url: `https://suporte.exemplo.com.br/chamados/${t.protocolo}`,
     created_at: t.abertura,
     updated_at: t.alteracao,
     messages: t.interacoes.map((m) => ({
       role: m.de_cliente ? "customer" : "agent",
       public: !m.interna,
       body: m.texto_html,
       body_format: "html",
       created_at: m.data,
     })),
   } }] } };
   ```

   Garanta que as datas cheguem com fuso (se o sistema manda `2026-10-01 10:00:00`, acrescente `-03:00`).
3. **HTTP Request**: método `POST`, URL `https://knobridge.exemplo.com.br/v1/ingest/tickets`, autenticação por cabeçalho (`Authorization` = `Bearer kbi_...`, guardado como credencial do n8n, não no fluxo), corpo JSON = `{{ $json }}`. Em **Settings**, ligue **Retry On Fail** (3 tentativas, espera de 5 s) para cobrir rede, 500 e 503.

Se o seu sistema só tem API (sem webhook), troque o nó Webhook por um **Schedule Trigger** e um **HTTP Request** que lista os chamados alterados desde a última execução.

### 6. Carga histórica por upload

Para trazer o histórico de uma vez, exporte os chamados num arquivo e envie pela aba **Upload**:

- `.jsonl`: um item por linha; ou `.json`: uma lista, ou `{"items": [...]}` igual ao corpo da API;
- cada item pode ser um item da API (`{"op": "upsert", "ticket": ...}`, `{"op": "delete", ...}`) ou um chamado puro, lido como `upsert`;
- até **50 MiB** por arquivo, sem limite de itens. O servidor processa em blocos de 100, com as mesmas regras da API.

O relatório mostra quantos itens foram lidos, quantos entraram na fila, quantos não mudaram, quantos eram antigos e a tabela dos recusados com a linha (JSONL) ou a posição (JSON) e o motivo. O arquivo não é guardado. Reenviar o mesmo arquivo é seguro: o que já entrou volta `unchanged`. Um arquivo maior que 50 MiB pode ser dividido ou enviado pela API.

### 7. Conferir a anonimização na prévia

Antes de ligar a integração, cole um chamado real na aba **Prévia** e clique em **Gerar prévia**. Ela mostra o Markdown exatamente como vai para o índice, com a configuração atual da fonte, e quais marcadores foram aplicados. **Nada é gravado.**

Com a anonimização ligada (padrão), sem LLM e de forma determinística:

| É trocado | Por |
|---|---|
| E-mails | `[EMAIL]` |
| IPv4 e IPv6 | `[IP]` (um número de versão depois de "versão", "version", "release", "build" ou "v" não é trocado) |
| CNPJ e CPF com dígitos verificadores válidos | `[CNPJ]`, `[CPF]` |
| Cartões que passam no algoritmo de Luhn | `[CARTAO]` |
| Telefones com DDD, ou `9xxxx-xxxx` | `[TELEFONE]` |
| Nome e primeiro nome do solicitante | `[SOLICITANTE]` |
| Empresa do solicitante | `[ORGANIZACAO]` |
| Atendentes e autores de mensagens de atendente | `[ATENDENTE_1]`, `[ATENDENTE_2]`... |
| Outros autores de mensagens de cliente | `[CLIENTE_1]`, `[CLIENTE_2]`... |

**Não é trocado**: nomes de terceiros que não estão no payload (o contador citado na mensagem, por exemplo), endereços, placas e outros dados fora das regras; `external_id`, `number`, datas e `url`. O link (`url`) vai só para a citação, não para o texto indexado, então não ponha dado pessoal nele. Para nomes de terceiros, declare-os como autores ou remova-os antes de enviar. Os limites completos estão em [chamados.md, Anonimização](../specs/chamados.md#anonimização).

`requester` e `assignees` nunca aparecem no índice. Notas internas ficam fora, a não ser que a fonte as inclua. Depois de indexado, o JSON bruto do chamado é apagado: sobram o Markdown anonimizado e os hashes. Por isso, **mudar a configuração da fonte vale só para os chamados processados depois**; para reaplicar, reenvie os chamados com conteúdo ou `updated_at` novos.

### 8. Ligar a coleção ao assistente e conversar

Ligue a coleção da fonte ao assistente (**Assistentes > Editar > Coleções**). Quando a resposta usa um chamado, a citação mostra o título, o número, o status (Aberto, Pendente, Resolvido ou Fechado) e a data; ao abri-la, o painel da citação traz o link **Abrir o chamado no sistema de origem** quando você envia `url`. O assistente prefere a solução de chamados resolvidos ou fechados e trata abertos e pendentes como problema em andamento.

### 9. Receber "Abrir chamado" do chat

Quando o assistente não sabe responder, o chat pode abrir um chamado no seu sistema. O KnoBridge envia um `POST` assinado para uma URL sua; você abre o chamado e devolve o número.

1. Em **Assistentes > Editar**, ligue **Oferecer "Abrir chamado" no chat**, informe a **URL do webhook** (`https`, num endereço público: endereços internos e reservados são recusados) e salve.
2. Abra a edição de novo e clique em **Gerar segredo**. Copie o `kbw_...`: ele aparece **uma única vez** e o destino precisa dele para conferir as assinaturas.
3. Clique em **Testar entrega**. O destino recebe um evento `ticket.test` e deve responder 2xx sem abrir chamado.

No chat, numa resposta sem fonte, o usuário clica **Abrir chamado**, revê a pergunta, o resumo (editável), o nome e o e-mail dele e as mensagens que vão junto, e confirma. O destino recebe:

```http
POST /seu/webhook HTTP/1.1
Content-Type: application/json
User-Agent: KnoBridge-Webhook/1
KnoBridge-Event: ticket.requested
KnoBridge-Delivery: 0e8b...
KnoBridge-Signature: t=1760274000,v1=5f2c...

{"event":"ticket.requested","version":1,"id":"0e8b...","created_at":"2026-10-12T13:00:00Z","workspace":{...},"assistant":{...},"conversation":{"id":"...","url":"https://kb.exemplo.com.br/w/.../conversations/..."},"requester":{"name":"...","email":"..."},"question":"...","summary":"...","messages":[...]}
```

O payload completo está em [chamados.md, Payload](../specs/chamados.md#payload). Para conferir a assinatura: separe `t` e `v1` do cabeçalho, recuse se `t` estiver a mais de 300 s do seu relógio, calcule o HMAC-SHA256 de `"<t>.<corpo bruto>"` com o segredo `kbw_...` inteiro como chave e compare com `v1` em tempo constante. Use o corpo **bruto**, antes de qualquer parse.

Em Python:

```python
import hashlib
import hmac
import time


def assinatura_valida(cabecalho: str, corpo: bytes, segredo: str) -> bool:
    pares = [parte.strip().partition("=") for parte in cabecalho.split(",")]
    t = next((valor for nome, _, valor in pares if nome == "t"), "")
    assinaturas = [valor for nome, _, valor in pares if nome == "v1"]
    if not t.isdigit() or abs(time.time() - int(t)) > 300:
        return False
    esperado = hmac.new(segredo.encode(), t.encode() + b"." + corpo, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(esperado, v1) for v1 in assinaturas)
```

Em Node (Express), com o corpo bruto:

```javascript
import crypto from "node:crypto";
import express from "express";

const SECRET = process.env.KNOBRIDGE_WEBHOOK_SECRET; // kbw_...
const app = express();

function validSignature(header, raw) {
  const pairs = header.split(",").map((part) => part.trim().split("="));
  const t = pairs.find(([name]) => name === "t")?.[1] ?? "";
  if (!/^\d+$/.test(t) || Math.abs(Date.now() / 1000 - Number(t)) > 300) return false;
  const expected = crypto.createHmac("sha256", SECRET).update(`${t}.`).update(raw).digest();
  return pairs
    .filter(([name]) => name === "v1")
    .some(([, v1]) => {
      const given = Buffer.from(v1 ?? "", "hex");
      return given.length === expected.length && crypto.timingSafeEqual(given, expected);
    });
}

app.post("/knobridge/chamados", express.raw({ type: "application/json" }), async (req, res) => {
  if (!validSignature(req.get("KnoBridge-Signature") ?? "", req.body)) return res.sendStatus(401);
  const event = JSON.parse(req.body.toString("utf8"));
  if (event.event === "ticket.test") return res.json({});
  // Use event.id para não abrir dois chamados: as retentativas repetem o mesmo id.
  const ticket = await abrirChamadoUmaVez(event.id, event); // seu sistema
  res.json({ ticket_id: ticket.number, url: ticket.url });
});
```

Responda **2xx** com `{"ticket_id": "...", "url": "https://..."}`: o chat mostra "Chamado 48213 aberto." com o link. Corpo vazio ou sem esses campos também conta como entregue, só sem número.

**Retentativas**: 408, 429, 5xx, timeout (10 s por tentativa) e erro de rede são tentados de novo, com espera de 10 s dobrando até 1 h, por até 24 h. Outros 4xx e qualquer 3xx (redirecionamentos não são seguidos) são falha definitiva, e o chat mostra que não foi possível abrir o chamado. Toda tentativa leva o mesmo `id` e o mesmo corpo, com um `t` novo: **use o `id` para não abrir o chamado duas vezes**.

## Como verificar

- A aba **Integração** mostra o prefixo do token atual, os chamados por estado (aguardando processamento, indexados, fora dos status indexados, remoções aguardando, removidos), quantos falharam no último processamento e a data do último recebimento.
- A aba **Indexação** mostra as execuções disparadas pelos envios e os documentos dos chamados.
- No chat, uma pergunta sobre um chamado resolvido traz a citação com número e status.
- Em **Assistentes > Editar**, **Testar entrega** responde "O destino aceitou a entrega de teste." quando o destino confere a assinatura e devolve 2xx.

## Como desfazer

- **Parar de receber**: gere um novo token e não o entregue a ninguém (o anterior para na hora), ou desative a fonte (os envios voltam 409 `source_inactive`).
- **Tirar chamados do índice**: envie `delete` para cada `external_id`, ou exclua a fonte, o que apaga a caixa de entrada, o índice da fonte e invalida o token.
- **Desligar "Abrir chamado"**: desmarque **Oferecer "Abrir chamado" no chat** no assistente.

## Limites

| O quê | Limite |
|---|---|
| Itens por requisição da API | 1 a 100 |
| Corpo da requisição | 5 MiB |
| Um chamado | 1 MiB de JSON, até 500 mensagens, 100 anexos, 50 tags, 50 campos adicionais |
| Arquivo de upload | 50 MiB, sem limite de itens |
| Prévia | 2 MiB |
| Webhook de saída | 10 s por tentativa, retentativas por 24 h |

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| 401 `invalid_ingest_token` | Token ausente, copiado errado ou girado. Gere outro na aba **Integração** e atualize a integração. |
| 409 `source_inactive` | A fonte está desativada. Ative-a; nada foi gravado. |
| 413 `payload_too_large` | Lote acima de 5 MiB. Mande menos itens por requisição. |
| 422 `validation_error` na requisição toda | JSON inválido, `items` vazio ou com mais de 100, ou item com `op` desconhecido. |
| Item `rejected` com `timezone_aware` | Instante sem fuso. Acrescente `-03:00` ou `Z`. |
| Item `rejected` com `updated_at_before_created_at` | `updated_at` anterior a `created_at`. |
| Item `rejected` com `extra_forbidden` | Campo que não existe no formato. Mova-o para `custom_fields`. |
| Item `rejected` com `duplicate_in_batch` | O mesmo `external_id` duas vezes no lote. Mande só a versão mais nova. |
| Item `stale` | O KnoBridge já tem uma versão mais nova (ou uma remoção posterior). Confira o `updated_at` que você envia. |
| `sync: deferred` | O serviço de sincronização estava fora do ar. Os chamados ficaram guardados e entram na próxima sincronização (outro envio ou **Sincronizar** na fonte). |
| Chamado não aparece no chat | Confira se ele foi indexado (aba **Integração**), se o status está entre os indexados e se a coleção está ligada ao assistente. |
| Mudei a anonimização e nada mudou | A configuração vale para os chamados processados depois. Reenviar o mesmo conteúdo volta `unchanged` e não reprocessa: reenvie com `updated_at` mais novo (o conteúdo pode ser o mesmo). |
| Webhook recusado ao salvar (`webhook_destination_blocked`) | A URL resolve para endereço interno, privado ou reservado. Use um endereço público com `https`. |
| "A entrega de teste falhou" com HTTP 401 | O destino não aceitou a assinatura: confira o segredo (gere outro se perdeu) e se a verificação usa o corpo bruto. |

## Referências

- Contrato: [chamados.md](../specs/chamados.md); citação no chat: [chat-sse.md](../specs/chat-sse.md#citations).
- Decisão de arquitetura: [ADR 0006](../adr/0006-chamados-por-push.md).
- Gerador de dados sintéticos: [scripts/synthetic_tickets/AGENTS.md](../../scripts/synthetic_tickets/AGENTS.md).
