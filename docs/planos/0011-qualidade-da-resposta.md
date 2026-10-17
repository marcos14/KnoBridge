---
id: 0011
titulo: Qualidade da resposta — busca em várias etapas, reranker self-host, limiar por modelo, aviso de arquivos gerados e conjunto de avaliação
slug: qualidade-da-resposta
solicitado_por: usuario
criado_em: 2026-10-17
atualizado_em: 2026-10-17
status: em_execucao
aprovado_em: 2026-10-17
aprovado_por: usuario
concluido_em: null
branch: plano/0011-qualidade-da-resposta
fases:
  - id: F1
    titulo: Contrato
    status: concluida
    subfases:
      - id: F1.1
        titulo: ADR e specs da busca em etapas, do reranker, do limiar por modelo, do aviso de arquivos gerados e da avaliação
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-17
        concluida_em: 2026-10-17
        commit: feb0eb2
  - id: F2
    titulo: Backend
    status: concluida
    subfases:
      - id: F2.1
        titulo: Reranker self-host (TEI com bge-reranker-v2-m3) no compose, cliente e opção por produto
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-17
        concluida_em: 2026-10-17
        commit: 43de0ff
      - id: F2.2
        titulo: Chamada de ferramentas nos provedores de LLM (OpenAI, Anthropic, OpenRouter e fake)
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-17
        concluida_em: 2026-10-17
        commit: 881b200
      - id: F2.3
        titulo: Rodada de chat em várias etapas em todos os canais, com limite por nível
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-17
        concluida_em: 2026-10-17
        commit: aee61a7
      - id: F2.4
        titulo: Limiar de similaridade por modelo de embedding e aviso de arquivos gerados
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-17
        concluida_em: 2026-10-17
        commit: b070873
  - id: F3
    titulo: Painel
    status: em_execucao
    subfases:
      - id: F3.1
        titulo: Etapas nos níveis, reordenação no produto, etapas visíveis no chat e aviso nas fontes
        status: em_execucao
        agente: claude-code-worktree
        iniciada_em: 2026-10-17
        concluida_em: null
        commit: null
  - id: F4
    titulo: Avaliação e validação
    status: em_execucao
    subfases:
      - id: F4.1
        titulo: Conjunto de avaliação sintético com gabarito e roteiro contra a stack
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-17
        concluida_em: 2026-10-17
        commit: null
      - id: F4.2
        titulo: E2E da stack, guias e documentação
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.3
        titulo: Ensaio no Minski contra a linha de base dos ensaios 0005 e 0006
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes:
  - id: D1
    data: 2026-10-17
    por: usuario
    decisao: o reranker é só self-host, o bge-reranker-v2-m3 da visão, sem provedor externo neste bloco
    motivo: escolha do usuário; segue a tabela de stack da visão (seção 9)
    alternativas: self-host com provedor externo opcional (Cohere ou Jina); só externo
    adr: null
  - id: D2
    data: 2026-10-17
    por: usuario
    decisao: o contêiner do reranker sobe sempre com o compose (dev e produção)
    motivo: escolha do usuário; a qualidade melhor vale o download do modelo e a memória
    alternativas: perfil opcional do compose
    adr: null
  - id: D3
    data: 2026-10-17
    por: usuario
    decisao: a reordenação é uma opção por produto, ligada por padrão quando a instância tem reranker; sem reranker, desabilitada e a busca segue como hoje
    motivo: escolha do usuário
    alternativas: só na instância
    adr: null
  - id: D4
    data: 2026-10-17
    por: usuario
    decisao: busca em várias etapas com o modelo do nível chamando uma ferramenta de busca, máximo de etapas configurável por nível (padrão Usuário final 2, Suporte 3, Desenvolvimento e produto 4), filtro de nível em cada busca e custo e etapas registrados por resposta
    motivo: o ensaio 0006 mostrou o Claude Code resolvendo pelo MCP, com até quatro buscas, o que a busca única do ask não resolve
    alternativas: etapa fixa de reformulação
    adr: null
  - id: D5
    data: 2026-10-17
    por: usuario
    decisao: conjunto de avaliação sintético com gabarito no repositório, rodado sob demanda contra a stack com LLM real; as perguntas do Minski seguem fora do repositório, para os ensaios
    motivo: medir o antes e o depois de cada mudança sem dados de terceiros no repositório (regra 9)
    alternativas: só sintético; só Minski
    adr: null
  - id: D6
    data: 2026-10-17
    por: usuario
    decisao: entram o limiar de similaridade por modelo de embedding, o aviso de arquivos gerados que dominam o índice e a busca em etapas em todos os canais que respondem (painel, REST, API compatível com OpenAI, ask do MCP e widget)
    motivo: escolha do usuário
    alternativas: deixar os itens menores para depois
    adr: null
  - id: D7
    data: 2026-10-17
    por: agente
    decisao: "decisões técnicas a confirmar no ADR da F1.1: reranker pelo Text Embeddings Inference (imagem CPU da Hugging Face) com o modelo baixado num volume, cliente HTTP atrás do Protocol Reranker que já existe em retrieval/rerank.py, aplicado aos top-30 depois da fusão; o E2E da CI troca o contêiner por um reranker falso numa camada do compose, sem baixar o modelo; modelo sem chamada de ferramentas (ou o provedor fake sem roteiro) cai na busca única de hoje; a busca da ferramenta respeita o nível da conversa no SQL, como a busca inicial"
    motivo: reaproveitar a interface existente e manter a CI leve e determinística
    alternativas: modelo carregado no processo da API (sentence-transformers); reranker real no E2E
    adr: docs/adr/0010-busca-em-etapas-e-reranker.md
  - id: D8
    data: 2026-10-17
    por: agente
    decisao: "F1.1 (ADR 0010): TEI cpu-1.9.4 com BAAI/bge-reranker-v2-m3 (volume reranker-models, 4g), POST /rerank com os 30 melhores depois da fusão e devolve 10, timeout 10 s e queda para a ordem do RRF; products.rerank padrão true, vale na busca inicial, em cada etapa, no search_knowledge e no Testar busca; etapa 1 = busca de hoje, as seguintes pela ferramenta interna search_sources {query}, max_steps 1 a 6 (2/3/4), última rodada com tool_choice none, até 3000 tokens e 30 fontes, citações acumuladas sem repetir; modelo sem ferramentas: ToolsUnsupportedError, refaz sem ferramentas e marca tools_unsupported_model no nível; min_similarity nulo = padrão do modelo (0,35 OpenAI, 0,60 gemini-embedding-001, 0,57 gemini-embedding-2), produtos com exatamente 0,35 passam a nulo; aviso de arquivos dominantes em sources.index_stats ao fim de execução bem-sucedida; migrações 0022 (F2.1), 0023 (F2.3) e 0024 (F2.4); E2E com scripts/fake_reranker.py"
    motivo: "contrato implementável"
    alternativas: "migração única; reranker só na busca inicial"
    adr: null
  - id: D9
    data: 2026-10-17
    por: agente
    decisao: "ordem das migrações conforme a integração: F2.1 = 0022, F2.4 = 0023, F2.3 = 0024 (a F2.3 roda depois da F2.1 e da F2.4); cada agente ajusta os números nas specs"
    motivo: "F2.1, F2.2 e F2.4 em paralelo"
    alternativas: "esperar para numerar"
    adr: null
  - id: D10
    data: 2026-10-17
    por: usuario
    decisao: "com a busca inicial sem nenhuma fonte, o modelo do nível é chamado para reformular e buscar de novo antes do não sei, em todos os canais (inclusive o widget); a resposta sem fonte passa a ter custo de LLM e entra em Uso e custos (regra 8: sem fonte, nenhum texto do LLM)"
    motivo: "pode achar o que a primeira formulação perdeu"
    alternativas: "manter não sei imediato sem LLM; reformular só fora do widget"
    adr: null
  - id: D11
    data: 2026-10-17
    por: usuario
    decisao: "produtos com similaridade mínima exatamente 0,35 passam a seguir o padrão do modelo de embedding da coleção (nulo); valores ajustados à mão ficam"
    motivo: "quem nunca mexeu ganha o valor certo para o modelo (ensaio 0004)"
    alternativas: "manter 0,35 nos existentes"
    adr: null
  - id: D12
    data: 2026-10-17
    por: agente
    decisao: "F2.2: ToolChoice como Literal (auto, required, none); OpenAI envia tools sem strict, tool_choice e parallel_tool_calls=false só com ferramentas e abre nova chamada por index ou por id novo (backends do OpenRouter mandam tudo no index 0); Anthropic com input_schema e disable_parallel_tool_use, resultados consecutivos num turno user; ToolsUnsupportedError pelos dois adaptadores via tools_refused, só quando havia ferramentas; o fake roteirizado avança um passo por chamada e ToolCallStep chama a ferramenta mesmo com tool_choice none; os adaptadores não somam custo (cada chamada termina no seu ChatUsage e a rodada soma na F2.3); um assert de tipo em conversations/chat.py até a F2.3 reescrever o laço"
    motivo: "spec chat.md conferida contra os SDKs fixados"
    alternativas: "enum; somar custo no adaptador"
    adr: null
  - id: D13
    data: 2026-10-17
    por: agente
    decisao: "F2.1: HttpReranker valida a resposta do TEI (um item por texto, índices distintos, score finito) e ordena por score com empate pela ordem do RRF; disponibilidade = KNOBRIDGE_RERANKER_URL definida (sem checagem de saúde por busca; a saúde fica em /v1/admin/health com o status novo disabled); Testar busca com rerank nulo = ligado se disponível e true sem reranker = 422 reranker_unavailable; serviço reranker com TEI cpu-1.9.4 e revisão do modelo fixada (953dc6f), mem_limit 4g, healthcheck por curl com start_period 15 min, api e worker não dependem dele; KNOBRIDGE_RERANKER_URL vazia no .env desliga; camada E2E com scripts/fake_reranker.py em python alpine"
    motivo: "spec indexacao.md"
    alternativas: "checar saúde a cada busca"
    adr: null
  - id: D14
    data: 2026-10-17
    por: agente
    decisao: "F2.4: limiar efetivo resolvido por grupo (credencial, modelo) em cada busca, número explícito vale para todos; KNOBRIDGE_MIN_SIMILARITY_DEFAULTS sobrescreve a tabela (source model) e modelo fora dela usa o fallback 0,35; PATCH com null volta ao padrão do modelo (campo omitido mantém); uma consulta a mais por página de produtos para effective_min_similarity; suggested_exclude_globs recalculado na resposta contra os exclude_globs atuais; migração 0023 troca 0,35 por nulo e o downgrade devolve 0,35"
    motivo: "spec indexacao.md e D11"
    alternativas: "limiar único por produto"
    adr: null
  - id: D15
    data: 2026-10-17
    por: agente
    decisao: "na rodada em etapas, uma chamada ao LLM que falha ou é cortada deixa tokens e custo da resposta nulos (desconhecidos); a chamada recusada com ToolsUnsupportedError não entra na soma"
    motivo: "um total parcial pareceria exato e subestimaria o custo; a recusa não gera cobrança"
    alternativas: "somar só as chamadas com uso conhecido; estimar a chamada falha"
    adr: null
  - id: D16
    data: 2026-10-17
    por: agente
    decisao: "a queda para a busca única por ToolsUnsupportedError só vale na primeira rodada, antes de qualquer saída, e grava a marca tools_unsupported_model só se o modelo ainda for o do nível; recusa numa rodada posterior falha a resposta com provider_tools_unsupported"
    motivo: "depois de texto ou de uma busca já emitidos ao cliente, recomeçar sem ferramentas duplicaria a saída; a condição evita marcar um modelo trocado no meio da rodada"
    alternativas: "cair para a busca única em qualquer rodada; não gravar marca"
    adr: null
  - id: D17
    data: 2026-10-17
    por: agente
    decisao: "lista de fontes cheia (30) responde 'limite atingido' sem buscar e sem contar etapa; chamada de ferramenta sem argumentos completos termina em chat_failed; rodada só com espaços conta como resposta final em branco"
    motivo: "casos de borda determinísticos, cobertos por teste, sem laço infinito nem custo sem fonte nova"
    alternativas: "buscar mesmo com a lista cheia; ignorar a chamada incompleta"
    adr: null
  - id: D18
    data: 2026-10-17
    por: agente
    decisao: "na API compatível com OpenAI em streaming, a resposta HTTP só começa no primeiro evento que não é step, para um erro do provedor numa etapa de busca voltar como erro JSON com o status certo"
    motivo: "depois do primeiro chunk o status 200 já foi enviado e o cliente oficial não distingue o erro"
    alternativas: "começar o stream na hora e mandar o erro como chunk"
    adr: null
  - id: D19
    data: 2026-10-17
    por: agente
    decisao: "Uso e custos ganha chat_searches como sexta coluna (0 do lado de embeddings), logo depois de answers no CSV e também nos totais do painel da instância; estimated_max_cost_per_answer_usd soma os tokens de todas as chamadas do máximo de etapas"
    motivo: "o custo extra das etapas precisa ficar visível onde o custo já é lido"
    alternativas: "contar buscas só no detalhe da conversa"
    adr: null
  - id: D20
    data: 2026-10-17
    por: agente
    decisao: "o conjunto de avaliação fica em scripts/eval/ com o corpus em fixtures/corpus/ (pasta só de dados, sem AGENTS.md que seria indexado), fontes eval-<rótulo>-<pasta>, credencial fake com chave de marcador, CLI que recusa opções com cara de segredo e compare recalculado sobre as perguntas em comum; os JSON de gerado/ têm cerca de 100 trechos cada para a fonte de código passar de 200 trechos e o aviso de arquivos dominantes disparar"
    motivo: "o verificador só isenta pastas fixtures; nomes de fonte são únicos no workspace; abaixo de 200 trechos nada domina (indexacao.md), o que a primeira execução contra a stack mostrou"
    alternativas: "corpus em scripts/eval/corpus/; JSON pequenos sem o aviso"
    adr: null
  - id: D21
    data: 2026-10-17
    por: agente
    decisao: "o serviço reranker roda com --max-batch-tokens 2048"
    motivo: "com o modelo real o TEI aquecia no máximo de 8.192 tokens, passava dos 4 GB e era morto por falta de memória em laço; os textos enviados têm até 2.000 caracteres; o E2E usa o reranker falso e não pegou o defeito"
    alternativas: "subir mem_limit para 8 GB ou mais; desligar o aquecimento"
    adr: null
  - id: D22
    data: 2026-10-17
    por: agente
    decisao: "o endereço fixo do painel na rede do compose passa de .10 para .250"
    motivo: "com o reranker a stack passou de nove contêineres e o Docker pode dar o .10 a outro serviço (Address already in use)"
    alternativas: "ip_range para os dinâmicos, que exigiria uma segunda variável ao trocar a sub-rede"
    adr: null
pendencias_usuario: []
---

# Plano 0011 — Qualidade da resposta

## 1. Pedido original

> Gostei, pode implementar

O pedido aprova o bloco proposto na conversa, **qualidade da resposta**, que tem cinco partes:
- busca em várias etapas no chat;
- reranker;
- similaridade mínima por modelo de embedding;
- aviso de arquivos gerados dominando o índice;
- conjunto de avaliação reproduzível.

O critério de sucesso combinado: no Minski, o `ask` sai de 7 de 9 para perto do 9 de 9 do modo `search_knowledge`, e o Suporte passa a montar a consulta SQL. O custo por resposta é medido por nível.

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | Como o reranker roda? | Só self-host. | 2026-10-17 |
| 2 | Como funciona a busca em várias etapas? | O modelo do nível chama uma ferramenta de busca, com o máximo de etapas por nível. | 2026-10-17 |
| 3 | Onde fica o conjunto de avaliação? | Sintético no repositório; o Minski fora dele. | 2026-10-17 |
| 4 | Que itens menores entram? | Limiar por modelo, aviso de arquivos gerados e busca em etapas em todos os canais. | 2026-10-17 |
| 5 | O contêiner do reranker sobe por padrão? | Sempre ligado. | 2026-10-17 |
| 6 | Onde se liga o reranker? | Por produto, ligado por padrão quando disponível. | 2026-10-17 |

O que a visão já decidia: busca híbrida, depois reranker, depois contexto (seções 6 e 7.4). Reranker cross-encoder nos top-30, com o bge-reranker-v2-m3 self-host como padrão. Modelos plugáveis atrás de interfaces. O `Protocol Reranker` já existe em `backend/src/knobridge/retrieval/rerank.py`, sem uso.

**Será feito**:
- **Reranker self-host** no compose, sempre ligado (bge-reranker-v2-m3), aplicado aos top-30 depois da fusão. É uma opção por produto.
- **Chamada de ferramentas** nos provedores de LLM.
- **Rodada de chat em várias etapas**: o modelo do nível reformula e busca de novo antes de dizer "não sei".
  - Vale em todos os canais que respondem.
  - Tem limite de etapas por nível, configurável em Níveis de resposta.
  - Etapas e custo ficam visíveis.
- **Limiar de similaridade com padrão por modelo** de embedding.
- **Aviso de arquivos gerados** que dominam o índice de uma fonte.
- **Conjunto de avaliação sintético** com gabarito e roteiro contra a stack.
- **E2E, guias e um ensaio no Minski** contra a linha de base dos ensaios 0005 e 0006.

**Fica de fora**: provedor externo de reranker; GPU; avaliação automática na CI com LLM real (é da Fase 3); mudança do modelo de embedding padrão.

## 3. Critérios de aceite

- [ ] Com o reranker ligado no produto, os trechos chegam ao contexto reordenados pelo cross-encoder.
  - Sem reranker na instância, ou com a opção desligada, a busca é a de hoje.
  - O E2E roda sem baixar o modelo.
- [ ] O modelo do nível pode buscar de novo até o máximo de etapas do nível.
  - Cada busca respeita o nível no SQL, provado por teste em que um trecho acima do nível nunca chega ao contexto em nenhuma etapa.
  - O máximo vem da configuração do nível.
  - Etapas e custo ficam gravados na resposta.
- [ ] A busca em etapas vale no painel, na REST, na API compatível com OpenAI, no `ask` do MCP e no widget. Um modelo sem chamada de ferramentas cai na busca única.
- [ ] Coleções com Gemini e com OpenAI ganham limiares padrão diferentes. A fonte mostra os arquivos que dominam o índice, com a sugestão de exclusão.
- [ ] O conjunto de avaliação roda com um comando contra a stack e gera um relatório com acertos, fontes, etapas, custo e tempo.
- [ ] No Minski, o relatório do ensaio compara com a linha de base (0005 e 0006), por nível e com o gasto. A cobertura fica em 95% ou mais.

## 4. Fases e subfases

Convenções para todas as subfases:
- **Idioma:** código em inglês, docs em pt-BR.
- **Regras:** valem as regras 1 a 10 do `AGENTS.md` raiz. A suíte padrão não chama LLM, embeddings, reranker nem rede externa: tudo passa por fakes atrás das interfaces.
- **`AGENTS.md` protegidos:** os agentes não editam `backend/AGENTS.md`, `backend/src/knobridge/AGENTS.md` nem o `AGENTS.md` raiz; relatam o texto e o orquestrador insere. A exceção é a F4.2, que edita o raiz.
- **Ordem das suítes:** backend, frontend, widget e E2E rodam um de cada vez.
- **Branch:** antes de cada commit, o orquestrador confere que está na branch do plano.

### F1 — Contrato

#### F1.1 — ADR e specs da busca em etapas, do reranker, do limiar por modelo, do aviso de arquivos gerados e da avaliação

- **Objetivo**: fechar o contrato antes do código.
- **Entregáveis**:
  - **ADR:** `docs/adr/0010-busca-em-etapas-e-reranker.md`, com D1 a D7.
  - **`chat.md` e `chat-sse.md`:** a rodada em etapas, com a ferramenta de busca, o máximo por nível, o que conta como etapa, o evento SSE de etapa (a consulta reformulada, sem conteúdo dos trechos), etapas e custo no `done` e na mensagem, e o fallback sem chamada de ferramentas.
  - **`produtos-e-niveis.md`:** máximo de etapas no nível e opção de reordenar no produto.
  - **`indexacao.md`:** reranker, limiar por modelo e aviso de arquivos gerados com os critérios.
  - **Canais:** `api-publica.md`, `mcp.md` e `widget.md`, com etapas nos canais e o que o visitante vê.
  - **`uso-e-custos.md`:** custo das etapas e do reranker.
  - **`modelo-de-dados.md`:** colunas novas e migração prevista `0022`.
  - **`docs/specs/avaliacao.md`:** formato do conjunto sintético, gabarito, métricas e relatório.
  - **Configuração:** variáveis de ambiente do reranker.
- **Contexto necessário**:
  - visão (seções 6, 7.4, 9 e 12);
  - ADRs 0004, 0008 e 0009;
  - as specs citadas;
  - `docs/pesquisa/0004`, `0005` e `0006`;
  - `backend/src/knobridge/retrieval/rerank.py`, `retrieval/search.py`, `conversations/chat.py` e `llm/provider.py`, só para ancorar.
- **Critérios de aceite**: specs implementáveis sem perguntas pelas subfases seguintes.
- **Depende de**: nenhuma.
- **Tamanho**: médio.

### F2 — Backend

#### F2.1 — Reranker self-host (TEI com bge-reranker-v2-m3) no compose, cliente e opção por produto

- **Entregáveis**:
  - serviço `reranker` no `docker-compose.yml`, com volume do modelo e healthcheck, e a camada do E2E trocando por um reranker falso;
  - settings e `.env.example`;
  - cliente HTTP atrás do `Reranker`, com timeout e queda para a ordem original em falha (registrada em log, sem derrubar a resposta);
  - aplicação aos top-30 depois da fusão quando o produto tem a opção ligada e a instância tem reranker;
  - migração `0022` com o que a spec atribuir a esta subfase (por exemplo `products.rerank`);
  - "Testar busca" com a opção;
  - testes com reranker fake e um teste de contrato do cliente contra um servidor HTTP falso.
- **Contexto necessário**:
  - `docs/specs/indexacao.md` e `chat.md`;
  - ADR 0010;
  - AGENTS de `retrieval/`, `products/`, `api/`, `migrations/` e `deploy/`;
  - `docker-compose.yml` e `docker-compose.e2e.yml`.
- **Critérios de aceite**:
  - ordem trocada pelo reranker fake;
  - falha do reranker não derruba a resposta;
  - opção desligada mantém a ordem;
  - isolamento;
  - `docker compose config` válido nas duas camadas.
- **Depende de**: F1.1.
- **Tamanho**: médio.

#### F2.2 — Chamada de ferramentas nos provedores de LLM

- **Entregáveis**:
  - extensão da interface `LLMProvider` com ferramentas (definição, chamada, resultado) e streaming;
  - adaptadores OpenAI (que também cobre o OpenRouter) e Anthropic pelos SDKs oficiais;
  - o provedor fake com roteiro de chamadas para os testes;
  - custo somado por chamada;
  - aviso claro quando o modelo não suporta ferramentas.
- **Contexto necessário**:
  - `docs/specs/chat.md` (seção da rodada em etapas);
  - ADR 0010;
  - AGENTS de `llm/`;
  - `llm/provider.py`, `openai_adapter.py`, `anthropic_adapter.py` e `fake.py`.
- **Critérios de aceite**: testes de cada adaptador com o transporte HTTP falso dos SDKs (sem rede); o fake roteirizável; nada muda para quem não usa ferramentas.
- **Depende de**: F1.1.
- **Tamanho**: médio.

#### F2.3 — Rodada de chat em várias etapas em todos os canais, com limite por nível

- **Entregáveis**:
  - o laço da rodada em `conversations/`: busca inicial, ferramenta de busca com o nível da conversa, máximo de etapas do nível, citações acumuladas e numeradas, e regra 8 mantida;
  - o evento SSE de etapa;
  - etapas e custo gravados na mensagem;
  - o máximo de etapas em `workspace_levels`, com padrões e migração (`0022`, junto da F2.1, ou `0023`, conforme a ordem de integração);
  - os canais REST, OpenAI, `ask` do MCP e widget;
  - fallback para a busca única.
- **Contexto necessário**:
  - `docs/specs/chat.md`, `chat-sse.md`, `produtos-e-niveis.md`, `api-publica.md`, `mcp.md` e `widget.md`;
  - AGENTS de `conversations/`, `levels/`, `retrieval/`, `apikeys/`, `mcp/` e `widget/`.
- **Critérios de aceite**:
  - um trecho acima do nível nunca chega ao contexto em nenhuma etapa (Postgres real);
  - o máximo é respeitado;
  - fake com roteiro de 1, 2 e N etapas;
  - "não sei" depois das etapas sem fonte;
  - todos os canais;
  - custo somado.
- **Depende de**: F2.2 e F2.1 (para a ordem da migração).
- **Tamanho**: médio.

#### F2.4 — Limiar de similaridade por modelo de embedding e aviso de arquivos gerados

- **Entregáveis**:
  - padrão de similaridade mínima por modelo de embedding (OpenAI e Gemini, conforme a spec), aplicado a produtos novos e explicado na API;
  - na ingestão, estatísticas por fonte dos arquivos que dominam o índice (critérios da spec) e a sugestão de padrão de exclusão, na API da fonte;
  - testes.
- **Contexto necessário**:
  - `docs/specs/indexacao.md` e `produtos-e-niveis.md`;
  - `docs/pesquisa/0004`;
  - AGENTS de `ingestion/`, `retrieval/`, `products/` e `api/`.
- **Critérios de aceite**: padrão por modelo testado; aviso com fonte sintética dominada por arquivos gerados; isolamento.
- **Depende de**: F1.1.
- **Tamanho**: pequeno a médio.

### F3 — Painel

#### F3.1 — Etapas nos níveis, reordenação no produto, etapas visíveis no chat e aviso nas fontes

- **Entregáveis**:
  - **Níveis de resposta:** máximo de etapas por nível, com o custo estimado considerando as etapas.
  - **Produto:** a opção "Reordenar trechos" e a disponibilidade do reranker; o limiar padrão do modelo da coleção.
  - **Chat:** as etapas visíveis enquanto o modelo busca de novo ("Buscando: …") e o total no fim.
  - **Fontes:** o aviso de arquivos gerados, com a sugestão de exclusão aplicável.
  - **Widget:** sem exibir as consultas ao visitante, conforme a spec.
  - Cliente gerado.
- **Contexto necessário**: `frontend/AGENTS.md`, as features de settings, products, chat e sources; tipos gerados; specs.
- **Critérios de aceite**: testes de cada tela e de cada papel.
- **Depende de**: F2.1, F2.3 e F2.4.
- **Tamanho**: médio.

### F4 — Avaliação e validação

#### F4.1 — Conjunto de avaliação sintético com gabarito e roteiro contra a stack

- **Entregáveis**:
  - `scripts/eval/`, com `AGENTS.md`:
    - corpus sintético pequeno: manual em Markdown, código de exemplo, esquema SQL em migrações e chamados e cards sintéticos;
    - perguntas com gabarito (fontes esperadas, trechos obrigatórios, nível, "deve dizer que não sabe");
    - roteiro que prepara um workspace na stack pela API, indexa, pergunta em cada nível e gera um relatório em Markdown e JSON com acertos, fontes, etapas, custo e tempo;
    - testes do roteiro contra uma API falsa (sem LLM).
  - Guia de uso.
- **Contexto necessário**: `docs/specs/avaliacao.md`, `scripts/AGENTS.md` e as specs da API usada.
- **Critérios de aceite**: o roteiro roda contra a stack com o provedor `fake` de ponta a ponta; testes com 95% ou mais; nenhum dado real.
- **Depende de**: F2.3.
- **Tamanho**: médio.

#### F4.2 — E2E da stack, guias e documentação

- **Entregáveis**:
  - **E2E da stack:** pergunta respondida em mais de uma etapa com o fake roteirizado, evento de etapa no chat, reordenação ligada e desligada com o reranker falso, e aviso de arquivos gerados numa fonte.
  - **Guias:** atualizações em `produtos-e-niveis.md`, `subir-ambiente.md` (o reranker no compose, memória e primeira subida) e `indexar-uma-fonte.md`, e um guia da avaliação.
  - **Documentação geral:** README, CHANGELOG e as seções 1 e 12 do `AGENTS.md` raiz.
- **Contexto necessário**: `frontend/e2e/stack/`, os guias e as specs do plano.
- **Critérios de aceite**: E2E verde duas vezes seguidas; guias revisados pelo orquestrador.
- **Depende de**: F3.1 e F4.1.
- **Tamanho**: médio.

#### F4.3 — Ensaio no Minski contra a linha de base dos ensaios 0005 e 0006

- **Entregáveis**:
  - **Preparação:** a stack `knobridge-minski` atualizada, com o reranker real.
  - **Perguntas:** as dos ensaios 0005 e 0006, nos três níveis e pelo `ask` do MCP.
  - **Comparação:**
    - linha de base, com busca única e sem reranker;
    - com reranker;
    - com reranker e etapas.
    - Em cada configuração: acertos, fontes, etapas, custo e tempo por nível.
  - **Avaliação sintética:** o conjunto sintético rodado com LLM real.
  - **Correções:** as que o ensaio pedir, com teste.
  - **Relatório:** `docs/pesquisa/0007-qualidade-da-resposta-no-minski.md`, só com métricas, perguntas e conclusões.
- **Contexto necessário**: orquestrador; `docs/pesquisa/0005` e `0006`.
- **Critérios de aceite**: relatório com a comparação e o gasto; nada do Minski no repositório.
- **Depende de**: F4.2.
- **Tamanho**: médio.

## 5. Decisões

As decisões D1 a D6 são do usuário (seção 2). A D7 reúne as escolhas técnicas que o ADR 0010 da F1.1 confirma ou corrige.

## 6. Pendências do usuário

Nenhuma.

## 7. Registro de andamento

- 2026-10-17 — plano criado na branch `plano/0011-qualidade-da-resposta` (a partir de `main`); aguardando aprovação.
- 2026-10-17 — plano aprovado pelo usuário ("Aprovado"); F1.1 iniciada (agente em worktree).
- 2026-10-17 — F1.1 concluída: ADR 0010, spec avaliacao.md e nove specs atualizadas, visão com D20; links, âncoras e tabelas conferidos
- 2026-10-17 — F2.1 iniciada (agente em worktree).
- 2026-10-17 — F2.2 iniciada (agente em worktree).
- 2026-10-17 — F2.4 iniciada (agente em worktree).
- 2026-10-17 — F2.2 concluída: chamada de ferramentas nos provedores OpenAI/OpenRouter, Anthropic e fake, com streaming e ToolsUnsupportedError; corpo sem ferramentas idêntico ao de hoje; gates do agente: ruff, pyright e 244 testes direcionados, módulos de llm/ em 100%; orquestrador: ruff, pyright e tests/llm na integração (a suíte inteira roda na próxima integração)
- 2026-10-17 — F2.1 concluída: reranker self-host (TEI com bge-reranker-v2-m3) no compose, HttpReranker com queda para a ordem do RRF, opção por produto (0022), saúde da instância e reranker falso no E2E; gates do agente: backend 3168 passed + 1 stub corrigido (25/25), 99,85%, scripts 99,81%, frontend 1711; orquestrador: ruff, pyright, 278 testes direcionados e compose nas duas camadas
- 2026-10-17 — F2.4 concluída: limiar de similaridade por modelo de embedding (0023, produtos com 0,35 passam ao padrão do modelo) e aviso de arquivos que dominam o índice em sources.index_stats; integrada sobre F2.1 e F2.2: backend 3245 passed com 99%, frontend 1711
- 2026-10-17 — F2.3 iniciada (agente em worktree).
- 2026-10-17 — F2.3 concluída: busca em etapas com search_sources até max_steps do nível em todos os canais, reformulação com busca vazia, evento step, steps/retrieval na mensagem, chat_searches em Uso e custos, migração 0024; backend 3.303 testes (99%), frontend 1.711
- 2026-10-17 — F3.1 iniciada
- 2026-10-17 — F4.1 iniciada (em paralelo à F3.1)
- 2026-10-17 — F4.1 concluída: scripts/eval com corpus sintético do Vértice ERP, 30 perguntas com gabarito, run/compare/copy-corpus e testes contra API falsa (264 testes, 99,9%); rodado contra uma stack isolada com o provedor fake: 5 fontes indexadas, aviso gerado/** na fonte de código, nenhum vazamento, limpeza e níveis restaurados; a validação achou e corrigiu dois defeitos do compose (a01bc74 reranker sem memória, c613051 IP do painel)

## 8. Encerramento

A preencher ao concluir.
