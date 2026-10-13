---
id: 0009
titulo: Produtos e níveis de acesso — o chat por produto com respostas, fontes e modelo conforme o nível de quem pergunta (usuário final, suporte, desenvolvimento e produto), também na API
slug: produtos-e-niveis
solicitado_por: usuario
criado_em: 2026-10-13
atualizado_em: 2026-10-13
status: em_execucao
aprovado_em: 2026-10-13
aprovado_por: usuario
concluido_em: null
branch: plano/0009-produtos-e-niveis
fases:
  - id: F1
    titulo: Contrato e modelo de dados
    status: concluida
    subfases:
      - id: F1.1
        titulo: ADR 0008 e specs de produtos e níveis (e ajustes em chat, API pública, chamados, indexação e autenticação)
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-13
        concluida_em: 2026-10-13
        commit: fd381b8
      - id: F1.2
        titulo: Migração 0018 (produtos a partir dos assistentes, níveis por membro e produto, nível mínimo de fonte e documento, níveis do workspace) com RLS
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-13
        concluida_em: 2026-10-13
        commit: cd7a78c
  - id: F2
    titulo: Servidor
    status: em_execucao
    subfases:
      - id: F2.1
        titulo: Produtos, configuração dos níveis do workspace e nível de cada membro por produto
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-13
        concluida_em: 2026-10-13
        commit: 3aabe2a
      - id: F2.2
        titulo: Chat por produto e nível (busca filtrada pelo nível, instruções e modelo do nível)
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-13
        concluida_em: 2026-10-13
        commit: 768d1e6
      - id: F2.3
        titulo: Cards de desenvolvimento por push (tipo card na API de entrada, conector interno e citação)
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-13
        concluida_em: 2026-10-13
        commit: 6773c35
      - id: F2.4
        titulo: API pública e webhook por produto e nível (chaves com produtos e nível máximo, model produto:nível, canal público só usuário final)
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F3
    titulo: Painel
    status: pendente
    subfases:
      - id: F3.1
        titulo: Produtos no lugar de Assistentes e a configuração dos níveis nas Configurações
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-13
        concluida_em: 2026-10-13
        commit: null
      - id: F3.2
        titulo: Nível por produto em Membros e convites, e nível mínimo nas fontes
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.3
        titulo: Chat com produto e nível, Conversas e Uso e custos por produto e nível, chaves de API por produto
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F4
    titulo: Entrega e ensaio
    status: pendente
    subfases:
      - id: F4.1
        titulo: E2E da stack, guias, README, CHANGELOG e AGENTS raiz
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.2
        titulo: Ensaio dos três níveis no índice do Minski
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes:
  - id: D1
    data: 2026-10-13
    por: usuario
    decisao: "Produto vira entidade do workspace (nome, coleções, texto próprio de instruções, webhook de abrir chamado); no chat a pessoa escolhe o produto e o nível vem do acesso dela"
    motivo: "a pessoa pensa no produto que usa, não em assistentes"
    alternativas: "produto = assistente; produto = coleção"
    adr: docs/adr/0008-produtos-e-niveis.md
  - id: D2
    data: 2026-10-13
    por: usuario
    decisao: "Três níveis de resposta: usuário final (como usar, dúvidas de fluxo), suporte (tudo do usuário final mais exemplos curtos de código, validações e consultas SQL de leitura para analisar cenários) e desenvolvimento e produto (tudo dos anteriores mais planejamento de features e verificação de cards já tratados)"
    motivo: "pedido do usuário"
    alternativas: "nenhuma"
    adr: docs/adr/0008-produtos-e-niveis.md
  - id: D3
    data: 2026-10-13
    por: usuario
    decisao: "O admin define o nível máximo de cada membro em cada produto; a pessoa pode responder num nível abaixo do seu, nunca acima"
    motivo: "acesso varia por produto"
    alternativas: "um nível por pessoa para todos os produtos; nível pelo papel do workspace"
    adr: null
  - id: D4
    data: 2026-10-13
    por: usuario
    decisao: "O nível restringe as fontes: cada fonte tem um nível mínimo, e a busca filtra antes de montar o contexto; padrões por tipo: usuário final = pastas de documentos e conhecimento revisado do harness; suporte = + chamados e conhecimento inferido; desenvolvimento e produto = + repositórios Git (código e commits) e cards; o admin muda por fonte"
    motivo: "o usuário final nunca deve receber trecho de código ou dado interno; não depender do modelo obedecer"
    alternativas: "só o estilo da resposta por prompt; tudo começando em usuário final; tudo começando em desenvolvimento"
    adr: docs/adr/0008-produtos-e-niveis.md
  - id: D5
    data: 2026-10-13
    por: usuario
    decisao: "Cards de desenvolvimento entram pelo mesmo push dos chamados, como tipo card (formato padrão, API com token e upload), e só o nível desenvolvimento e produto os vê"
    motivo: "qualquer ferramenta (Jira, Azure DevOps, GitHub Issues, Trello) integra sem conector próprio, como os chamados"
    alternativas: "conector de uma ferramenta; deixar para depois"
    adr: null
  - id: D6
    data: 2026-10-13
    por: usuario
    decisao: "Modelo por nível definido uma vez no workspace (credencial e modelo para cada um dos três níveis); os produtos herdam"
    motivo: "configuração simples; o modelo mais capaz vai para o nível que precisa"
    alternativas: "modelo por produto e nível"
    adr: null
  - id: D7
    data: 2026-10-13
    por: usuario
    decisao: "SQL do suporte a partir do que já está indexado (migrações, models e conhecimento do harness); sem fonte nova de esquema nem conexão ao banco do cliente"
    motivo: "sem integração nova e sensível neste plano"
    alternativas: "dicionário de dados por upload; conexão ao catálogo do banco"
    adr: null
  - id: D8
    data: 2026-10-13
    por: usuario
    decisao: "Na API, a chave define os produtos e o nível máximo; cada requisição informa produto e nível desejado (≤ máximo) como objetivo; na API compatível com OpenAI, model é <produto> ou <produto>:<nível>; canal público (sem login do usuário, como o futuro widget) só aceita usuário final"
    motivo: "o mesmo controle de acesso do painel vale para as integrações"
    alternativas: "nível fixo por chave"
    adr: docs/adr/0008-produtos-e-niveis.md
  - id: D9
    data: 2026-10-13
    por: usuario
    decisao: "Os assistentes atuais viram produtos (mesmas coleções; o modelo dele vale para os três níveis até o admin ajustar); conversas, chaves de API e webhook de chamados passam para o produto; a tela Assistentes dá lugar a Produtos"
    motivo: "um conceito só para o usuário"
    alternativas: "produtos e assistentes convivendo"
    adr: docs/adr/0008-produtos-e-niveis.md
  - id: D10
    data: 2026-10-13
    por: usuario
    decisao: "Instruções de cada nível com texto padrão do KnoBridge, editável pelo admin do workspace junto com os modelos; cada produto pode acrescentar um texto próprio"
    motivo: "o comportamento do nível é do produto KnoBridge, mas cada empresa ajusta o tom"
    alternativas: "texto fixo no código"
    adr: null
  - id: D11
    data: 2026-10-13
    por: usuario
    decisao: "Membros atuais e novos começam como usuário final em todos os produtos; owners e admins começam como desenvolvimento e produto; o convite pode trazer o nível"
    motivo: "seguro por padrão"
    alternativas: "nível pelo papel na migração"
    adr: null
  - id: D12
    data: 2026-10-13
    por: usuario
    decisao: "Webhook de abrir chamado é configuração do produto; chaves de API têm escopo por produto (no lugar do escopo por assistente) e nível máximo"
    motivo: "consequência de D9"
    alternativas: "webhook por workspace"
    adr: null
  - id: D13
    data: 2026-10-13
    por: agente
    decisao: "O nível mínimo vale por fonte e pode ser refinado por documento (conhecimento revisado = usuário final, inferido = suporte, na mesma fonte runner); o filtro entra no SQL da busca (chunk com nível mínimo ≤ nível da pergunta), nunca depois; a conversa grava produto e nível, e o custo e o uso passam a agrupar também por produto e nível"
    motivo: "filtro no banco é a garantia de que o contexto do LLM não leva fonte acima do nível"
    alternativas: "filtrar depois da busca; nível só por fonte"
    adr: docs/adr/0008-produtos-e-niveis.md
  - id: D14
    data: 2026-10-13
    por: agente
    decisao: "F1.1: produto mantém o id do assistente de origem (conversas, chaves e pedidos migram com o mesmo valor; segredo do webhook não é recifrado); temperatura, credencial e modelo vão para o nível do workspace, idioma, tom, mensagem de sem fonte, similaridade e system_prompt (instructions) ficam no produto; instruções de nível nulas = texto padrão do KnoBridge; nível sem modelo responde 409 level_not_configured (400 na rota OpenAI) e o checklist ganha o item levels; nível do membro sem registro segue o papel (owner/admin product_dev, demais end_user); nível fixo por conversa e conferido a cada pergunta; nível mínimo efetivo = maior entre fonte, documento e chunk, com refinamentos que só sobem (código em fonte de pasta = product_dev; seção de evidências do harness = support, citação end_user sem evidência); mudar o nível da fonte recalcula chunks sem reindexar; Testar busca passa a editor com level; rotas /assistants do painel removidas, API pública aceita assistant_id e os nomes antigos de model como alias; max_level obrigatório na chave, nível omitido = max_level da chave, chaves e conversas migradas em product_dev; sufixo :nível só para os três nomes; canal público limitado a end_user no núcleo; cards em cards.md reaproveitando ticket_inbox e o token kbi_ (409 source_kind_mismatch), status backlog/in_progress/done/cancelled; modelo inicial dos níveis = o do assistente mais usado; uso troca assistant por product e ganha level"
    motivo: "detalhes de contrato revisados pelo orquestrador; os refinamentos de nível fecham vazamentos de código por fontes de pasta, evidências do harness e Testar busca"
    alternativas: "nível só por fonte; manter /assistants no painel; nível omitido = end_user"
    adr: null
  - id: D15
    data: 2026-10-13
    por: agente
    decisao: "F1.2: assistants renomeada para products (e assistant_collections para product_collections) com os mesmos ids e políticas renomeadas; nomes terminados em :nível viram ' - nível' (ou (2), (3)) e uma restrição impede novos; workspace_levels com o modelo do assistente mais usado; conversas, mensagens e chaves em product_dev; chunks.min_level com padrão product_dev no banco (o mais restritivo); a migração liga app.system só na transação para os passos de dados; downgrade recusa produto novo, conversa ou chave abaixo de product_dev, nível de membro, convite com níveis e fonte cards; colunas credential_id, model e temperature ficam transitórias em products e saem na F2.2 por uma migração 0019 (o downgrade devolve o modelo do nível product_dev)"
    motivo: "suíte verde sem antecipar a F2; nada vaza por padrão"
    alternativas: "editar a 0018 na F2; criar products e copiar"
    adr: null
  - id: D16
    data: 2026-10-13
    por: agente
    decisao: "F2.1: serviços em products/ (service, listing, duplicate) e levels/ (defaults com os textos padrão, workspace com preço e custo estimado, members, grants de convite); rotas /assistants removidas (404) e webhook em /products/{id}/ticket-webhook; até a F2.2, criar produto copia credential_id, model e temperature do primeiro nível configurado (product_dev, support, end_user) e responde 409 level_not_configured sem nenhum; collection_ids repetidos e PATCH vazio dão 422; níveis de membro gravados com upsert; o E2E da stack quebra até a tela de níveis (F3.1/F4.1); os eventos de auditoria do webhook ainda usam assistant.* e passam a product.* na F2.4"
    motivo: "contrato da F1.1 com a suíte verde no meio da transição"
    alternativas: "manter /assistants como alias no painel"
    adr: null
  - id: D17
    data: 2026-10-13
    por: agente
    decisao: "F2.3: cards reaproveitam o pacote tickets/ (push.py com TICKETS e CARDS; card_wire.py e card_markdown.py), mesma caixa ticket_inbox e token kbi_; token de fonte do outro tipo dá 409 source_kind_mismatch nos envios e 404 em upload, prévia e resumo; marcadores [RELATOR] e [RESPONSAVEL_n]; card inválido guardado falha com card_invalid; reindexar fonte de cards é recusado; auditoria source.cards_uploaded; as telas da fonte de cards (criar, integração, upload, prévia) entram na F3.2 e a citação de card na F3.3 (lacuna apontada pelo agente; generalizam as telas de chamados, sem escopo novo)"
    motivo: "mesmo mecanismo dos chamados, sem duplicar código"
    alternativas: "pacote cards/ separado; deixar a fonte de cards só pela API"
    adr: null
  - id: D18
    data: 2026-10-13
    por: agente
    decisao: "F2.2: conversa criada com product_id e level opcional (sem level = máximo de quem cria); a cada pergunta, antes do embedding: produto ativo (409 product_inactive), nível até o máximo atual (403 level_not_allowed) e nível configurado (409 level_not_configured); filtro de chunks.min_level no SQL dos dois braços sem statement a mais; prompt = instruções do nível (ou padrão) + texto do produto + regras fixas, com credencial, modelo e temperatura do nível; citação knowledge em end_user com evidence null; lote grava documents/chunks.min_level (código em pasta = product_dev, inferido = support, seção de evidências sempre trecho próprio support); só owner/admin muda o nível mínimo da fonte (recalcula trechos sem reindexar, auditado); uso com group_by product e level; checklist provider, collection, source, levels, product, chat; migração 0019 remove credential_id, model e temperature de products; pacote assistants/ removido (F2.4 troca os imports transitórios Product as Assistant)"
    motivo: "contrato da F1.1; garantia de nível no banco"
    alternativas: "filtro depois da busca; manter assistants/"
    adr: null
  - id: D19
    data: 2026-10-13
    por: agente
    decisao: "F3.1: área Produtos no lugar de Assistentes (redireciona /assistants), seção Níveis de resposta nas Configurações salva por PATCH .../levels/{level} com todos os campos; instruções iguais ao texto padrão vão como nulo; sugestões de modelo fixas a partir dos preços conhecidos; checklist com levels e product sem o apelido assistant (a API já manda as chaves novas desde a F2.2); E2E da stack ainda vai a /assistants e é refeito na F4.1"
    motivo: "contrato gerado é PATCH por nível"
    alternativas: "PUT de todos os níveis; manter o apelido assistant"
    adr: null
pendencias_usuario: []
---

# Plano 0009 — Produtos e níveis de acesso

## 1. Pedido original

> "Hoje ja tem uma interface interna para usar o assistente? Se não, vamos colocar na pauta para a próxima fase de desenvolvimento! O que precisa: selecionar qual o produto; com base no acesso, definir o nível das respostas — usuário final (apenas como usar, tirar dúvidas sobre o fluxo....); usuário suporte (além do usuário final, consegue explicar com pequenos exemplos de códigos, exemplos de validação, monta consultas SQL para análises de cenários...); Desenvolvimento e Produto (tudo dos anteriores, mas ajuda a planejar novas features, entende se a demanda já foi tratada em algum card anteriormente...). Com base do nível do usuário, um modelo mais ou menos capaz é aplicado. Isso também vale para as APIs e outras formas de chat, deve ser informado o objetivo e se for público só aceita o nível usuário final"

Hoje há um chat interno (menu **Chat**), mas por assistente, sem produto nem níveis.

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | O que é um produto? | Entidade nova com coleções e configuração por nível | 2026-10-13 |
| 2 | Como o nível é definido? | Por pessoa e produto; pode responder abaixo, nunca acima | 2026-10-13 |
| 3 | O nível restringe as fontes? | Sim: fonte com nível mínimo, filtrado na busca | 2026-10-13 |
| 4 | De onde vêm os cards? | Mesmo push dos chamados, tipo card | 2026-10-13 |
| 5 | Modelos por nível | Padrão do workspace por nível | 2026-10-13 |
| 6 | Conhecimento para SQL | Só o que já está indexado | 2026-10-13 |
| 7 | Produto e nível na API | Chave com produtos e nível máximo; requisição informa produto e nível; canal público só usuário final | 2026-10-13 |
| 8 | Assistentes atuais | Viram produtos | 2026-10-13 |
| 9 | Nível mínimo padrão das fontes | Documentos e conhecimento revisado: usuário final; chamados e inferido: suporte; Git e cards: desenvolvimento | 2026-10-13 |
| 10 | Instruções por nível | Padrão do KnoBridge, editável no workspace, com texto extra por produto | 2026-10-13 |
| 11 | Nível de quem entra | Usuário final; owners e admins: desenvolvimento e produto | 2026-10-13 |
| 12 | Webhook e chaves | Por produto | 2026-10-13 |

**O que será feito**:
- **Produtos** substituem assistentes: os existentes são migrados.
- **Configuração dos níveis** nas Configurações do workspace: para cada um dos três, credencial e modelo e o texto de instruções.
- **Nível de cada membro**: em Membros, o admin define o nível máximo de cada pessoa em cada produto; o convite já pode trazer o nível.
- **Nível mínimo das fontes**: definido por fonte (e refinado por documento no conhecimento do harness) e aplicado na busca.
- **Chat**: a pessoa escolhe o produto e responde no seu nível máximo ou abaixo; as respostas usam o modelo, as instruções e as fontes daquele nível.
- **Cards de desenvolvimento** chegam por push, como os chamados.
- **API pública**: chaves com produtos e nível máximo, a requisição informa produto e nível, e o canal público fica limitado ao usuário final.
- **Conversas e Uso e custos** passam a mostrar e agrupar por produto e nível.

**Fora do escopo**:
- fonte de esquema de banco e conexão ao banco do cliente (D7);
- o widget e os canais em si (a regra do canal público fica pronta no núcleo);
- conector específico de ferramenta de cards (D5).

## 3. Critérios de aceite

- [ ] Os assistentes existentes viram produtos sem perder coleções, conversas, chaves nem webhook.
- [ ] A mesma pergunta, no mesmo produto, responde diferente por nível:
  - usuário final só recebe fontes do nível dele, nunca trecho de código, provado por teste no SQL da busca;
  - suporte recebe exemplos de código e SQL a partir das fontes do seu nível;
  - desenvolvimento e produto consulta também cards e código.
- [ ] Cada nível usa o modelo configurado no workspace.
- [ ] Ninguém responde acima do próprio nível, nem pelo painel nem pela API; chave com nível máximo de usuário final recusa suporte; canal público só aceita usuário final.
- [ ] Cards entram por API e por upload, e são citados só para desenvolvimento e produto.
- [ ] Conversas e Uso e custos mostram e filtram produto e nível.
- [ ] O E2E da stack cobre os três níveis; o ensaio no Minski tem relatório; cobertura ≥ 95% e isolamento testados.

## 4. Fases e subfases

Convenções para todas as subfases: código em inglês, docs em pt-BR; regras 1 a 10 do `AGENTS.md` raiz; a suíte padrão não chama LLM nem rede externa. Os agentes não editam `backend/AGENTS.md`, `backend/src/knobridge/AGENTS.md` nem o `AGENTS.md` raiz: relatam o texto e o orquestrador insere (exceto F4.1, que edita o raiz). Backend, frontend e E2E rodam um de cada vez. Antes de cada commit, o orquestrador confere que está na branch do plano.

### F1 — Contrato e modelo de dados

#### F1.1 — ADR 0008 e specs

- **Entregáveis**:
  - `docs/adr/0008-produtos-e-niveis.md` (D1, D2, D4, D8, D9, D13), com linha na seção 9 da visão.
  - `docs/specs/produtos-e-niveis.md`:
    - produto e níveis (nomes técnicos `end_user`, `support`, `product_dev`);
    - configuração do workspace (modelos e instruções por nível, com os textos padrão);
    - nível por membro e produto, convites e a regra de responder abaixo do próprio nível;
    - nível mínimo de fonte e de documento, com os padrões por tipo, e o filtro na busca;
    - o chat com produto e nível;
    - a migração dos assistentes.
  - Ajustes nas specs:
    - `chat.md` e `chat-sse.md`: produto e nível na conversa e no evento;
    - `api-publica.md`: chaves por produto e nível máximo, `model` como `<produto>[:<nível>]`, campo de nível na REST e canal público;
    - `chamados.md`: tipo card, com o formato do card, ou uma `cards.md` curta se ficar melhor;
    - `indexacao.md`: nível mínimo;
    - `autenticacao.md`: nível por membro e convites;
    - `uso-e-custos.md`: agrupamento por produto e nível.
- **Contexto necessário**:
  - `AGENTS.md` raiz e `docs/AGENTS.md`;
  - visão (seções 7 a 9);
  - as specs citadas;
  - `docs/adr/0006` e `0007`.
- **Critérios de aceite**: contratos completos para as subfases seguintes; links válidos; checagens verdes.
- **Depende de**: nenhuma.
- **Tamanho**: médio.

#### F1.2 — Migração 0018

- **Entregáveis**:
  - tabelas `products` (a partir de `assistants`: nome, texto extra, webhook, ativo), `product_collections`, `workspace_levels` (credencial, modelo e instruções por nível) e `member_product_levels`;
  - coluna `min_level` em `sources`, `documents` e `chunks` (ou só em `chunks`, se a spec decidir), com os padrões por tipo;
  - produto e nível em `conversations` e em `messages` (para uso e custos);
  - em `api_keys`: `product_ids` e `max_level`;
  - migração de dados: assistentes → produtos, com conversas, chaves e webhook apontando para o produto;
  - níveis iniciais dos membros (D11) e do workspace (o modelo do assistente mais usado, ou o primeiro, nos três níveis);
  - `modelo-de-dados.md` v1.0.
- **Contexto necessário**:
  - `backend/AGENTS.md` e os AGENTS de `migrations/`, `assistants/`, `conversations/`, `ingestion/`, `apikeys/` e `tenancy/`;
  - a migração `0017`;
  - `docs/specs/produtos-e-niveis.md`.
- **Critérios de aceite**: `upgrade` com dados de assistentes, conversas, chaves e webhook migrados corretamente (teste com dados semeados); `downgrade` testado ou recusado com dados novos; RLS em todas as tabelas novas.
- **Depende de**: F1.1.
- **Tamanho**: médio.

### F2 — Servidor

#### F2.1 — Produtos, níveis do workspace e nível por membro

- **Entregáveis**:
  - CRUD de produtos, no lugar das rotas de assistentes, conforme a spec decidir sobre compatibilidade;
  - rotas da configuração de níveis do workspace (admin);
  - nível por membro e produto (admin), com o convite trazendo o nível;
  - `GET /v1/me` com o nível máximo de cada produto;
  - auditoria.
- **Contexto necessário**: AGENTS de `assistants/`, `tenancy/`, `api/` e `audit/`; specs de produtos e autenticação.
- **Critérios de aceite**: papéis, validação, isolamento entre workspaces, auditoria, e a regra de nunca ficar acima do máximo.
- **Depende de**: F1.2.
- **Tamanho**: médio.

#### F2.2 — Chat por produto e nível

- **Entregáveis**:
  - conversa com produto e nível, validando o nível contra o máximo da pessoa;
  - busca híbrida filtrando `min_level` no SQL dos dois braços;
  - instruções do nível mais o texto do produto no prompt;
  - modelo e credencial do nível;
  - custo e uso com produto e nível;
  - nível mínimo por documento no conhecimento do harness (revisado ou inferido) e padrões por tipo de fonte.
  - o lote de ingestão grava `min_level` (fonte, documento e trecho) e o chunking nunca junta a seção de evidências com outra;
  - migração `0019` que remove as colunas transitórias `credential_id`, `model` e `temperature` de `products` (o downgrade devolve o modelo do nível `product_dev`; D15).
- **Contexto necessário**: AGENTS de `conversations/`, `retrieval/`, `ingestion/` e `harness/`; `retrieval/search.py`; `conversations/chat.py` e `prompt.py`; spec de produtos e chat.
- **Critérios de aceite**:
  - teste de que um chunk acima do nível nunca chega ao contexto, nos dois braços e na fusão;
  - modelo e instruções certos por nível;
  - nível acima do máximo dá 403;
  - número constante de consultas.
- **Depende de**: F2.1.
- **Tamanho**: médio.

#### F2.3 — Cards por push

- **Entregáveis**:
  - tipo card no recebimento (API e upload): formato, validação, caixa de entrada e anonimização se couber;
  - conector interno, Markdown e chunking do card;
  - citação `kind: card`;
  - fonte de cards com nível mínimo de desenvolvimento e produto.
- **Contexto necessário**: AGENTS de `tickets/` e `ingestion/`; o tipo card na spec; o pacote `tickets/` como padrão.
- **Critérios de aceite**: os mesmos critérios dos chamados (idempotência, `updated_at`, lápide, isolamento), citação no chat só no nível desenvolvimento e produto.
- **Depende de**: F1.2.
- **Tamanho**: médio.

#### F2.4 — API pública e webhook por produto e nível

- **Entregáveis**:
  - chaves com `product_ids` e `max_level`;
  - REST de conversa com produto e nível;
  - API compatível com OpenAI com `model` `<produto>[:<nível>]` (sem nível = o máximo da chave, ou usuário final se a spec decidir) e `/v1/models` listando as combinações permitidas;
  - a regra do canal público (só usuário final) no núcleo, testada;
  - webhook de abrir chamado vindo do produto.
- **Contexto necessário**: AGENTS de `apikeys/`, `api/` e `tickets/`; specs de API pública e chamados.
- **Critérios de aceite**: nível acima do máximo da chave recusado (REST e OpenAI); SDK oficial com `model` `produto:nível`; webhook por produto; isolamento.
- **Depende de**: F2.2.
- **Tamanho**: médio.

### F3 — Painel

#### F3.1 — Produtos e níveis nas Configurações

- **Entregáveis**:
  - a área **Produtos** no lugar de **Assistentes**: lista, criar e editar com coleções, texto extra e webhook; duplicar;
  - nas **Configurações** do workspace, a seção **Níveis de resposta**, com credencial, modelo e instruções de cada nível e o custo estimado por resposta.
- **Contexto necessário**: `frontend/AGENTS.md`, `features/assistants` e `features/settings`; tipos gerados.
- **Critérios de aceite**: testes de cada tela e de cada papel.
- **Depende de**: F2.1.
- **Tamanho**: médio.

#### F3.2 — Nível em Membros, convites e fontes

- **Entregáveis**:
  - em **Membros**, o nível por produto (tabela membro × produto ou diálogo por membro);
  - o convite com nível;
  - nas **Fontes**, o nível mínimo, com os padrões por tipo e um aviso ao subir o nível de uma fonte em uso.
  - a fonte de **cards** no painel (criar, Integração com token e exemplos, Upload e Prévia), generalizando as telas da fonte de chamados (D17).
- **Contexto necessário**: `features/members` e `features/sources`; tipos gerados.
- **Critérios de aceite**: testes de edição, validação e papéis.
- **Depende de**: F2.1, F2.2.
- **Tamanho**: médio.

#### F3.3 — Chat, Conversas, Uso e custos e chaves por produto e nível

- **Entregáveis**:
  - **Chat** com seletor de produto e de nível (só até o máximo da pessoa) e o selo do nível em cada conversa;
  - **Conversas** e **Uso e custos** com filtro e agrupamento por produto e nível;
  - **Chaves de API** com produtos e nível máximo, e exemplos com `model` `produto:nível`.
  - citação `kind: card` no chat com número, tipo, status e sprint.
- **Contexto necessário**: `features/chat`, `features/conversations`, `features/usage` e `features/apikeys`; tipos gerados.
- **Critérios de aceite**: testes do seletor (nível acima indisponível), filtros e chaves.
- **Depende de**: F2.2, F2.4, F3.1.
- **Tamanho**: médio.

### F4 — Entrega e ensaio

#### F4.1 — E2E, guias e documentação

- **Entregáveis**:
  - E2E da stack:
    - produto migrado do assistente;
    - mesma pergunta em três níveis com fontes diferentes, sem código para o usuário final;
    - card citado só no nível desenvolvimento e produto;
    - chave com nível máximo de usuário final recusando suporte pelo SDK da OpenAI.
  - Guias:
    - `docs/guias/produtos-e-niveis.md`;
    - atualizações em `primeiro-acesso.md` e `usar-a-api.md`;
    - guia de cards junto do de chamados.
  - README, CHANGELOG e as seções 1 e 12 do `AGENTS.md` raiz.
- **Contexto necessário**: `frontend/e2e/stack/` e os guias.
- **Critérios de aceite**: E2E verde duas vezes seguidas; guias revisados pelo orquestrador.
- **Depende de**: F3.1 a F3.3.
- **Tamanho**: médio.

#### F4.2 — Ensaio dos três níveis no Minski

- **Entregáveis**:
  - na stack `knobridge-minski`, migrada para este código: o produto MAESTRO com as fontes do ensaio e os níveis mínimos padrão;
  - perguntas dos ensaios 0001 e 0002 e perguntas novas de suporte (SQL e validação) e de desenvolvimento (planejamento e "já foi tratado?");
  - comparação por nível de fontes usadas, qualidade lida pelo orquestrador, modelo e custo;
  - correções com teste;
  - relatório `docs/pesquisa/0005-niveis-no-minski.md`, só com métricas, perguntas e conclusões.
- **Contexto necessário**: orquestrador; `docs/pesquisa/0001` e `0002`.
- **Critérios de aceite**: relatório com a comparação por nível e o gasto; nada do Minski no repositório.
- **Depende de**: F4.1.
- **Tamanho**: médio.

## 5. Decisões

D1 a D12 vêm das respostas do usuário; D13 é do agente.

## 6. Pendências do usuário

Nenhuma.

## 7. Registro de andamento

- 2026-10-13 — plano criado na branch `plano/0009-produtos-e-niveis` (a partir de `plano/0008-telas-de-uso-e-administracao`, ainda não integrada); aguardando aprovação.
- 2026-10-13 — plano aprovado pelo usuário ("Aprovado"); F1.1 iniciada (agente em worktree).
- 2026-10-13 — F1.1 concluída: ADR 0008, specs produtos-e-niveis.md e cards.md, ajustes em chat, chat-sse, api-publica, chamados, indexação, autenticação e uso-e-custos, visão v0.6; links e checagens verdes
- 2026-10-13 — F1.2 iniciada (agente em worktree).
- 2026-10-13 — F1.2 concluída: migração 0018 (assistentes viram produtos com o mesmo id, níveis do workspace e do membro, nível em conversas, mensagens e chaves, nível mínimo em fontes, documentos e trechos), RLS e teste com dados semeados; gates do agente: backend 2451 passed com 99,89%; orquestrador: ruff, pyright e AGENTS na integração
- 2026-10-13 — F2.1 iniciada (agente em worktree).
- 2026-10-13 — F2.3 iniciada (agente em worktree).
- 2026-10-13 — F2.1 concluída: produtos no lugar dos assistentes, configuração dos níveis do workspace, nível por membro e produto e convites com níveis; gates do agente: backend 2513 passed com 99,88%, frontend 1437; orquestrador: ruff, pyright e AGENTS na integração
- 2026-10-13 — F2.3 concluída: cards de desenvolvimento por push (API e upload), conector interno cards, Markdown e chunking do card e citação kind card, integrados sobre a F2.1; backend 2621 passed com 99% de cobertura, frontend 1438
- 2026-10-13 — F2.2 iniciada (agente em worktree).
- 2026-10-13 — F2.2 concluída: chat por produto e nível com filtro de nível mínimo no SQL da busca (teste prova que trecho acima do nível nunca chega ao LLM), modelo, temperatura e instruções do nível, ingestão gravando o nível, nível mínimo da fonte editável, uso por produto e nível e migração 0019; gates do agente: backend 2676 passed com 99,88%, frontend 1440; orquestrador: ruff, pyright e AGENTS na integração
- 2026-10-13 — F3.1 concluída: telas de Produtos e Níveis de resposta, checklist com níveis; integrada sobre a F2.2; frontend 1466 passed, 98,62% branches

## 8. Encerramento

A preencher ao concluir.
