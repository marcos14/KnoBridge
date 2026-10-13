# Produtos e níveis de resposta

> Rascunho v0.1 · 2026-10-13 · Em uso (plano 0009)

Passo a passo para organizar as respostas por **produto** (o sistema sobre o qual as pessoas perguntam, como "ERP" ou "Portal do Cliente") e por **nível de resposta** (quanto detalhe técnico a resposta pode ter e quais fontes ela usa): configurar os três níveis do workspace, criar produtos, definir o nível máximo de cada membro, ajustar o nível mínimo das fontes, conversar num nível e chamar um produto num nível pela API.

Contrato em [produtos-e-niveis.md](../specs/produtos-e-niveis.md); decisão de arquitetura no [ADR 0008](../adr/0008-produtos-e-niveis.md). Os produtos substituem os antigos assistentes: quem já tinha assistentes encontra cada um como produto, com o mesmo nome e o mesmo id (abaixo, [Workspaces que tinham assistentes](#workspaces-que-tinham-assistentes)).

## Os três níveis

| Nível (painel) | Nome técnico | Para quem | Recebe |
|---|---|---|---|
| Usuário final | `end_user` | Quem usa o sistema | Como usar, passo a passo e dúvidas de fluxo. Nunca código nem SQL. |
| Suporte | `support` | Equipe de suporte | Tudo do usuário final, mais exemplos curtos de código, validações e consultas SQL só de leitura. |
| Desenvolvimento e produto | `product_dev` | Desenvolvimento e produto | Tudo dos anteriores, mais planejamento de funcionalidades e verificação de cards já tratados. |

O nível de uma pergunta decide três coisas: **as fontes** (só trechos com nível mínimo igual ou abaixo, filtrados na própria busca), **as instruções** (o texto do nível mais o texto extra do produto) e **o modelo** (credencial e modelo do nível). A garantia de que o usuário final não recebe código é o filtro das fontes, não o texto das instruções: o modelo nunca vê um trecho acima do nível da pergunta.

## Pré-requisitos

- O ambiente rodando ([subir-ambiente.md](subir-ambiente.md)) e um workspace em que você é owner ou admin ([primeiro-acesso.md](primeiro-acesso.md)).
- Um provedor de LLM cadastrado em **Provedores** (em desenvolvimento, o `fake`, com o modelo `fake-chat`).
- Para respostas com fonte: uma coleção com fontes sincronizadas ([indexar-uma-fonte.md](indexar-uma-fonte.md)).

## Passos

### 1. Configurar os níveis de resposta

Precisa de papel administrador ou acima. Um workspace novo nasce com os três níveis **sem modelo**, e nenhum produto responde num nível sem modelo ("O nível … ainda não foi configurado neste workspace").

1. Vá em **Configurações** e desça até **Níveis de resposta**. Há um cartão por nível.
2. Em cada cartão, escolha a **Credencial** e informe o **Modelo** (com o `fake`, `fake-chat`; com um provedor real, o identificador exato, como `gpt-4.1-mini`; a caixa sugere os modelos conhecidos do tipo da credencial). Ajuste a **Temperatura** se quiser (padrão 0,2).
3. **Instruções do nível**: o texto padrão do KnoBridge para o nível já vem preenchido e recebe as melhorias das próximas versões enquanto não for editado. Edite para o seu caso; **Restaurar padrão** volta ao texto do KnoBridge ao salvar.
4. Clique em **Salvar nível**. Aparece "Nível … atualizado." e o selo **Configurado**.

Cada cartão mostra o **Custo estimado por resposta** (referência de 4.000 tokens de entrada e 600 de saída), para comparar um modelo mais barato no usuário final com um mais capaz no desenvolvimento. Modelo sem preço conhecido mostra "Sem preço conhecido para este modelo."; para acrescentar preços, veja `KNOBRIDGE_CHAT_PRICES` em [primeiro-acesso.md](primeiro-acesso.md#10-acompanhar-o-uso-e-os-custos).

Escolher **Nenhuma (nível desligado)** na credencial desliga o nível: as perguntas nele passam a ser recusadas. Uma credencial em uso por algum nível não pode ser excluída.

### 2. Criar um produto

Precisa de papel editor ou acima.

1. Vá em **Produtos** e clique em **Novo produto**.
2. Preencha **Nome** (ex.: `ERP`; único no workspace e sem terminar em `:end_user`, `:support` ou `:product_dev`, porque o nome é o `model` da API) e, se quiser, **Descrição**.
3. Marque as **Coleções** em que o produto busca. Sem coleção, ele responde sempre "sem fonte".
4. **Texto extra** (opcional): instruções próprias do produto, acrescentadas depois das do nível da conversa (ex.: "Os módulos se chamam Faturamento, Estoque e Financeiro").
5. Os demais campos têm padrão: idioma `pt-BR`, tom neutro, similaridade mínima 0,35, ativo. **Mensagem quando não há fonte** em branco usa a mensagem padrão.
6. Clique em **Salvar**.

O produto não tem modelo nem temperatura: vêm do nível da conversa. Na lista, **Duplicar** copia a configuração e as coleções (o webhook vai sem segredo); **Excluir** apaga também as conversas do produto (para guardar o histórico, desative). O webhook de "Abrir chamado" fica no próprio produto ([receber-chamados-por-api.md](receber-chamados-por-api.md#9-receber-abrir-chamado-do-chat)).

### 3. Definir o nível máximo de cada membro

Precisa de papel administrador ou acima. Cada membro tem, em cada produto, um **nível máximo**: no chat, ele conversa nesse nível ou abaixo. Sem nada escolhido, vale o padrão do papel:

| Papel | Nível máximo padrão |
|---|---|
| Proprietário, Administrador | Desenvolvimento e produto |
| Editor, Leitor | Usuário final |

O superadmin que **entra** num workspace tem papel efetivo de administrador e, por isso, Desenvolvimento e produto.

1. Vá em **Membros > Níveis por produto**. Há uma coluna por produto e uma linha por membro; cada célula mostra o nível explícito ou "Padrão do papel: …".
2. Escolha o nível na célula. A mudança vale na próxima pergunta. Para voltar ao padrão, escolha a opção **Padrão do papel: …**.

Um nível escolhido não muda com o papel; o padrão acompanha o papel (rebaixar um admin para editor baixa o padrão dele para Usuário final). Quem tem papel acima do seu aparece só para leitura.

Para já convidar com nível: em **Membros > Convidar**, preencha **Nível por produto (opcional)**. Os níveis valem a partir do aceite; em branco, vale o padrão do papel do convite.

### 4. Ajustar o nível mínimo das fontes

Cada fonte tem um **nível mínimo**: só as perguntas nesse nível ou acima usam os trechos dela. O padrão depende do tipo:

| Tipo de fonte | Nível mínimo padrão | Refinamento automático |
|---|---|---|
| Pasta | Usuário final | Arquivo de código (extensões de linguagem, inclusive SQL e scripts) sobe para Desenvolvimento e produto. |
| Runner local (conhecimento do harness) | Usuário final | Item **inferido** sobe para Suporte; a seção de evidências (caminhos e excertos de código) é sempre Suporte. |
| Chamados | Suporte | Nenhum. |
| Cards de desenvolvimento | Desenvolvimento e produto | Nenhum. |
| Repositório Git | Desenvolvimento e produto | Nenhum. |

Assim, uma pasta de manuais com alguns arquivos de código entrega os manuais a todos e o código só a desenvolvimento e produto, sem configuração.

Só owner e admin mudam o nível mínimo:

1. Em **Fontes**, ao criar (**Nova fonte**) ou editar uma fonte, escolha o **Nível mínimo**. A opção "(padrão)" é a do tipo.
2. Ao mudar o nível de uma fonte com documentos, o painel avisa quem deixa (ou passa) a usar os trechos. Clique em **Salvar**.

A mudança vale na hora, sem reindexar. O refinamento automático só **sobe** o nível: baixar a fonte para Usuário final não expõe o código de uma pasta. A lista de **Fontes** mostra o nível de cada uma e filtra por nível. O editor vê o nível, mas não o muda.

### 5. Conversar num nível

1. Vá em **Chat**. Escolha o **Produto** (só os ativos) e o **Nível de resposta**: o padrão é o seu máximo no produto; os níveis acima dele aparecem desabilitados, com o motivo.
2. Escreva a pergunta e envie. A conversa mostra o selo **Nível: …**.

O nível é da conversa: fica fixo do início ao fim. Para perguntar em outro nível, abra uma **Nova conversa**. Se um admin baixar o seu máximo depois, as conversas antigas continuam legíveis, mas as acima do novo máximo não aceitam mais perguntas. A lista de conversas filtra por produto e por nível; **Conversas** (owner e admin) também.

Exemplo: a mesma pergunta "Como emitir a segunda via do boleto?" num produto com um manual (`.md`), um arquivo de código e uma consulta SQL marcada como Suporte cita só o manual em Usuário final, o manual e a consulta em Suporte, e os três (mais os cards, se houver) em Desenvolvimento e produto.

### 6. Chamar um produto num nível pela API

1. Em **Chaves de API > Nova chave**, escolha os **Produtos** (todos os ativos ou só alguns) e o **Nível máximo** da chave. O painel pré-seleciona **Usuário final**: suba de propósito, só para integrações internas.
2. Na REST própria, crie a conversa com `product_id` e, se quiser, `level` (sem `level`, vale o máximo da chave).
3. Na API compatível com OpenAI, o `model` é `<produto>` ou `<produto>:<nível>`, como `ERP` ou `ERP:support`. `GET /v1/models` lista o produto e uma entrada por nível até o máximo da chave.

Nível acima do máximo da chave é recusado com 403 `level_not_allowed`. Exemplos completos em [usar-a-api.md](usar-a-api.md).

## Como verificar

- **Início**: o passo "Configure a credencial e o modelo do nível Usuário final" sai da lista depois do passo 1, e "Crie um produto ativo ligado a uma coleção" depois do passo 2.
- **Chat**: um leitor vê Suporte e Desenvolvimento e produto desabilitados; um owner vê os três.
- **Uso e custos**: **Agrupar por > Produto** ou **Nível** mostra respostas, tokens e custo de cada um; os filtros de produto e nível valem para as respostas do chat.
- **Auditoria**: `workspace_level.updated`, `product.created`, `member_level.updated` e `source.min_level_changed`.

## Workspaces que tinham assistentes

A atualização (migração `0018`) transforma cada assistente num produto com o **mesmo id e o mesmo nome**; as instruções do assistente viram o **Texto extra** do produto. Os três níveis do workspace recebem a credencial, o modelo e a temperatura do assistente mais usado. Conversas e chaves de API existentes ficam no nível **Desenvolvimento e produto** (até então toda resposta usava todas as fontes), então as integrações em uso continuam recebendo as mesmas fontes: revise o **Nível máximo** de cada chave em **Chaves de API** e baixe o que não precisa de código. Os membros ficam no padrão do papel.

O `model` com o nome ou o id do assistente continua valendo na API compatível com OpenAI, e `assistant_id` continua aceito na REST como sinônimo obsoleto de `product_id`. A tela **Assistentes** virou **Produtos** (o endereço antigo redireciona).

## Como desfazer

- Para desligar um nível, escolha **Nenhuma (nível desligado)** na credencial dele.
- Para voltar um membro ao padrão, escolha **Padrão do papel: …** na célula dele.
- Para voltar uma fonte ao nível do tipo, escolha a opção "(padrão)".
- Para tirar um produto do chat sem perder o histórico, desmarque **Ativo**.

## Problemas comuns

- **"O nível … ainda não foi configurado neste workspace"** no chat ou 409/400 `level_not_configured` na API: o nível não tem credencial e modelo. Configure em **Configurações > Níveis de resposta** (passo 1).
- **O botão Novo produto não aparece**: não há provedor de LLM no workspace. Cadastre um em **Provedores**.
- **Não consigo escolher Suporte no chat**: o seu nível máximo no produto é Usuário final (padrão de editor e leitor). Peça a um admin para subir em **Membros > Níveis por produto**.
- **"Esta conversa … não aceita novas perguntas"**: o seu máximo baixou depois que a conversa começou. Abra uma nova conversa num nível permitido.
- **A resposta de Usuário final não cita um arquivo que eu esperava**: o arquivo é código (sobe para Desenvolvimento e produto) ou a fonte tem nível mínimo acima. Confira o nível na lista de **Fontes**.
- **O campo Nível mínimo está desabilitado**: só owner e admin mudam o nível de uma fonte.
- **O nome do produto é recusado**: nomes que terminam em `:end_user`, `:support` ou `:product_dev` não são aceitos, porque o `:` indica o nível no `model` da API.
