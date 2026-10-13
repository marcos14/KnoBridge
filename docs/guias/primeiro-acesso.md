# Primeiro acesso: da instância vazia ao primeiro chat

> Rascunho v0.4 · 2026-10-13 · Em uso (planos 0002, 0003, 0008 e 0009)
>
> **Mudanças da v0.4** (plano 0009, F4.1): os assistentes viram **produtos**; o modelo sai do produto e vai para os **níveis de resposta** do workspace, configurados antes do chat; o checklist ganha o passo dos níveis; o chat escolhe produto e nível; convites com nível por produto; Uso e custos agrupado por produto e nível. Detalhes em [produtos-e-niveis.md](produtos-e-niveis.md).
>
> **Mudanças da v0.3** (plano 0008, F4.1): a configuração inicial cria o primeiro workspace, sem convite; o Início com o checklist de primeiros passos; o painel da instância e o "Entrar" do superadmin em qualquer workspace; Uso e custos; acesso pela API em [usar-a-api.md](usar-a-api.md).
>
> **Mudanças da v0.2** (plano 0003, F6.2): o chat responde com citações quando o assistente tem coleção indexada; o passo a passo da indexação está em [indexar-uma-fonte.md](indexar-uma-fonte.md).

Passo a passo para quem acabou de subir o KnoBridge: criar o superadmin e o primeiro workspace, seguir os primeiros passos do Início, criar outros workspaces, convidar pessoas, cadastrar um provedor de LLM, configurar os níveis de resposta, criar um produto, conversar com ele e acompanhar o uso. Em desenvolvimento, tudo funciona sem chave de API real, com o provedor `fake`, e os e-mails (convites, redefinição de senha) são lidos no Mailpit.

Regras de acesso, sessões e convites em [autenticacao.md](../specs/autenticacao.md); funcionamento do chat em [chat.md](../specs/chat.md); produtos e níveis em [produtos-e-niveis.md](../specs/produtos-e-niveis.md).

## Pré-requisitos

- O ambiente de desenvolvimento rodando e saudável, conforme [subir-ambiente.md](subir-ambiente.md):

  ```bash
  docker compose up -d --build --wait
  ```

- Um navegador. Para testar convites com uma segunda pessoa, uma janela anônima ou outro navegador (cada um guarda a própria sessão).
- Painel em <http://localhost:5173> e Mailpit em <http://localhost:8025> (portas padrão; mudam com `FRONTEND_PORT` e `MAILPIT_UI_PORT` no `.env`).

Nenhum e-mail sai para caixas reais: todos caem no Mailpit, e os links apontam para o painel (`KNOBRIDGE_PUBLIC_BASE_URL`). Use endereços fictícios, como `voce@example.test`.

## Passos

### 1. Configuração inicial: superadmin e primeiro workspace

1. Abra <http://localhost:5173>. Com a instância vazia, o painel leva para **Configuração inicial** (`/setup`).
2. Informe nome, e-mail, senha (de 12 a 1024 caracteres) e a confirmação, e em **Nome do workspace** o nome do primeiro workspace (ex.: `Suporte`). Clique em **Criar conta e entrar**.

Essa conta é o **superadmin** da instância, com e-mail já verificado, e é **owner** do workspace criado junto, sem convite nem e-mail. O painel abre direto o **Início** desse workspace (`/w/<id>`). Para mudar o nome depois, use **Configurações** do workspace. A tela de configuração só existe enquanto não há nenhum usuário; depois, quem chega vai para **Entrar** (`/login`).

### 2. O Início e os primeiros passos

O **Início** de cada workspace mostra os números do mês (documentos indexados, fontes ativas, execuções com falha nos últimos 7 dias, conversas e avaliações e, para owner e admin, o custo estimado) e a lista **Primeiros passos**:

1. Cadastre um provedor de LLM (passo 6 deste guia);
2. Crie uma coleção;
3. Adicione uma fonte e sincronize até concluir uma execução;
4. Configure a credencial e o modelo do nível Usuário final (passo 7 deste guia);
5. Crie um produto ativo ligado a uma coleção (passo 8);
6. Faça uma pergunta no chat e receba uma resposta com fonte.

Cada item pendente leva à tela dele (os passos 2 e 3 estão em [indexar-uma-fonte.md](indexar-uma-fonte.md)). Os feitos somem da lista, e a lista some quando tudo está feito. Quem não tem papel para um passo vê "Peça a um administrador do workspace para fazer este passo."

### 3. Painel da instância e outros workspaces

O superadmin vê, no menu, o grupo **Administração da instância**:

- **Painel**: contagens de workspaces e usuários, execuções e respostas com falha nos últimos 7 dias, as falhas recentes, o uso de todos os workspaces no período e a saúde dos serviços (API, banco, Temporal e worker).
- **Workspaces**: criar, renomear, suspender, reativar e **Entrar** (abaixo).
- **Usuários** e **Auditoria da instância**.

Para criar outro workspace:

1. Em **Administração da instância > Workspaces** (`/admin/workspaces`), clique em **Criar workspace** e preencha:
   - **Nome**: por exemplo, `Suporte Interno`;
   - **Identificador (opcional)**: letras minúsculas, números e hífens; em branco, é gerado a partir do nome;
   - **E-mail do proprietário**: o de quem vai cuidar do workspace (pode ser o seu).
2. Clique em **Criar**. O workspace nasce sem membros, e o proprietário recebe um convite por e-mail (no Mailpit, em dev). O superadmin não vira membro.

O proprietário abre o link do convite (`/accept-invitation?token=...`): sem conta, informa nome e senha e clica em **Criar conta e aceitar** (a conta nasce verificada e já entra); com conta, entra primeiro (**Entrar para aceitar**) e clica em **Aceitar convite**. Logado com outro e-mail, o aceite é recusado.

### 4. Entrar num workspace como superadmin

Para administrar um workspace do qual não é membro (ajudar um cliente, conferir uma configuração), o superadmin **entra** nele:

1. Em **Administração da instância > Workspaces**, clique em **Entrar** na linha do workspace (suspenso, reative antes).
2. O painel abre o Início do workspace com a faixa **Acesso de superadmin a <nome>** no topo. Nesse acesso, ele tem papel de **administrador**: tudo que um admin pode, menos conceder o papel de proprietário. Ele não aparece em **Membros** nem recebe e-mails do workspace.
3. Para encerrar, clique em **Sair** na faixa. Entrar em outro workspace ou sair da conta também encerra.

O acesso vale só para a sessão atual (outro navegador não o herda) e fica registrado na auditoria do workspace e na da instância (`superadmin.workspace_entered` e `superadmin.workspace_exited`).

### 5. Convidar outras pessoas (opcional)

1. No workspace, vá em **Membros** e clique em **Convidar**.
2. Informe o e-mail e o **Papel** (`Leitor`, `Editor`, `Administrador` ou `Proprietário`, até o seu). Se já houver produtos, **Nível por produto (opcional)** define o nível máximo da pessoa em cada um; em branco, vale o padrão do papel (owner e admin: Desenvolvimento e produto; editor e leitor: Usuário final). Clique em **Enviar convite**.
3. Abra o link do e-mail no Mailpit numa janela anônima e crie a conta da pessoa convidada.

O que cada papel pode fazer está na [matriz de permissões](../specs/autenticacao.md#matriz-de-permissões). Em resumo: leitor conversa com produtos ativos, até o próprio nível máximo; editor também gerencia provedores, coleções, fontes e produtos; administrador também gerencia membros (e o nível de cada um por produto), convites, configurações (inclusive os níveis de resposta), chaves de API e o nível mínimo das fontes, e vê auditoria e conversas de todos; proprietário é administrador que pode conceder o papel de proprietário. Convites pendentes ficam na mesma tela, com **Reenviar** e **Revogar**; o link vale 7 dias.

### 6. Cadastrar um provedor de LLM

Precisa de papel editor ou acima.

1. Vá em **Provedores** e clique em **Novo provedor**.
2. Em desenvolvimento, sem chave real:
   - **Tipo**: `Fake (testes, sem rede)`;
   - **Nome**: por exemplo, `Fake dev`;
   - **Chave de API**: qualquer texto com 8 caracteres ou mais, por exemplo `fake-key-dev`.
3. Clique em **Salvar** e depois em **Testar conexão** na linha do provedor. Deve aparecer "Conexão com Fake dev funcionando."

O tipo `fake` não faz nenhuma chamada de rede e só é aceito quando `KNOBRIDGE_ENV` é diferente de `production` (o compose de dev usa `local`). A chave é guardada cifrada e nunca volta para a tela; só os 4 últimos caracteres aparecem ([ADR 0003](../adr/0003-segredos-cifrados.md)).

### 7. Configurar os níveis de resposta

Precisa de papel administrador ou acima. Cada pergunta é respondida num de três níveis (**Usuário final**, **Suporte** e **Desenvolvimento e produto**), e é o nível que tem a credencial, o modelo, a temperatura e as instruções. Um workspace novo nasce com os três sem modelo, e o chat recusa perguntas num nível sem modelo.

1. Vá em **Configurações** e desça até **Níveis de resposta**.
2. Em cada um dos três cartões, escolha a **Credencial** cadastrada e informe o **Modelo**: com o provedor `fake`, use `fake-chat`.
3. Deixe a temperatura (0,2) e as instruções padrão do KnoBridge, ou ajuste. Clique em **Salvar nível** em cada cartão.

O passo a passo completo, com o custo estimado por resposta e as instruções de cada nível, está em [produtos-e-niveis.md](produtos-e-niveis.md#1-configurar-os-níveis-de-resposta).

### 8. Criar um produto

Precisa de papel editor ou acima. O produto é o sistema sobre o qual as pessoas perguntam (ex.: `ERP`).

1. Vá em **Produtos** e clique em **Novo produto**.
2. Preencha **Nome** (ex.: `ERP`) e marque as **Coleções** em que ele busca, se já houver (sem coleção, ele responde sempre "sem fonte").
3. Os demais campos têm padrão: idioma `pt-BR`, tom neutro, similaridade mínima 0,35, ativo. **Texto extra** acrescenta instruções do produto às do nível; deixe **Mensagem quando não há fonte** em branco para usar a mensagem padrão.
4. Clique em **Salvar**.

### 9. Conversar

1. Vá em **Chat**, escolha o **Produto** e o **Nível de resposta** (o padrão é o seu máximo no produto; os níveis acima dele ficam desabilitados), escreva a pergunta e clique em **Enviar** (Enter envia; Shift+Enter quebra a linha). O nível fica fixo na conversa: para outro nível, abra uma nova conversa.
2. A resposta chega em streaming. **Enquanto o produto não tiver coleção indexada, ela é sempre a mensagem de "sem fonte"**, marcada como "Respondida sem fonte: o assistente ofereceu abrir chamado.": a regra do produto é não responder sem fonte ([chat.md](../specs/chat.md#regra-de-citações-regra-8-do-agentsmd)). Nesse caso o LLM nem é chamado. Para o produto responder com citações, indexe uma fonte e ligue a coleção a ele, conforme [indexar-uma-fonte.md](indexar-uma-fonte.md). Cada nível só usa as fontes com nível mínimo igual ou abaixo dele: em Usuário final, nunca código ([produtos-e-niveis.md](produtos-e-niveis.md#4-ajustar-o-nível-mínimo-das-fontes)). Para o botão **Abrir chamado** dessas respostas enviar o pedido ao seu sistema de chamados, configure o webhook do produto ([receber-chamados-por-api.md](receber-chamados-por-api.md#9-receber-abrir-chamado-do-chat)).
3. Avalie a resposta com **Resposta útil** ou **Resposta não ajudou** e, se quiser, um comentário.
4. As suas conversas ficam na lista à esquerda do chat, com filtros por produto e nível. Owner e administrador veem as conversas de todos os membros, com filtros e totais, em **Conversas**.

### 10. Acompanhar o uso e os custos

Precisa de papel administrador ou acima.

1. Vá em **Uso e custos**. Escolha o **Período** (**Este mês**, **Mês passado**, **Últimos 30 dias** ou **Personalizado**, em UTC) e **Agrupar por** (dia, fonte, coleção, produto, nível, canal, chave de API ou modelo); os filtros de produto e nível valem para as respostas do chat.
2. Os totais mostram tokens e custo de embeddings (execuções de indexação) e do chat (respostas que chamaram o LLM); a tabela, um grupo por linha, ordenável por coluna; o gráfico, o custo por dia. **Exportar CSV** baixa a mesma visão.

Os valores em US$ são **estimativas** do KnoBridge, calculadas com tabelas de preço, não a fatura do provedor. Modelo sem preço conhecido (como o `fake`) tem os tokens contados, mas o custo fica de fora, com o aviso **Custo parcial**. Para acrescentar ou corrigir preços de chat, defina `KNOBRIDGE_CHAT_PRICES` no `.env` (exemplo no `.env.example`) e recrie a stack com `docker compose up -d --wait`; mudar a tabela não recalcula o passado ([uso-e-custos.md](../specs/uso-e-custos.md#preços-do-chat)).

Para chamar os produtos de outro sistema, com uma chave de API (com nível máximo), pela REST ou pelo SDK da OpenAI, siga [usar-a-api.md](usar-a-api.md).

### 11. Usar um provedor real (OpenAI, Anthropic ou OpenRouter)

1. Em **Provedores > Novo provedor**, escolha o **Tipo** (`OpenAI`, `Anthropic` ou `OpenRouter`), dê um nome e cole a sua chave de API. **URL base** fica em branco, a menos que use um servidor compatível (ex.: Ollama, vLLM) ou um gateway.
2. Clique em **Testar conexão**: o KnoBridge faz a chamada autenticada mais barata do provedor (listar modelos) e mostra o resultado. Erros comuns: chave recusada, limite de uso, provedor fora do ar.
3. Em **Configurações > Níveis de resposta**, troque a **Credencial** de cada nível e informe o **Modelo** com o identificador exato usado pelo provedor (por exemplo, `gpt-4.1-mini` na OpenAI; para Anthropic e OpenRouter, o identificador da documentação deles). Cada nível pode ter o seu modelo: um mais barato em Usuário final, um mais capaz em Desenvolvimento e produto.

Enquanto o produto não tiver coleção com trechos relevantes, o chat continua respondendo "sem fonte" sem chamar o provedor. Para embeddings (coleções), use OpenAI ou OpenRouter: a Anthropic não oferece embeddings ([indexar-uma-fonte.md](indexar-uma-fonte.md)). Use chaves reais só na sua máquina ou num ambiente protegido, e nunca as commite. Lembre que as chaves gravadas dependem de `KNOBRIDGE_SECRET_KEY`: trocar esse segredo exige recadastrar as chaves dos provedores ([ADR 0003](../adr/0003-segredos-cifrados.md)).

## Como verificar

- O **Início** mostra os primeiros passos que faltam; com tudo feito, a lista some.
- **Administração da instância > Auditoria da instância** mostra `setup.completed`, os logins, a criação dos workspaces e as entradas de superadmin; **Auditoria** do workspace (owner/admin) mostra o convite aceito, o provedor, o teste de conexão, os níveis (`workspace_level.updated`) e o produto.
- **Conversas** (owner/admin) lista a conversa do passo 9, com o produto, o nível e a avaliação dada.
- Pela API, com o mesmo navegador logado: `http://localhost:5173/v1/me` devolve o seu usuário e os workspaces com o papel em cada um e o seu nível máximo em cada produto (`product_levels`).

## Outros fluxos de conta

- **Esqueci a senha**: em **Entrar**, clique em **Esqueci minha senha**, informe o e-mail e abra o link no Mailpit (vale 1 hora). Redefinir encerra todas as sessões da conta.
- **Verificar e-mail**: contas criadas por convite e o superadmin já nascem verificados. Para reenviar o link de verificação, use **Perfil** (menu do usuário). Hoje a verificação é informativa: nenhuma tela exige e-mail verificado.
- **Sessões**: **Segurança** (menu do usuário) troca a senha, lista as sessões ativas e encerra uma ou todas.

## Como desfazer

Para voltar à instância vazia (apaga banco, usuários, workspaces e conversas):

```bash
docker compose down -v
docker compose up -d --build --wait
```

Sem apagar tudo: o superadmin pode suspender workspaces e usuários em **Administração da instância**, e o workspace pode excluir produtos e provedores (um provedor em uso por um nível de resposta ou por uma coleção não pode ser excluído).

## Problemas comuns

- **O e-mail não chegou ao Mailpit**: veja "E-mail não aparece no Mailpit" em [subir-ambiente.md](subir-ambiente.md#problemas-comuns). O envio acontece depois da resposta da API; falhas só aparecem no log da `api` (`email_delivery_failed`).
- **"Muitas tentativas" no login**: depois de 5 senhas erradas para o mesmo e-mail e IP em 15 minutos, o login fica bloqueado até a janela acabar, mesmo com a senha certa. Em dev, espere ou recrie o ambiente.
- **O link do convite diz que é inválido**: o link vale 7 dias, deixa de valer quando o convite é reenviado (vale só o mais novo) ou revogado, e não funciona com o workspace suspenso. Peça um novo em **Membros > Reenviar**.
- **Aceitar convite recusa o meu login**: você está logado com outro e-mail. Saia (menu do usuário > **Sair**) ou use uma janela anônima.
- **O tipo `Fake` é recusado ao salvar o provedor**: a API está com `KNOBRIDGE_ENV=production`. Use um provedor real ou um ambiente de desenvolvimento.
- **Não vejo Provedores, Produtos, Conversas ou Uso e custos no menu**: o menu mostra só o que o seu papel permite (editor para provedores e produtos; administrador para conversas, uso e custos, chaves de API, configurações e auditoria). O superadmin que não é membro precisa **Entrar** no workspace (passo 4).
- **O custo aparece como "Custo parcial"**: há respostas ou execuções com modelo sem preço na tabela. Para modelos de chat, acrescente o preço em `KNOBRIDGE_CHAT_PRICES` (passo 10).
- **O chat diz que não há produto disponível**: não há produto ativo no workspace. Crie um ou reative-o em **Produtos**.
- **O chat diz que o nível ainda não foi configurado**: o nível da conversa não tem credencial e modelo. Configure em **Configurações > Níveis de resposta** (passo 7).
- **O botão Novo produto não aparece**: não há provedor de LLM no workspace (passo 6).
- **Não consigo escolher Suporte ou Desenvolvimento e produto no chat**: o seu nível máximo no produto é menor. Um admin muda em **Membros > Níveis por produto** ([produtos-e-niveis.md](produtos-e-niveis.md#3-definir-o-nível-máximo-de-cada-membro)).
