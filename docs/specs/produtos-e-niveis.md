# Produtos e níveis de resposta

> v1.0 · 2026-10-13 · Implementado (plano 0009, F1.1 a F3.3; o ensaio da F4.2 acrescentou a proibição de planejar ao texto padrão do usuário final)

Contrato dos **produtos** (que substituem os assistentes) e dos **níveis de resposta**: o que é um produto, os três níveis e a configuração deles no workspace, o nível máximo de cada membro em cada produto, o nível mínimo das fontes e dos documentos e o filtro na busca, o chat com produto e nível, a migração dos assistentes, a compatibilidade das rotas antigas, papéis e auditoria. A decisão de arquitetura está no [ADR 0008](../adr/0008-produtos-e-niveis.md); as escolhas do usuário, no [plano 0009](../planos/0009-produtos-e-niveis.md) (D1 a D13).

Specs tocadas por este contrato: [chat.md](chat.md) (rodada de chat), [chat-sse.md](chat-sse.md) (eventos), [api-publica.md](api-publica.md) (chaves e `model`), [cards.md](cards.md) (cards de desenvolvimento), [chamados.md](chamados.md) (webhook por produto), [indexacao.md](indexacao.md) (nível mínimo no índice e na busca), [autenticacao.md](autenticacao.md) (nível por membro, convites e `/v1/me`) e [uso-e-custos.md](uso-e-custos.md) (agrupamento por produto e nível). As tabelas ficam em [modelo-de-dados.md](modelo-de-dados.md), na migração `0018` (F1.2).

Código previsto: `backend/src/knobridge/products/` (no lugar de `assistants/`: produtos, coleções do produto, duplicação, listagem), `backend/src/knobridge/levels/` (os níveis, a configuração do workspace, os textos padrão, o nível por membro e a regra do canal público), `api/products.py`, `api/levels.py` e `api/member_levels.py`. Telas: `frontend/src/features/products/` (no lugar de `features/assistants/`), a seção **Níveis de resposta** em `features/settings/` e o nível em `features/members/` e `features/sources/`.

## Conceitos

- **Produto**: o sistema sobre o qual as pessoas perguntam (ex.: "ERP", "Portal do Cliente"). Entidade do workspace com nome, descrição, coleções, um texto próprio de instruções, idioma, tom, mensagem de "sem fonte", similaridade mínima e o webhook de abrir chamado. No chat, a pessoa escolhe o produto (D1).
- **Nível de resposta**: quanto detalhe técnico a resposta pode ter e quais fontes ela pode usar. São três, em ordem crescente (D2):

| Ordem | Nome técnico | Na interface | Para quem | Pode receber |
|---|---|---|---|---|
| 0 | `end_user` | Usuário final | Quem usa o sistema | Como usar, passo a passo e dúvidas de fluxo. Nunca código nem SQL. |
| 1 | `support` | Suporte | Equipe de suporte | Tudo do usuário final, mais exemplos curtos de código, validações e consultas SQL só de leitura, a partir das fontes. |
| 2 | `product_dev` | Desenvolvimento e produto | Desenvolvimento e produto | Tudo dos anteriores, mais planejamento de features e verificação de cards já tratados. |

- "Abaixo" e "acima" seguem essa ordem. `level_rank(end_user) = 0`, `support = 1`, `product_dev = 2`. O nome técnico é o valor em toda a API, no banco e no `model` da API compatível com OpenAI; o painel traduz.
- O nível de uma pergunta decide três coisas: **as fontes** (só trechos com nível mínimo menor ou igual, filtrados no SQL da busca), **as instruções** (o texto do nível, mais o texto do produto) e **o modelo** (credencial e modelo configurados para o nível no workspace).
- O **nível máximo** é um teto por pessoa e produto (no painel) ou por chave (na API). Quem pergunta escolhe o nível da conversa até o próprio teto, nunca acima (D3, D8).

## Produto

### Campos

| Campo | Tipo | Regras |
|---|---|---|
| `id` | uuid | Na migração, é o mesmo id do assistente de origem. |
| `name` | texto | 1 a 200 caracteres, sem espaços nas pontas; único no workspace (409 `product_name_taken`). Não pode terminar em `:end_user`, `:support` nem `:product_dev` (422 `product_name_invalid`), porque o nome é o `model` da API compatível com OpenAI, onde `:<nível>` tem significado ([api-publica.md](api-publica.md#modelo--produto-e-nível)). |
| `description` | texto | Até 1000 caracteres; vazio permitido. |
| `instructions` | texto | O **texto extra** do produto, acrescentado depois das instruções do nível (D10). Até 20 000 caracteres; vazio permitido. Na migração, recebe o `system_prompt` do assistente. |
| `collection_ids` | lista de uuid | Coleções em que o chat busca (0 a 100, sem repetição). Coleção inexistente ou de outro workspace: 422 `product_collection_invalid` (`details.collection_ids`). Sem coleção, o produto responde sempre "sem fonte", sem embedding nem LLM. |
| `language` | texto | Tag BCP 47 das respostas; padrão `pt-BR`. |
| `tone` | `neutral`, `formal` ou `friendly` | Padrão `neutral`. |
| `no_source_message` | texto | Resposta quando não há fonte (regra 8); vazio ou `null` grava a mensagem padrão em pt-BR. |
| `min_similarity` | número | De 0 a 1, padrão 0,35 ([chat.md](chat.md#recuperação-de-fontes)). |
| `active` | booleano | Padrão `true`. Inativo some para o leitor e não aceita conversa nova nem mensagem (409 `product_inactive`). |
| `ticket_webhook_url` | texto ou `null` | Webhook de abrir chamado do produto (D12), com as regras de [chamados.md](chamados.md#configuração-no-produto). |
| `ticket_webhook_configured` | booleano | Só leitura: URL e segredo presentes. |
| `ticket_webhook_secret_created_at` | data ou `null` | Só leitura. |
| `my_max_level` | nível | Só leitura: o nível máximo de **quem lê** neste produto ([Nível por membro](#nível-por-membro-e-produto)). O painel usa para montar o seletor do chat. |
| `created_at`, `updated_at` | data | |

Saem do produto, em relação ao assistente: `provider_id`, `model` e `temperature`, que passam para a configuração dos níveis do workspace (D6). `system_prompt` passa a se chamar `instructions`.

### Rotas

Sob `/v1/workspaces/{workspace_id}/products` (`api/products.py`), com sessão e, nas não seguras, CSRF:

| Rota | Papel | Efeito |
|---|---|---|
| `GET ""` | viewer (leitor só vê ativos) | Lista paginada (`limit` padrão 50, máximo 200; `offset`; `total`). Filtros `query` (nome ou descrição, até 200 caracteres, sem diferenciar maiúsculas, `%`, `_` e `\` escapados), `active`, `collection_id`; `sort` = `name` (padrão), `-name`, `created_at`, `-created_at`, `updated_at`, `-updated_at`, empate pelo `id`. Número constante de statements (página, coleções e o nível de quem lê). |
| `GET /{product_id}` | viewer | `ProductOut`. Inexistente ou, para leitor, inativo: 404 `not_found`. |
| `POST ""` | editor | Cria. 201 `ProductOut`. |
| `PATCH /{product_id}` | editor | Campo omitido fica; `collection_ids` substitui o conjunto; corpo vazio é 422. |
| `DELETE /{product_id}` | editor | 204. Apaga as conversas do produto (com mensagens, feedback e pedidos de chamado) e os níveis dos membros nele; some do escopo das chaves sem erro. Para preservar o histórico, desative. |
| `POST /{product_id}/duplicate` | editor | Como a duplicação de assistentes ([chat.md](chat.md#duplicação-de-produtos)): copia a configuração e as coleções, nome `<nome> (cópia)`, `(cópia 2)`…; o webhook copia só a URL (sem segredo). Não copia conversas nem os níveis dos membros (no produto novo vale o padrão por papel). |
| `POST /{product_id}/ticket-webhook/secret` | admin | Gera o segredo `kbw_…` ([chamados.md](chamados.md#configuração-no-produto)). |
| `POST /{product_id}/ticket-webhook/test` | editor | Envia o evento de teste. |

Erros: 404 `not_found`, 409 `product_name_taken`, 422 `product_name_invalid`, `product_collection_invalid`, `webhook_url_invalid`, `webhook_destination_blocked` ou `validation_error`.

## Configuração dos níveis no workspace

Cada workspace tem **exatamente três** configurações de nível, uma por nível, criadas com o workspace (e pela migração para os existentes). Os produtos herdam todas (D6). Tela: **Configurações > Níveis de resposta** (admin).

### Campos

| Campo | Tipo | Regras |
|---|---|---|
| `level` | nível | Identifica a linha. |
| `provider_id` | uuid ou `null` | Credencial de LLM do workspace (422 `level_provider_invalid` se inexistente ou de outro workspace). Uma credencial em uso por um nível não se exclui (409 `provider_in_use`, como nas coleções). |
| `provider_name`, `provider_kind` | texto ou `null` | Só leitura. |
| `model` | texto ou `null` | Identificador do modelo no provedor, até 200 caracteres, sem espaços. `provider_id` e `model` são os dois nulos ou os dois preenchidos (422 `validation_error`). |
| `temperature` | número | De 0 a 2, padrão 0,2. |
| `instructions` | texto | As instruções do nível, até 20 000 caracteres. Na leitura, sempre o texto efetivo. |
| `instructions_is_default` | booleano | Só leitura: o workspace usa o texto padrão do KnoBridge (gravado como nulo, para receber as melhorias do padrão nas versões seguintes). |
| `default_instructions` | texto | Só leitura: o texto padrão do KnoBridge para o nível (abaixo), para o painel mostrar e restaurar. |
| `configured` | booleano | Só leitura: `provider_id` e `model` presentes. |
| `price` | objeto ou `null` | Só leitura: `{"input_usd_per_mtok", "output_usd_per_mtok"}` da tabela de preços do chat ([uso-e-custos.md](uso-e-custos.md#preços-do-chat)); `null` sem modelo ou sem preço. |
| `estimated_cost_per_answer_usd` | número ou `null` | Só leitura: custo de uma resposta de referência com 4000 tokens de entrada e 600 de saída (6 casas), para a tela comparar os níveis. `null` sem preço. |
| `updated_at` | data | |

**Nível sem modelo** (`configured = false`): conversa nova ou mensagem nesse nível responde 409 `level_not_configured` (`details.level`), antes de qualquer embedding. Um workspace novo nasce com os três níveis sem modelo; o checklist do Início pede a configuração ([uso-e-custos.md](uso-e-custos.md#checklist-de-primeiros-passos)).

### Rotas

| Rota | Papel | Efeito |
|---|---|---|
| `GET /v1/workspaces/{workspace_id}/levels` | admin | `{"items": [WorkspaceLevelOut, …]}` com os três, na ordem dos níveis. |
| `PATCH /v1/workspaces/{workspace_id}/levels/{level}` | admin, CSRF | Corpo com `provider_id`, `model`, `temperature` e/ou `instructions` (omitido fica; `instructions: null` volta ao padrão; corpo vazio é 422). Resposta 200 `WorkspaceLevelOut`. Nível desconhecido no caminho: 422 `validation_error`. |

Mudar o modelo ou as instruções vale para as perguntas seguintes; as respostas gravadas mantêm o `model` com que foram geradas.

### Textos padrão das instruções

Constantes em `levels/defaults.py`, em pt-BR, versionadas com o código. Valem quando o workspace não editou o texto do nível.

**`end_user` (Usuário final)**:

```text
Você atende o usuário final do produto: a pessoa que usa o sistema no dia a dia e não tem acesso ao código-fonte nem ao banco de dados.

O que você pode fazer:
- Explicar como usar telas, campos e funcionalidades, em passo a passo numerado, com os nomes que o usuário vê na tela.
- Explicar fluxos e regras de negócio em linguagem simples: o que acontece, em que ordem e por quê.
- Explicar mensagens de erro e aviso: o que significam e o que o próprio usuário pode fazer para resolver.

O que você não pode fazer:
- Mostrar trechos de código, nomes de rotinas, funções, classes, arquivos, tabelas ou colunas internas.
- Escrever ou sugerir consultas SQL, scripts, comandos ou alterações de configuração técnica.
- Comentar detalhes de implementação, chamados internos ou o trabalho da equipe de desenvolvimento.
- Planejar funcionalidades novas ou mudanças no produto: diga que o pedido vai para a equipe do produto.

Se a solução depender de mexer em código, banco de dados ou configuração técnica, diga que o caso precisa da equipe de suporte e ofereça abrir um chamado.
```

**`support` (Suporte)**:

```text
Você atende a equipe de suporte do produto: analistas que investigam casos de clientes, conhecem o sistema por dentro e precisam entender o que aconteceu, mas não alteram o código.

O que você pode fazer, além do que o usuário final recebe:
- Mostrar exemplos curtos de código tirados das fontes (poucas linhas) para explicar uma regra, validação ou mensagem, citando o arquivo e as linhas.
- Explicar validações e condições: em que situação a regra dispara, que dados ela confere e qual mensagem mostra.
- Montar consultas SQL somente de leitura (SELECT) para analisar o cenário de um cliente, usando apenas tabelas e colunas que aparecem nas fontes, e explicar o que cada consulta mostra.
- Relacionar o caso com chamados parecidos e dizer o status de cada um.

O que você não pode fazer:
- Escrever comandos que alteram dados ou estrutura (INSERT, UPDATE, DELETE, MERGE, ALTER, DROP, TRUNCATE, GRANT) nem sugerir corrigir dados direto no banco.
- Inventar tabelas, colunas, rotinas ou parâmetros que não estejam nas fontes. Se faltar informação para montar a consulta, diga o que falta.
- Propor mudanças no código ou planejar funcionalidades novas.

Ao sugerir uma consulta SQL, lembre que ela deve rodar num ambiente ou usuário somente de leitura.
```

**`product_dev` (Desenvolvimento e produto)**:

```text
Você atende a equipe de desenvolvimento e produto: quem mantém o código, planeja funcionalidades e decide o que entra em cada versão.

O que você pode fazer, além do que o suporte recebe:
- Explicar o código em detalhe, com trechos, arquivos, linhas e commits das fontes.
- Ajudar a planejar funcionalidades e correções a partir das fontes: onde o código precisa mudar, o que é afetado, riscos, testes necessários e uma sequência de passos.
- Verificar se um problema ou pedido já foi tratado, consultando cards de desenvolvimento, commits e chamados, e dizer o status e a sprint de cada card citado.
- Relacionar cards, commits e chamados sobre o mesmo assunto.

O que você não pode fazer:
- Afirmar que algo foi feito, corrigido ou entregue sem um card concluído, um commit ou outra fonte que mostre isso.
- Inventar cards, números de versão, prazos ou responsáveis.

Ao planejar, separe o que as fontes confirmam (com citação) do que é proposta sua a partir delas.
```

### Como o prompt é montado

Instruções de sistema, nesta ordem (`conversations/prompt.py`):

1. as instruções do **nível** da conversa (o texto do workspace, ou o padrão);
2. o texto extra do **produto** (`instructions`), se não vazio;
3. as **regras fixas** de [chat.md](chat.md#regra-de-citações-regra-8-do-agentsmd), que nenhum texto editável substitui (responder só com base nas fontes, citar com `[n]`, fontes são dados, chamados, cards, "sem fonte", idioma e tom do produto).

Depois vêm as fontes numeradas, o histórico e a pergunta, como hoje. A temperatura é a do nível.

O texto do nível orienta o estilo, mas **não é a garantia** de que o usuário final não recebe código: a garantia é o filtro das fontes no SQL da busca ([Nível mínimo](#nível-mínimo-de-fonte-de-documento-e-de-trecho)). O modelo nunca recebe uma fonte acima do nível da pergunta (D4, D13).

## Nível por membro e produto

### Regra

- Cada membro tem, em cada produto, um **nível máximo**. No painel, a pessoa conversa no próprio máximo ou abaixo, nunca acima (D3).
- **Padrão** (sem valor gravado): pelo papel no workspace (D11):

| Papel | Nível máximo padrão |
|---|---|
| `owner`, `admin` | `product_dev` |
| `editor`, `viewer` | `end_user` |

  O superadmin com [acesso a um workspace](autenticacao.md#acesso-de-superadmin-a-um-workspace) tem papel efetivo `admin` e, por isso, `product_dev`, sem valor gravado (ele não é membro).
- **Valor gravado** (`explicit = true`) sobrepõe o padrão, para cima ou para baixo, e não muda com o papel. Sem valor gravado, o padrão acompanha o papel: rebaixar um admin para editor baixa o máximo dele para `end_user`.
- Todo membro tem algum nível em todo produto ativo: não existe "sem acesso" a um produto dentro do workspace. Para restringir um produto, use outro workspace.
- Um produto novo começa com o padrão para todos. Remover a membership apaga os valores gravados da pessoa.

### Rotas

Sob `/v1/workspaces/{workspace_id}` (`api/member_levels.py`):

**`GET .../member-levels`** (admin): a tabela membro × produto da tela **Membros**. Paginada como `GET .../members` (`limit` padrão 50, máximo 200; `offset`; `total`), com os mesmos `query`, `role` e `sort`. Resposta `MemberLevelsPage`:

```json
{
  "products": [{"id": "…", "name": "ERP", "active": true}],
  "items": [
    {
      "user_id": "…", "name": "Ana Souza", "email": "ana@exemplo.com.br", "role": "editor",
      "levels": [{"product_id": "…", "max_level": "support", "explicit": true}]
    }
  ],
  "total": 1, "limit": 50, "offset": 0
}
```

`products` traz todos os produtos (ativos e inativos), por nome; cada item traz um nível por produto, na mesma ordem. Número constante de statements (membros da página, produtos e valores gravados).

**`PUT .../members/{user_id}/product-levels`** (admin, CSRF): corpo `{"levels": [{"product_id": "uuid", "max_level": "support" | null}]}`, de 1 a 200 itens, sem produto repetido. `max_level: null` apaga o valor gravado (volta ao padrão do papel). Produtos fora do corpo ficam como estão. Resposta 200 com o item do membro (o formato de `items[]` acima).

| Erro | Quando |
|---|---|
| 404 `not_found` | O usuário não é membro do workspace. |
| 403 `role_not_allowed` | O membro tem papel acima do de quem edita (`details.max_role`), como na gestão de membros. |
| 422 `member_level_product_invalid` | Produto inexistente ou de outro workspace (`details.product_ids`). |
| 422 `validation_error` | Corpo inválido, nível desconhecido, lista vazia ou repetida. |

Quem lê o próprio nível: `my_max_level` em `GET .../products` e `product_levels` em `GET /v1/me` ([autenticacao.md](autenticacao.md#nível-por-produto-no-v1me)).

### Convites com nível

`POST .../invites` aceita `product_levels` opcional, no mesmo formato dos itens do `PUT` (sem `null`; até 200; produto do workspace, senão 422 `invite_product_invalid`). Os valores ficam no convite e viram valores gravados na mesma transação do aceite; um produto excluído nesse meio tempo é ignorado. Sem `product_levels`, vale o padrão do papel do convite. Reconvidar substitui o convite inteiro, inclusive os níveis. `GET .../invites` devolve `product_levels` de cada convite. Detalhes em [autenticacao.md](autenticacao.md#convites).

## Nível mínimo de fonte, de documento e de trecho

### Regra

Cada trecho do índice tem um **nível mínimo**: a pergunta só recebe trechos com `nível mínimo ≤ nível da pergunta` (D4). Ele é o **maior** entre três valores:

1. **O da fonte** (`sources.min_level`, obrigatório): padrão pelo tipo, alterável pelo admin.
2. **O do documento** (`documents.min_level`, opcional): refinamento automático do conector, nunca editável pela API (D13).
3. **O do trecho** (`chunks.meta.min_level`, opcional): refinamento automático do chunking.

O refinamento só **sobe** o nível: baixar a fonte nunca expõe um documento ou trecho que o conector marcou mais alto.

### Padrões por tipo

| Fonte (`kind`) | Nível mínimo padrão da fonte | Refinamento automático |
|---|---|---|
| `folder` (pastas de documentos) | `end_user` | Documento que o parsing trata como **código** (`ParsedKind.CODE`: extensões de `CODE_LANGUAGES` em `ingestion/parsing.py`, com ou sem gramática do tree-sitter, inclusive SQL e scripts): `product_dev`. Assim uma pasta com código não entrega código ao usuário final. |
| `runner` (conhecimento do harness) | `end_user` | Item com `confidence = inferido`: documento `support`; `revisado`: sem refinamento (`end_user`). No Markdown do item, o trecho da seção `## Evidências` (caminhos e excertos de código) tem `meta.min_level = support`, e o chunking nunca junta essa seção com outra no mesmo trecho. |
| `tickets` (chamados) | `support` | Nenhum. |
| `cards` (cards de desenvolvimento, [cards.md](cards.md)) | `product_dev` | Nenhum. |
| `git` (código e commits) | `product_dev` | Nenhum. |

Aprovar um item de conhecimento muda a confiança e, por isso, reindexa o documento ([indexacao.md](indexacao.md#conhecimento-do-harness)); o nível dele cai de `support` para o da fonte. Reabrir faz o caminho inverso.

### Citação de conhecimento no nível `end_user`

A citação `kind: knowledge` carrega as evidências (caminhos, linhas e excertos de código). Numa resposta no nível `end_user`, a citação vai com `evidence: null`, mesmo quando o trecho citado é de um item revisado. Nos níveis `support` e `product_dev`, vai como hoje. A regra vale no fio, na gravação da mensagem e na API pública.

### Quem muda e o que acontece

- `sources.min_level` aparece em `SourceOut` com `min_level_is_default` (igual ao padrão do tipo). `POST .../sources` aceita `min_level` opcional (omitido = padrão do tipo) e `PATCH .../sources/{id}` aceita `min_level`.
- **Só owner e admin** criam fonte com nível diferente do padrão ou mudam o nível de uma fonte (403 `forbidden` com `details.required_role = admin` para o editor, que continua editando os outros campos). O nível é uma regra de acesso, como as chaves e os níveis dos membros.
- A mudança vale **na hora, sem reindexar**: na mesma transação do `PATCH`, o servidor recalcula `chunks.min_level` de todos os trechos da fonte (o maior entre o novo nível da fonte, `documents.min_level` e `chunks.meta.min_level`) numa instrução. Nenhum embedding é recalculado. Fontes de chamados e de cards já apagaram o bruto, então reindexar não seria possível.
- Auditoria: `source.min_level_changed` com `name`, `from` e `to`.
- O painel avisa ao subir o nível de uma fonte em uso por algum produto (os níveis abaixo deixam de vê-la) e ao baixar (os níveis abaixo passam a vê-la).

### O filtro na busca

`SearchService.search` recebe o nível da pergunta e o aplica **no SQL dos dois braços**, antes da fusão e antes de montar o contexto (D13):

- braço vetorial: `WHERE … AND chunks.min_level = ANY(:allowed_levels)`;
- braço textual: a mesma condição;
- `:allowed_levels` = os níveis de `end_user` até o da pergunta (`{end_user}`, `{end_user, support}` ou os três).

Nunca se filtra depois da busca: um trecho acima do nível não entra nos candidatos, na fusão, nas citações nem no contexto do LLM. Os testes provam isso nos dois braços e na fusão (F2.2), com número constante de statements. O `hnsw.ef_search` de 1000 já compensa o filtro extra aplicado depois do índice ([indexacao.md](indexacao.md#busca-híbrida)).

A rota "testar busca" das coleções (`POST .../collections/{id}/search`) passa a exigir **editor** (era qualquer membro, e um leitor com nível `end_user` leria trechos de código por ela) e aceita `level` (padrão `product_dev`, tudo). Quem gerencia fontes vê o conteúdo delas nas telas de administração; os níveis governam o chat e a API.

## Chat com produto e nível

### No painel

- **`POST /v1/workspaces/{workspace_id}/conversations`** (viewer, CSRF): corpo `{"product_id": "uuid", "level": "support"}`. `level` é opcional; omitido, vale o nível máximo de quem pergunta no produto. Resposta 201 com a conversa, que guarda `product_id` e `level`.
- **O nível é da conversa**: fica fixo do início ao fim. Para mudar de nível, a pessoa abre outra conversa. Cada mensagem grava também `product_id` e `level` (para uso e custos).
- **A cada pergunta** (`POST .../conversations/{id}/messages`), na fase 1 e antes do embedding, o servidor confere de novo: produto ativo (409 `product_inactive`), nível configurado (409 `level_not_configured`) e `level ≤ nível máximo atual` de quem pergunta. Se o admin baixou o máximo depois, a conversa continua legível, mas a pergunta recebe 403 `level_not_allowed`.
- A busca usa as coleções e a similaridade mínima do produto e o nível da conversa; o LLM usa a credencial, o modelo, a temperatura e as instruções do nível, mais o texto do produto.

| Erro | HTTP | `details` | Quando |
|---|---|---|---|
| `level_not_allowed` | 403 | `{"requested_level", "max_level", "reason"}` | Nível acima do máximo. `reason`: `member` (painel), `api_key` (chave) ou `public_channel` (canal público). |
| `level_not_configured` | 409 | `{"level"}` | O nível não tem credencial e modelo no workspace. |
| `product_inactive` | 409 | `null` | Produto desativado. |
| `not_found` | 404 | `null` | Produto inexistente ou, para o leitor, inativo. |
| `validation_error` | 422 | `[{loc, problem}]` | Nível desconhecido ou corpo inválido. |

Leitura: `ConversationOut` e `ConversationSummary` trazem `product_id`, `product_name` e `level` (no lugar de `assistant_id` e `assistant_name`); `GET .../conversations` aceita os filtros `product_id` e `level`. Eventos SSE em [chat-sse.md](chat-sse.md) (v0.9).

### Na API pública

A chave define os produtos (`product_ids`) e o nível máximo (`max_level`); cada requisição informa o produto e, se quiser, o nível (D8). Sem nível, vale o `max_level` da chave. Contrato em [api-publica.md](api-publica.md#chaves-escopo-e-nível-máximo).

### Canal público

Um canal é **público** quando quem pergunta não está identificado (o widget embutível e qualquer canal futuro sem login). No núcleo (`levels/policy.py`), o teto efetivo de uma pergunta é:

```text
teto = mínimo(teto do principal, teto do canal)
teto do principal = nível máximo do membro no produto (painel) ou max_level da chave (API)
teto do canal     = end_user, se o canal é público; senão, sem limite
```

Os canais `panel`, `api` e `mcp` (o servidor MCP, com a chave; [mcp.md](mcp.md#produto-e-nível)) não são públicos; o `widget` é ([widget.md](widget.md#nível-sempre-end_user), plano 0010). Um canal público que pede `support` ou `product_dev` recebe 403 `level_not_allowed` com `reason: public_channel`, mesmo que a chave usada por ele tenha `max_level` maior. A regra e o teste ficam prontos neste plano, com um canal público fake; o widget e os canais entram depois.

## Migração dos assistentes

A migração `0018` (F1.2) transforma, numa transação, cada assistente num produto (D9):

| Antes | Depois |
|---|---|
| `assistants` (cada linha) | `products` com o **mesmo `id`**, `name`, `description`, `instructions` = `system_prompt`, `language`, `tone`, `no_source_message`, `min_similarity`, `active`, `ticket_webhook_url`, `ticket_webhook_secret_ciphertext` e `ticket_webhook_secret_created_at`. O segredo não é recifrado: como o id se preserva, os dados associados continuam `assistant_ticket_webhook:<workspace_id>:<id>` (o rótulo antigo fica, documentado em [modelo-de-dados.md](modelo-de-dados.md)), e a migração não precisa da `KNOBRIDGE_SECRET_KEY`. Um nome terminado em `:end_user`, `:support` ou `:product_dev` tem o último `:` trocado por ` - `. |
| `assistant_collections` | `product_collections`, mesmos pares. |
| `assistants.credential_id`, `model`, `temperature` | Os três níveis do workspace recebem a credencial, o modelo e a temperatura do **assistente mais usado** do workspace (mais respostas com `model` preenchido; empate pelo mais antigo, depois pelo id). Sem assistentes, os três ficam sem modelo. As instruções dos níveis ficam no padrão (nulas). |
| `conversations.assistant_id` | `conversations.product_id` (mesmo valor) e `level = product_dev`. |
| `messages` | `product_id` (o da conversa) e `level = product_dev`. |
| `api_keys.assistant_ids` | `api_keys.product_ids` (mesmos valores) e `max_level = product_dev`. |
| `ticket_requests.assistant_id` | `ticket_requests.product_id`. |
| Membros | Nenhum valor gravado: vale o padrão do papel (D11). |
| `sources` | `min_level` = padrão do tipo; `documents.min_level` e `chunks.min_level` calculados pelas regras de refinamento (código detectado nas pastas, confiança dos itens de conhecimento, seção de evidências). |

Por que `product_dev` nas conversas e chaves existentes: até aqui, toda resposta usava todas as fontes, o que equivale a `product_dev`. Gravar outro nível mentiria sobre o que foi respondido, e as integrações em uso continuam recebendo as mesmas fontes. O admin baixa o `max_level` de cada chave depois, se quiser. Um membro cujo máximo ficou abaixo continua lendo as conversas antigas, mas pergunta numa conversa nova.

O `downgrade` é recusado (falha) se houver produto criado depois da migração, conversa com nível diferente de `product_dev`, fonte `cards` ou valor gravado de nível; sem isso, desfaz o mapeamento acima, voltando o modelo do nível `product_dev` para todos os assistentes.

## Compatibilidade das rotas antigas

Decisão: **as rotas de assistentes do painel são removidas** na mesma entrega; **a API pública mantém a compatibilidade**.

| Rota antiga | Destino |
|---|---|
| `/v1/workspaces/{wid}/assistants…` (CRUD, duplicar, webhook) | Removidas. Substituídas por `/v1/workspaces/{wid}/products…`. Respondem 404. |
| Filtro `assistant_id` em `.../admin/conversations`, `group_by=assistant` em `.../usage` | Removidos; no lugar, `product_id`, `level`, `group_by=product` e `group_by=level`. Valor antigo: 422 `validation_error`. |
| `POST /v1/conversations` (API pública) com `assistant_id` | **Aceito** como sinônimo obsoleto de `product_id` (os ids são os mesmos). Mandar os dois dá 422. A resposta traz `product_id` e também `assistant_id` (mesmo valor), marcado como obsoleto no OpenAPI. |
| `model` = nome ou id do assistente (API compatível com OpenAI) | **Continua valendo**: é o nome ou o id do produto, sem nível (vale o `max_level` da chave). |
| Payload do webhook de chamado | Ganha `product` e `level`; mantém `assistant` com os mesmos `id` e `name`, obsoleto. `version` continua 1 (mudança aditiva). |

Por quê: as rotas `/assistants` são de sessão e só o painel, que muda na mesma entrega (F3.1), as chama; mantê-las exigiria traduzir `provider_id`, `model` e `temperature` de um assistente para os níveis do workspace, que não têm mais essa forma. A API pública e o webhook são contratos com sistemas de terceiros, que não mudam junto com o KnoBridge; como os ids e os nomes se preservam, manter o sinônimo custa uma linha de validação. Os campos obsoletos saem numa versão futura, anunciada no `CHANGELOG.md`.

## Papéis

| Ação | Papel mínimo |
|---|---|
| Listar e ler produtos | viewer (leitor só vê ativos) |
| Criar, editar, duplicar, excluir produto; testar o webhook | editor |
| Gerar o segredo do webhook | admin |
| Ler e editar a configuração dos níveis | admin |
| Ler a tabela de níveis dos membros e editar o nível de um membro | admin (respeitando `role_not_allowed`) |
| Convidar com nível | admin (como convidar) |
| Mudar o nível mínimo de uma fonte, ou criar fonte com nível diferente do padrão | admin |
| "Testar busca" numa coleção | editor |
| Conversar num produto | viewer, até o próprio nível máximo |

Matriz completa em [autenticacao.md](autenticacao.md#matriz-de-permissões).

## Auditoria

| Evento | Quando | `details` |
|---|---|---|
| `product.created` | Criar ou duplicar | `name`, `collection_ids`, `duplicated_from` (só ao duplicar) |
| `product.updated` | Editar | `name`, `fields` (nomes dos campos alterados; nunca o texto das instruções nem a URL do webhook) |
| `product.deleted` | Excluir | `name`, `conversation_count` |
| `product.ticket_webhook_secret_rotated` | Gerar segredo | `name` |
| `product.ticket_webhook_tested` | Testar webhook | `name`, `ok`, `status`, `error_code` |
| `workspace_level.updated` | `PATCH .../levels/{level}` | `level`, `fields`, `provider_id` e `model` (quando mudaram); nunca o texto das instruções |
| `member_level.updated` | `PUT .../members/{id}/product-levels` | `user_id`, `changes` (`[{product_id, from, to}]`, com `null` para "padrão") |
| `source.min_level_changed` | Mudar o nível mínimo de uma fonte | `name`, `from`, `to` |
| `invitation.created` | Convidar | os campos de hoje mais `product_levels` |
| `api_key.created`, `api_key.updated` | Chaves | os campos de hoje com `product_ids` e `max_level` no lugar de `assistant_ids` |

Na trilha do workspace, com `target_type` = `product`, `workspace_level`, `membership`, `source`, `invitation` ou `api_key`. Os eventos antigos `assistant.*` continuam na trilha como foram gravados.

## Referências

- [ADR 0008](../adr/0008-produtos-e-niveis.md) e [plano 0009](../planos/0009-produtos-e-niveis.md).
- pgvector, filtragem com índices aproximados: <https://github.com/pgvector/pgvector#filtering>
