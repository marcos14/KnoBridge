# Chat com produtos e níveis

> Rascunho v0.5 · 2026-10-14 · Em uso (planos 0002, 0003, 0008 e 0009; plano 0010 em implementação)
>
> **Mudanças da v0.5** (plano 0010, F1.1; implementação nas F2.2 e F3.2): canais **`mcp`** (ferramenta `ask` do servidor MCP, conversa da chave; [mcp.md](mcp.md#ask)) e **`widget`** (visitante do widget, conversa do widget, sempre no nível `end_user`; [widget.md](widget.md)); a conversa tem exatamente um dono: pessoa, chave ou widget ([Acesso e privacidade](#acesso-e-privacidade)); feedback do visitante sem usuário; a visão administrativa mostra e filtra os dois canais, o widget e o visitante ([Visão administrativa](#visão-administrativa)).
>
> **Mudanças da v0.4** (plano 0009, F1.1; implementação nas F2.1 a F2.4): o **produto** substitui o assistente e cada conversa tem um **nível** (`end_user`, `support`, `product_dev`) que decide as fontes (filtro de nível mínimo no SQL da busca), as instruções (texto do nível + texto do produto) e o modelo (do nível, no workspace) ([produtos-e-niveis.md](produtos-e-niveis.md)); nível conferido a cada pergunta (403 `level_not_allowed`, 409 `level_not_configured`, 409 `product_inactive`); mensagens gravam produto e nível; citação `kind: card` ([cards.md](cards.md#citação-kind-card)) e regra fixa de cards; citação de conhecimento sem evidências no nível `end_user`; visão administrativa filtra produto e nível; a lista e a duplicação de assistentes viram as de produtos ([Listagem e duplicação de produtos](#listagem-e-duplicação-de-produtos)).
>
> **Mudanças da v0.3** (plano 0008, F1.1; implementação nas F2.2, F2.3 e F2.5): cada resposta grava o canal e o custo estimado ([Custo e canal por resposta](#custo-e-canal-por-resposta)); conversas da API pública, de uma chave e não de uma pessoa ([api-publica.md](api-publica.md#conversas-da-api)); a visão administrativa mostra e filtra o canal; busca, filtros e ordenação na lista de assistentes e a ação de duplicar (desde a v0.4, de produtos: [Listagem e duplicação de produtos](#listagem-e-duplicação-de-produtos)).
>
> **Mudanças da v0.2** (plano 0003, F4.2): o chat busca as fontes de verdade (`HybridRetriever` sobre as coleções do assistente, com a similaridade mínima dele), as citações ganham caminho, linhas, símbolo, linguagem e SHA (e, na F6.1, autor e data dos commits), e as regras fixas do prompt passam a ser em pt-BR e mais estritas.

Como o KnoBridge responde a uma pergunta feita sobre um produto, num nível de resposta (até a v0.3, "a um assistente"): regra de citações, busca de fontes (`Retriever`), orquestração da rodada, estados das mensagens, histórico enviado ao LLM, feedback e visão administrativa. O formato dos eventos no fio (Server-Sent Events) está em [chat-sse.md](chat-sse.md) e não se repete aqui; os schemas das rotas JSON estão no [`openapi.json`](openapi.json); as tabelas, em [modelo-de-dados.md](modelo-de-dados.md#conversations).

Código: [`backend/src/knobridge/conversations/`](../../backend/src/knobridge/conversations/AGENTS.md) (motor), [`backend/src/knobridge/retrieval/`](../../backend/src/knobridge/retrieval/AGENTS.md) (busca e montagem das fontes), [`backend/src/knobridge/api/conversations.py`](../../backend/src/knobridge/api/AGENTS.md) e `api/admin_conversations.py` (rotas), [`backend/src/knobridge/llm/`](../../backend/src/knobridge/llm/AGENTS.md) (provedores). Tela: `frontend/src/features/chat/` e `frontend/src/features/conversations/`.

## Recuperação de fontes

Cada produto consulta as coleções ligadas a ele (`collection_ids` na API do produto, tabela `product_collections` em [modelo-de-dados.md](modelo-de-dados.md)) com a sua similaridade mínima (`min_similarity`, padrão 0,35; decisão D12 do plano 0003, calibrado pelo [ensaio com dados reais](../pesquisa/0001-ensaio-minski.md)), **só nos trechos permitidos ao nível da conversa** (v0.4; [produtos-e-niveis.md](produtos-e-niveis.md#o-filtro-na-busca)). A produção usa o `HybridRetriever` (`retrieval/retriever.py`):

1. Lê, numa consulta, a similaridade mínima e as coleções do produto. **Sem coleção, devolve vazio sem chamar o provedor de embedding** (e o chat responde "sem fonte" sem LLM).
2. Chama a busca híbrida (`SearchService.search`, `retrieval/search.py`) nessas coleções, com o nível da conversa: vetorial (cosseno) + textual, os dois braços filtrando `chunks.min_level` no SQL, fusão RRF, até 10 trechos. Um trecho entra se alcança `min_similarity` ou casa a busca textual (conjuntiva); pergunta sem relação volta vazia. Um trecho acima do nível nunca é candidato, então também nunca vira citação nem contexto.
3. Transforma cada trecho numa fonte (`retrieval/context.py`): o conteúdo é o corpo do trecho sem o cabeçalho `path:`/`symbol:`/`section:` usado no embedding (`chunks.meta.display`); o título é o caminho do arquivo ou o título do commit; a URI é `<caminho>#L<início>-L<fim>` (texto e código), `<caminho>` (documentos convertidos, sem linhas), `commit:<sha>` ou, num item de conhecimento de fonte `runner`, `knowledge:<chave>` (título do item, com a confiança e as evidências; [indexacao.md](indexacao.md#conhecimento-do-harness)) ou, num chamado de fonte `tickets`, `ticket:<external_id>` (título do chamado, com número, status, data e link, e uma linha `Chamado <número> · <status> · <data> · seção <Seção>` antes do conteúdo, só para o LLM; [chamados.md](chamados.md#no-chat)) ou, num card de fonte `cards` (v0.4), `card:<external_id>` (título do card, com número, tipo, status, sprint, data e link, e uma linha `Card <número> · <tipo> · <status> · sprint <nome> · <data> · seção <Seção>` antes do conteúdo; [cards.md](cards.md#no-chat)).
4. Corta pelo orçamento de contexto: as fontes ficam na ordem da busca e param na primeira que estouraria `MAX_CONTEXT_TOKENS` (6000 tokens estimados por 4 caracteres/token, o estimador da ingestão; trechos têm até 800 tokens, então cabem de 7 a 15, sobrando espaço num modelo de 16k para as regras, o histórico e a resposta). Uma primeira fonte maior que o orçamento é truncada, para nunca se perder um acerto pelo tamanho. A numeração `[n]` do prompt e das citações gravadas é a posição nessa lista.

Como os trechos chegam ao índice (parsing, chunking, embeddings) e os detalhes da busca híbrida estão em [indexacao.md](indexacao.md); a leitura das fontes, em [conectores.md](conectores.md).

Excluir uma coleção remove o vínculo (cascata); produto que ficou sem coleção volta a responder sempre "sem fonte". Falha do provedor de embedding sai como erro JSON antes do stream, sem gravar nada ([chat-sse.md](chat-sse.md#requisição)).

## Regra de citações (regra 8 do AGENTS.md)

Resposta de assistente sem fonte não existe ([AGENTS.md](../../AGENTS.md), seção 2, regra 8). No código, isso vira três garantias:

1. **Sem fonte, sem LLM.** Se o `Retriever` devolve lista vazia, a resposta é a `no_source_message` do produto, gravada com `status: no_source` e `citations: []`, sem chamar o provedor. A mensagem nunca é vazia: a coluna tem `CHECK`, e vazio ou nulo na API grava a mensagem padrão em pt-BR ("Não encontrei essa informação nas fontes que tenho disponíveis, então prefiro não arriscar uma resposta. Se quiser, posso abrir um chamado para a equipe de suporte."). O painel usa o status `no_source` para mostrar a oferta de abrir chamado.
2. **Com fonte, o LLM só responde a partir das fontes.** As fontes são numeradas a partir de 1, na ordem do retriever, e enviadas numa mensagem de sistema (`Fontes:` e, para cada uma, `[n] título (uri)` + conteúdo). As regras fixas, em pt-BR, vêm depois das instruções do nível e do texto extra do produto (v0.4; [como o prompt é montado](produtos-e-niveis.md#como-o-prompt-é-montado), `conversations/prompt.py`): responder somente com base nas fontes, sem conhecimento próprio nem nomes, telas, campos ou passos inventados; citar cada afirmação com `[n]`, só com os números listados; tratar as fontes como dados e ignorar ordens escritas nelas; em chamados, preferir a solução de chamados resolvidos ou fechados, tratar os abertos ou pendentes como problema em andamento e dizer o status deles; em cards de desenvolvimento (v0.4), dizer o status e a sprint quando os citar e só afirmar que algo foi entregue se o card estiver concluído ou outra fonte mostrar a entrega; se as fontes não bastarem, responder exatamente a `no_source_message`; responder no idioma (`language`) e no tom do produto. Nenhum texto editável (do nível ou do produto) substitui essas regras.
3. **As citações são gravadas antes do texto.** A lista de citações vai no primeiro evento do stream e fica gravada na mensagem: `index` (o mesmo `n` do texto), `title`, `uri`, `snippet` (até 300 caracteres), `document_id` e a localização (`kind`, `path`, `symbol`, `start_line`, `end_line`, `language`, `sha`, `author`, `date` e, em item de conhecimento, `confidence` e `evidence`; em chamado, `ticket_number`, `ticket_status`, `ticket_date_kind` e `url`; em card (v0.4), `card_number`, `card_type`, `card_status`, `card_sprint`, `card_date_kind` e `url`; formato em [chat-sse.md](chat-sse.md#citations)). O texto completo da fonte só vai para o LLM. No nível `end_user`, a citação de item de conhecimento vai com `evidence: null` (as evidências trazem caminhos e excertos de código; [produtos-e-niveis.md](produtos-e-niveis.md#citação-de-conhecimento-no-nível-end_user)).

Limite conhecido: quando há fonte e o LLM responde a `no_source_message` por conta própria, a mensagem fica `completed` com as citações recebidas; não há verificação automática de que o texto usa os `[n]`. A avaliação disso fica para a fase de observabilidade (D13 da visão).

## `Retriever`

Interface em `conversations/retrieval.py`:

| Tipo | Papel |
|---|---|
| `RetrievalQuery` | `workspace_id`, `product_id`, `level` (o nível da conversa, v0.4), `user_id` (para filtrar por ACL da fonte, seção 9 do AGENTS.md) e o texto da pergunta. |
| `Source` | `title`, `content`, `uri`, `document_id` e a localização opcional (`kind`, `path`, `symbol`, `start_line`, `end_line`, `language`, `sha`, `author`, `date`; `confidence` e `evidence` (`EvidenceRef`) em item de conhecimento; `ticket_number`, `ticket_status`, `ticket_date_kind`, `url` e `context_line` (só para o LLM) em chamado; `card_number`, `card_type`, `card_status`, `card_sprint`, `card_date_kind`, `url` e `context_line` em card). |
| `Retriever` (`Protocol`) | `async retrieve(db, query) -> Sequence[Source]`: fontes da pergunta, da melhor para a pior; vazia quando nada é relevante. `db` é a sessão do chamador, com o escopo de RLS do workspace. |
| `HybridRetriever` | Implementação de produção (`retrieval/retriever.py`, seção anterior), montada em `api/deps.py:get_retriever`; os testes trocam por um retriever fixo. |

O reranker (seção 7.4 da visão) entra depois dentro do `HybridRetriever`, sem mudar o motor do chat.

**Quando a busca roda.** A busca vetoriza a pergunta pela rede (dezenas a centenas de milissegundos). Ela roda na fase 1, na sessão da requisição, **depois** das checagens de acesso (dono, produto ativo, nível configurado e dentro do máximo atual: ninguém sem acesso dispara embedding) e **antes** de travar a conversa com `FOR UPDATE`, para perguntas simultâneas na mesma conversa não esperarem a chamada de rede uma da outra. A conexão da requisição fica ocupada durante o embedding, porque a transação do `WorkspaceContext` já está aberta desde a checagem de membership; tirá-la dali exigiria abrir a transação depois da autenticação em todas as rotas, e o custo (uma chamada curta, limitada pelo timeout do provedor) é pequeno perto da geração do LLM, que continua fora de qualquer transação.

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
    A->>DB: fase 1: confere acesso
    A->>R: retrieve(pergunta)
    R-->>A: fontes
    A->>DB: trava a conversa, grava a pergunta
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
   - lê a conversa e exige que quem pergunta seja o dono, produto ativo (409 `product_inactive`; até a v0.3, `assistant_inactive`), nível com modelo no workspace (409 `level_not_configured`) e nível da conversa até o máximo **atual** de quem pergunta, pessoa ou chave (403 `level_not_allowed`; [produtos-e-niveis.md](produtos-e-niveis.md#chat-com-produto-e-nível));
   - chama o retriever (ver "Quando a busca roda");
   - trava a conversa com `FOR UPDATE` (serializa perguntas simultâneas e garante `position` única);
   - grava `interrupted` em respostas `streaming` órfãs da conversa (ver abaixo);
   - lê o histórico, define o título da conversa na primeira pergunta (a pergunta numa linha, até 80 caracteres, sem LLM) e grava a pergunta;
   - sem fonte: grava a resposta final `no_source`; com fonte: grava um marcador `streaming` com as citações e o modelo do nível, e prepara a chamada ao LLM (a chave é decifrada só em memória).
   Por isso, erros de acesso e de estado saem como JSON comum, antes do stream ([chat-sse.md](chat-sse.md#requisição)).
2. **`stream` (fase 2)**: emite `citations`, repassa cada pedaço do provedor como `delta` e, no fim, grava o desfecho num `scoped_session` novo e curto: `completed` com tokens, custo estimado e latência, `failed` com o `error_code`, ou `interrupted` com o conteúdo parcial se o cliente desconectou. A gravação final roda protegida contra cancelamento e só altera mensagem ainda `streaming`, então acontece uma vez só (uma conversa excluída no meio não casa com nada).
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

## Custo e canal por resposta

Desde a v0.3 (D4 e D7 do [plano 0008](../planos/0008-telas-de-uso-e-administracao.md)), cada mensagem grava:

- **`channel`**: `panel` (painel), `api` (API pública, REST própria ou compatível com OpenAI; [api-publica.md](api-publica.md)), `mcp` (ferramenta `ask` do MCP, v0.5; [mcp.md](mcp.md)) ou `widget` (widget embutível, v0.5; [widget.md](widget.md)). Pergunta e resposta levam o canal da requisição. É o mesmo `channel` da conversa, repetido na mensagem para as agregações de [uso-e-custos.md](uso-e-custos.md) não precisarem do join e para canais futuros. Mensagens gravadas antes da migração ficam `panel`.
- **`cost_usd`**: custo estimado da resposta, pela tabela de preços de chat (`ChatPriceTable`, [uso-e-custos.md](uso-e-custos.md#preços-do-chat)) aplicada a `model`, `input_tokens` e `output_tokens`, com 6 casas. É gravado junto com o desfecho (`completed`, `failed`, `interrupted`), quando o provedor informou os tokens. É `null` em perguntas, em `no_source` (sem LLM), quando o modelo não tem preço ou quando faltam tokens. Nunca zero por desconhecimento.
- **`product_id` e `level`** (v0.4): o produto e o nível da conversa, repetidos na mensagem pelo mesmo motivo do `channel` ([uso-e-custos.md](uso-e-custos.md) agrupa e filtra por eles). Pergunta e resposta levam os mesmos valores.

O evento `done` traz `cost_usd` ([chat-sse.md](chat-sse.md#done)); a leitura da conversa traz `cost_usd` e `channel` em cada mensagem. Mudar a tabela de preços não recalcula respostas antigas.

## Histórico enviado ao LLM

Com fonte, o LLM recebe, nesta ordem: as instruções (texto do nível + texto do produto + regras fixas), as fontes numeradas, o histórico e a pergunta nova. O histórico são as **10 mensagens mais recentes** da conversa (`DEFAULT_HISTORY_WINDOW`), das mais antigas para as mais novas, contando os dois papéis: todas as perguntas e só as respostas `completed` ou `no_source` (respostas `failed`, `interrupted` e `streaming` ficam de fora). A pergunta atual não conta na janela. Credencial, modelo e temperatura são os do nível da conversa no workspace (v0.4).

Na rota compatível com OpenAI (`/v1/chat/completions`), o histórico não vem do banco: são as mensagens `user` e `assistant` enviadas pelo cliente antes da pergunta, com a mesma janela de 10, e só a pergunta e a resposta são gravadas ([api-publica.md](api-publica.md#post-v1chatcompletions)).

## Acesso e privacidade

A RLS isola o workspace; dentro dele, as regras são da aplicação (`Reader` em `conversations/service.py`):

| Ação | Quem pode |
|---|---|
| Criar conversa | Qualquer membro (inclusive leitor), com produto ativo do workspace, num nível até o próprio máximo no produto (v0.4; sem `level`, o máximo). Pela API pública, uma chave com o produto no escopo, num nível até o `max_level` dela; a conversa é da chave (`api_key_id`, `user_id` nulo) e só ela a lê e continua ([api-publica.md](api-publica.md#conversas-da-api)); pelo MCP (v0.5), a mesma regra, com `channel = mcp`, e cada canal só lê as suas ([mcp.md](mcp.md#conversas-uso-e-custos)). Pelo widget (v0.5), o visitante de um widget ativo, sempre no nível `end_user`; a conversa é do widget (`widget_id`, `user_id` e `api_key_id` nulos) e só o token de conversa `kbv_` a lê e continua ([widget.md](widget.md#token-de-conversa-kbv_)). |
| Listar "minhas conversas" | Cada um vê só as próprias, da mais recente para a mais antiga. |
| Ler uma conversa | O dono, e owner/admin do workspace. Os demais recebem 404. |
| Enviar mensagem, excluir conversa | Só o dono; enviar exige também o nível da conversa até o máximo atual do dono (403 `level_not_allowed`). Owner/admin que leem a conversa de outro recebem 403 `forbidden`. A exclusão é auditada (`conversation.deleted`, sem conteúdo). |
| Avaliar resposta | Quem pode ler a conversa. |

Matriz completa em [autenticacao.md](autenticacao.md#matriz-de-permissões).

## Feedback

`POST .../conversations/{conversation_id}/messages/{message_id}/feedback` com `{"rating": "up" | "down", "comment": "..."}` (comentário opcional, até 2000 caracteres). Um feedback por mensagem e usuário: enviar de novo substitui (upsert). Só mensagens do assistente aceitam feedback (422 `feedback_target_invalid`). Na leitura da conversa (`GET .../conversations/{id}`), cada mensagem traz o feedback de quem está lendo. No widget (v0.5), o visitante avalia pela rota pública, com o feedback gravado sem usuário (`user_id` nulo), um por mensagem ([widget.md](widget.md#post-conversationsconversation_idmessagesmessage_idfeedback)).

## Visão administrativa

Owner e admin do workspace têm rotas próprias em `/v1/workspaces/{workspace_id}/admin/conversations` (tela **Conversas** do painel):

- `GET ""`: conversas de todos os membros e das chaves de API, da mais recente para a mais antiga, com nome do usuário (ou, desde a v0.3, `channel`, `api_key_id` e `api_key_name` nas conversas da API, com usuário nulo), o produto (`product_id`, `product_name`) e o nível (`level`) (v0.4; até a v0.3, `assistant_id` e `assistant_name`), contagem de mensagens, de 👍 e de 👎 e data da última mensagem. Filtros: `product_id` e `level` (v0.4, no lugar de `assistant_id`, que passa a dar 422), `user_id`, `channel` (v0.3), `api_key_id` (v0.3), período de criação semiaberto `[created_from, created_to)` (UTC; início maior ou igual ao fim dá 422) e `negative_feedback=true` (só conversas com ao menos um 👎). Paginada (`limit`/`offset`, `total`).
- `GET /stats`: totais do período (padrão: os 30 dias anteriores ao relógio do servidor): conversas (pela data de criação), mensagens, 👍, 👎 e respostas `no_source`, `failed` e `interrupted` (pela data da mensagem).
- `GET /{conversation_id}`: a conversa com as mensagens paginadas e o feedback de todos, com quem deu. Vale também para a conversa da API, com os mesmos campos da lista (usuário nulo, `api_key_id` e `api_key_name`); a chave revogada continua com o nome.

Na lista e no detalhe, `user_id`, `user_name` e `user_email` são nulos na conversa da API, e `api_key_id` e `api_key_name` são nulos na do painel. `channel` aceita `panel` ou `api` (outro valor: 422). O painel mostra a conversa da API como "API · <nome da chave>" no lugar do usuário e tem o filtro **Canal** (Painel, API).

**Canais `mcp` e `widget`** (v0.5):

- A lista e o detalhe trazem também `widget_id`, `widget_name` e `visitor` (`{name, email, external_id}` da identidade assinada, ou `null`): preenchidos só na conversa do widget. A conversa do MCP tem `api_key_id` e `api_key_name`, como a da API.
- `channel` aceita `panel`, `api`, `mcp` e `widget` (outro valor: 422); filtro novo `widget_id`. O filtro `api_key_id` casa as conversas da chave nos canais `api` e `mcp`.
- O painel mostra "MCP · <nome da chave>" e "Widget · <nome do widget>" no lugar do usuário, com o nome e o e-mail do visitante quando a identidade é assinada (senão, "Visitante"); o filtro **Canal** ganha MCP e Widget, e há o filtro **Widget**.
- O feedback do visitante (`feedback.user_id` nulo) conta nos 👍 e 👎 e aparece no detalhe como "Visitante". O pedido de chamado aparece na mensagem, como no painel.
- `GET /stats` conta todos os canais.

As consultas usam número constante de statements, independente do tamanho da página (há teste que conta). A visão é só leitura: o admin não envia mensagens nem exclui conversas de outros.

## Listagem e duplicação de produtos

Desde a v0.4, as rotas são as de produtos, `/v1/workspaces/{workspace_id}/products` (`api/products.py`, serviço em `products/`), com o contrato completo em [produtos-e-niveis.md](produtos-e-niveis.md#rotas); as de assistentes saíram ([compatibilidade](produtos-e-niveis.md#compatibilidade-das-rotas-antigas)). Papéis na [matriz](autenticacao.md#matriz-de-permissões).

**`GET ""`** é paginada (`limit` padrão 50, máximo 200; `offset`; `total`):

| Parâmetro | Efeito |
|---|---|
| `query` | Até 200 caracteres; casa nome ou descrição, sem diferenciar maiúsculas (`ILIKE` com `%`, `_` e `\` escapados). Até a v0.3, também o modelo, que saiu do produto. |
| `active` | `true` ou `false`. Leitor só vê ativos de qualquer forma. |
| `collection_id` | Produtos ligados a essa coleção. |
| `sort` | `name` (padrão), `-name`, `created_at`, `-created_at`, `updated_at`, `-updated_at`. Empate pelo `id`. Valor fora da lista: 422 `validation_error`. |

O filtro `provider_id` da v0.3 saiu (a credencial é do nível). Número constante de statements (página, coleções de cada item e `my_max_level` de quem lê).

### Duplicação de produtos

**`POST /{product_id}/duplicate`** (editor ou acima, CSRF): cria um produto novo com a configuração do original (descrição, texto extra de instruções, idioma, tom, mensagem de "sem fonte", similaridade mínima, ativo e as mesmas coleções). Corpo opcional `{"name": "..."}`; sem ele, o nome é `<nome> (cópia)` e, se já existir, `<nome> (cópia 2)`, `(cópia 3)`..., cortando o nome original para caber em 200 caracteres. O webhook de chamados copia só a URL: o segredo não é copiado, então o novo produto fica com `ticket_webhook_configured = false` até gerar o seu. Conversas, feedback e níveis gravados dos membros não são copiados (no produto novo vale o padrão do papel). Resposta 201 `ProductOut`. Erros: 404 `not_found` (original inexistente ou, para leitor, inativo), 409 `product_name_taken` (só com `name` explícito já usado), 422 `product_name_invalid`. Auditoria: `product.created` com `name`, `collection_ids` e `duplicated_from` (id do original).

### Listagem de provedores

`GET /v1/workspaces/{workspace_id}/providers` (editor ou acima; `api/providers.py`) continua paginada e, desde a v0.3, aceita `query` (nome, até 200 caracteres, sem diferenciar maiúsculas, com `%`, `_` e `\` escapados), `kind` (`openai`, `anthropic`, `openrouter`, `fake`) e `sort` (`name` (padrão), `-name`, `created_at`, `-created_at`, `updated_at`, `-updated_at`). Empate pelo `id`; valor fora da lista: 422 `validation_error`. A chave continua só mascarada (`key_hint`).

## Referências

- Server-Sent Events: <https://html.spec.whatwg.org/multipage/server-sent-events.html>
