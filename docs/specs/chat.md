# Chat com assistentes

> Rascunho v0.1 · 2026-10-10 · Em uso (plano 0002)

Como o KnoBridge responde a uma pergunta feita a um assistente: regra de citações, busca de fontes (`Retriever`), orquestração da rodada, estados das mensagens, histórico enviado ao LLM, feedback e visão administrativa. O formato dos eventos no fio (Server-Sent Events) está em [chat-sse.md](chat-sse.md) e não se repete aqui; os schemas das rotas JSON estão no [`openapi.json`](openapi.json); as tabelas, em [modelo-de-dados.md](modelo-de-dados.md#conversations).

Código: [`backend/src/knobridge/conversations/`](../../backend/src/knobridge/conversations/AGENTS.md) (motor), [`backend/src/knobridge/api/conversations.py`](../../backend/src/knobridge/api/AGENTS.md) e `api/admin_conversations.py` (rotas), [`backend/src/knobridge/llm/`](../../backend/src/knobridge/llm/AGENTS.md) (provedores). Tela: `frontend/src/features/chat/` e `frontend/src/features/conversations/`.

## Estado atual: sem RAG

Até existirem os pipelines de indexação (Fase 1 do roadmap da [visão](../01-visao-do-projeto.md#11-roadmap-sugerido)), a produção usa o `NullRetriever`, que nunca encontra fonte. Consequência direta da regra de citações: **toda resposta hoje é a mensagem de "sem fonte" do assistente, e o LLM não é chamado no chat**. O caminho com LLM (citações, streaming de `delta`, uso de tokens) já existe e é coberto por testes com um retriever e um provedor falsos, injetados pelas dependências `get_retriever` e `get_provider_factory` de `api/deps.py`. O provedor configurado no assistente só é chamado, por enquanto, no teste de conexão da tela de provedores.

## Regra de citações (regra 8 do AGENTS.md)

Resposta de assistente sem fonte não existe ([AGENTS.md](../../AGENTS.md), seção 2, regra 8). No código, isso vira três garantias:

1. **Sem fonte, sem LLM.** Se o `Retriever` devolve lista vazia, a resposta é a `no_source_message` do assistente, gravada com `status: no_source` e `citations: []`, sem chamar o provedor. A mensagem nunca é vazia: a coluna tem `CHECK`, e vazio ou nulo na API grava a mensagem padrão em pt-BR ("Não encontrei essa informação nas fontes que tenho disponíveis, então prefiro não arriscar uma resposta. Se quiser, posso abrir um chamado para a equipe de suporte."). O painel usa o status `no_source` para mostrar a oferta de abrir chamado.
2. **Com fonte, o LLM só responde a partir das fontes.** As fontes são numeradas a partir de 1, na ordem do retriever, e enviadas numa mensagem de sistema (`[n] título (uri)` + conteúdo). As instruções fixas, acrescentadas depois do prompt de sistema do assistente, mandam responder só com as fontes, citar cada afirmação como `[n]`, usar o idioma e o tom do assistente e, se as fontes não bastarem, responder exatamente a `no_source_message` (`conversations/prompt.py`).
3. **As citações são gravadas antes do texto.** A lista de citações vai no primeiro evento do stream e fica gravada na mensagem: `index` (o mesmo `n` do texto), `title`, `uri`, `snippet` (até 300 caracteres) e `document_id`. O texto completo da fonte só vai para o LLM.

Limite conhecido: quando há fonte e o LLM responde a `no_source_message` por conta própria, a mensagem fica `completed` com as citações recebidas; não há verificação automática de que o texto usa os `[n]`. A avaliação disso fica para a fase de observabilidade (D13 da visão).

## `Retriever`

Interface em `conversations/retrieval.py`:

| Tipo | Papel |
|---|---|
| `RetrievalQuery` | `workspace_id`, `assistant_id`, `user_id` (para filtrar por ACL da fonte, seção 9 do AGENTS.md) e o texto da pergunta. |
| `Source` | `title`, `content`, `uri` (opcional), `document_id` (opcional). |
| `Retriever` (`Protocol`) | `async retrieve(query) -> Sequence[Source]`: fontes da pergunta, da melhor para a pior; vazia quando nada é relevante. |
| `NullRetriever` | Implementação de produção até existir indexação: devolve sempre vazio. |

A busca híbrida, o reranker e a montagem de contexto (seção 7.4 da visão) entram como outra implementação de `Retriever`, trocada em `api/deps.py:get_retriever`, sem mudar o motor do chat. O retriever é chamado dentro da transação da fase 1, com o escopo de RLS do workspace.

## Orquestração em duas fases

`ChatService` (`conversations/chat.py`) divide cada rodada em duas fases, para nenhuma transação ficar aberta enquanto o LLM gera a resposta (segundos):

```mermaid
sequenceDiagram
    participant C as Cliente
    participant A as API
    participant DB as Postgres
    participant R as Retriever
    participant L as LLM
    C->>A: POST .../messages (pergunta)
    A->>DB: fase 1: trava a conversa, grava a pergunta
    A->>R: retrieve(pergunta)
    R-->>A: fontes
    alt sem fonte
        A->>DB: grava resposta no_source (final)
        A-->>C: citations [], delta (mensagem sem fonte), done
    else com fonte
        A->>DB: grava resposta streaming com as citações
        A-->>C: citations
        A->>L: fase 2: stream_chat (fora de transação)
        L-->>A: deltas
        A-->>C: delta...
        A->>DB: grava o desfecho (sessão nova e curta)
        A-->>C: done ou error
    end
```

1. **`prepare` (fase 1)**, na transação da requisição (`WorkspaceContext`), que faz commit antes do primeiro byte da resposta:
   - lê a conversa com `FOR UPDATE` (serializa perguntas simultâneas e garante `position` única) e exige que quem pergunta seja o dono;
   - grava `interrupted` em respostas `streaming` órfãs da conversa (ver abaixo);
   - exige assistente ativo (409 `assistant_inactive`);
   - lê o histórico, chama o retriever, define o título da conversa na primeira pergunta (a pergunta numa linha, até 80 caracteres, sem LLM) e grava a pergunta;
   - sem fonte: grava a resposta final `no_source`; com fonte: grava um marcador `streaming` com as citações e o modelo, e prepara a chamada ao LLM (a chave é decifrada só em memória).
   Por isso, erros de acesso e de estado saem como JSON comum, antes do stream ([chat-sse.md](chat-sse.md#requisição)).
2. **`stream` (fase 2)**: emite `citations`, repassa cada pedaço do provedor como `delta` e, no fim, grava o desfecho num `scoped_session` novo e curto: `completed` com tokens e latência, `failed` com o `error_code`, ou `interrupted` com o conteúdo parcial se o cliente desconectou. A gravação final roda protegida contra cancelamento e só altera mensagem ainda `streaming`, então acontece uma vez só (uma conversa excluída no meio não casa com nada).
3. **`settle`**: chamado sempre que o stream HTTP fecha; marca `interrupted` a resposta cujo stream nem começou.

Erros do provedor viram evento `error` com o código de domínio (`provider_auth_failed`, `provider_rate_limited`, `provider_unavailable`, `provider_request_failed`); qualquer outra exceção vira `chat_failed`, registrada no log só pelo tipo, porque o texto pode conter a chave. Logs (`chat_turn_finished`, `chat_turn_crashed`) levam `workspace_id` e `conversation_id`, nunca a pergunta nem a resposta.

## Estados das mensagens

| `status` | Papel | Quando |
|---|---|---|
| `completed` | `user` | Toda pergunta. |
| `streaming` | `assistant` | Marcador gravado na fase 1 enquanto o LLM responde. |
| `completed` | `assistant` | O LLM terminou; resposta com citações. |
| `no_source` | `assistant` | Nenhuma fonte; mensagem de "sem fonte", sem LLM. |
| `failed` | `assistant` | Erro do provedor ou do servidor; `error_code` diz qual; `content` guarda o que chegou antes do erro. |
| `interrupted` | `assistant` | O cliente desconectou antes do fim, ou o processo morreu no meio do stream. |

```mermaid
stateDiagram-v2
    [*] --> no_source: sem fonte (fase 1)
    [*] --> streaming: com fonte (fase 1)
    streaming --> completed: provedor terminou
    streaming --> failed: erro do provedor ou do servidor
    streaming --> interrupted: cliente desconectou ou resposta órfã
    no_source --> [*]
    completed --> [*]
    failed --> [*]
    interrupted --> [*]
```

**Resposta órfã.** Se o processo da API morre no meio do stream, ninguém grava o desfecho. Nenhum stream dura mais que 5 minutos (`STALE_STREAMING_AFTER`, `conversations/stale.py`), então uma resposta `streaming` com `updated_at` mais antigo que isso, pelo relógio injetado, é mostrada como `interrupted` em toda leitura (conversa do dono, detalhe e estatísticas da visão administrativa), sem gravar nada, e é regravada como `interrupted` pela fase 1 da próxima pergunta da conversa.

## Histórico enviado ao LLM

Com fonte, o LLM recebe, nesta ordem: as instruções (prompt do assistente + regras fixas), as fontes numeradas, o histórico e a pergunta nova. O histórico são as **10 mensagens mais recentes** da conversa (`DEFAULT_HISTORY_WINDOW`), das mais antigas para as mais novas, contando os dois papéis: todas as perguntas e só as respostas `completed` ou `no_source` (respostas `failed`, `interrupted` e `streaming` ficam de fora). A pergunta atual não conta na janela. A temperatura é a do assistente.

## Acesso e privacidade

A RLS isola o workspace; dentro dele, as regras são da aplicação (`Reader` em `conversations/service.py`):

| Ação | Quem pode |
|---|---|
| Criar conversa | Qualquer membro (inclusive leitor), com assistente ativo do workspace. |
| Listar "minhas conversas" | Cada um vê só as próprias, da mais recente para a mais antiga. |
| Ler uma conversa | O dono, e owner/admin do workspace. Os demais recebem 404. |
| Enviar mensagem, excluir conversa | Só o dono. Owner/admin que leem a conversa de outro recebem 403 `forbidden`. A exclusão é auditada (`conversation.deleted`, sem conteúdo). |
| Avaliar resposta | Quem pode ler a conversa. |

Matriz completa em [autenticacao.md](autenticacao.md#matriz-de-permissões).

## Feedback

`POST .../conversations/{conversation_id}/messages/{message_id}/feedback` com `{"rating": "up" | "down", "comment": "..."}` (comentário opcional, até 2000 caracteres). Um feedback por mensagem e usuário: enviar de novo substitui (upsert). Só mensagens do assistente aceitam feedback (422 `feedback_target_invalid`). Na leitura da conversa (`GET .../conversations/{id}`), cada mensagem traz o feedback de quem está lendo.

## Visão administrativa

Owner e admin do workspace têm rotas próprias em `/v1/workspaces/{workspace_id}/admin/conversations` (tela **Conversas** do painel):

- `GET ""`: conversas de todos os membros, da mais recente para a mais antiga, com nome do usuário e do assistente, contagem de mensagens, de 👍 e de 👎 e data da última mensagem. Filtros: `assistant_id`, `user_id`, período de criação semiaberto `[created_from, created_to)` (UTC; início maior ou igual ao fim dá 422) e `negative_feedback=true` (só conversas com ao menos um 👎). Paginada (`limit`/`offset`, `total`).
- `GET /stats`: totais do período (padrão: os 30 dias anteriores ao relógio do servidor): conversas (pela data de criação), mensagens, 👍, 👎 e respostas `no_source`, `failed` e `interrupted` (pela data da mensagem).
- `GET /{conversation_id}`: a conversa com as mensagens paginadas e o feedback de todos, com quem deu.

As consultas usam número constante de statements, independente do tamanho da página (há teste que conta). A visão é só leitura: o admin não envia mensagens nem exclui conversas de outros.

## Referências

- Server-Sent Events: <https://html.spec.whatwg.org/multipage/server-sent-events.html>
