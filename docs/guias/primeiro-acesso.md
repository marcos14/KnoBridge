# Primeiro acesso: da instância vazia ao primeiro chat

> Rascunho v0.2 · 2026-10-11 · Em uso (planos 0002 e 0003)
>
> **Mudanças da v0.2** (plano 0003, F6.2): o chat responde com citações quando o assistente tem coleção indexada; o passo a passo da indexação está em [indexar-uma-fonte.md](indexar-uma-fonte.md).

Passo a passo para quem acabou de subir o KnoBridge: criar o superadmin, criar um workspace, convidar pessoas, cadastrar um provedor de LLM e um assistente e conversar com ele. Em desenvolvimento, tudo funciona sem chave de API real, com o provedor `fake`, e os e-mails são lidos no Mailpit.

Regras de acesso, sessões e convites em [autenticacao.md](../specs/autenticacao.md); funcionamento do chat em [chat.md](../specs/chat.md).

## Pré-requisitos

- O ambiente de desenvolvimento rodando e saudável, conforme [subir-ambiente.md](subir-ambiente.md):

  ```bash
  docker compose -f deploy/docker-compose.yml up -d --build --wait
  ```

- Um navegador. Para testar convites com uma segunda pessoa, uma janela anônima ou outro navegador (cada um guarda a própria sessão).
- Painel em <http://localhost:5173> e Mailpit em <http://localhost:8025> (portas padrão; mudam com `FRONTEND_PORT` e `MAILPIT_UI_PORT` no `deploy/.env`).

Nenhum e-mail sai para caixas reais: todos caem no Mailpit, e os links apontam para o painel (`KNOBRIDGE_PUBLIC_BASE_URL`). Use endereços fictícios, como `voce@example.test`.

## Passos

### 1. Configuração inicial (superadmin)

1. Abra <http://localhost:5173>. Com a instância vazia, o painel leva para **Configuração inicial** (`/setup`).
2. Informe nome, e-mail e senha (de 12 a 1024 caracteres) e clique em **Criar conta e entrar**.

Essa conta é o **superadmin** da instância, com e-mail já verificado. A tela de configuração só existe enquanto não há nenhum usuário; depois, quem chega vai para **Entrar** (`/login`).

### 2. Criar o primeiro workspace

O superadmin administra a instância, mas não participa de nenhum workspace por padrão. Por isso o painel mostra "Você ainda não participa de nenhum workspace".

1. Clique em **Criar ou gerenciar workspaces** (ou vá em **Administração da instância > Workspaces**, `/admin/workspaces`).
2. Clique em **Criar workspace** e preencha:
   - **Nome**: por exemplo, `Suporte Interno`;
   - **Identificador (opcional)**: letras minúsculas, números e hífens; em branco, é gerado a partir do nome;
   - **E-mail do proprietário**: o seu próprio e-mail, para você mesmo entrar como owner (ou o de outra pessoa).
3. Clique em **Criar**. O workspace nasce sem membros, e o proprietário recebe um convite por e-mail.

### 3. Aceitar o convite de proprietário

1. Abra o Mailpit (<http://localhost:8025>) e o e-mail de convite.
2. Clique no link (`/accept-invitation?token=...`). Como você está logado com o e-mail convidado, clique em **Aceitar convite**. O painel abre o workspace (`/w/<id>`).

Se o convite for para outra pessoa: sem conta, ela informa nome e senha e clica em **Criar conta e aceitar** (a conta nasce verificada e já entra); com conta, precisa entrar primeiro (**Entrar para aceitar**). Logado com outro e-mail, o aceite é recusado.

### 4. Convidar outras pessoas (opcional)

1. No workspace, vá em **Membros** e clique em **Convidar**.
2. Informe o e-mail e o **Papel** (`Leitor`, `Editor`, `Administrador` ou `Proprietário`, até o seu) e clique em **Enviar convite**.
3. Abra o link do e-mail no Mailpit numa janela anônima e crie a conta da pessoa convidada.

O que cada papel pode fazer está na [matriz de permissões](../specs/autenticacao.md#matriz-de-permissões). Em resumo: leitor conversa com assistentes ativos; editor também gerencia provedores e assistentes; administrador também gerencia membros, convites, configurações e vê auditoria e conversas de todos; proprietário é administrador que pode conceder o papel de proprietário. Convites pendentes ficam na mesma tela, com **Reenviar** e **Revogar**; o link vale 7 dias.

### 5. Cadastrar um provedor de LLM

Precisa de papel editor ou acima.

1. Vá em **Provedores** e clique em **Novo provedor**.
2. Em desenvolvimento, sem chave real:
   - **Tipo**: `Fake (testes, sem rede)`;
   - **Nome**: por exemplo, `Fake dev`;
   - **Chave de API**: qualquer texto com 8 caracteres ou mais, por exemplo `fake-key-dev`.
3. Clique em **Salvar** e depois em **Testar conexão** na linha do provedor. Deve aparecer "Conexão com Fake dev funcionando."

O tipo `fake` não faz nenhuma chamada de rede e só é aceito quando `KNOBRIDGE_ENV` é diferente de `production` (o compose de dev usa `local`). A chave é guardada cifrada e nunca volta para a tela; só os 4 últimos caracteres aparecem ([ADR 0003](../adr/0003-segredos-cifrados.md)).

### 6. Criar um assistente

Precisa de papel editor ou acima.

1. Vá em **Assistentes** e clique em **Novo assistente**.
2. Preencha **Nome** (ex.: `Assistente de suporte`), escolha o **Provedor** cadastrado e informe o **Modelo**: com o provedor `fake`, use `fake-chat`.
3. Os demais campos têm padrão: temperatura 0,2, idioma `pt-BR`, tom neutro, ativo. Deixe **Mensagem quando não há fonte** em branco para usar a mensagem padrão.
4. Clique em **Salvar**.

### 7. Conversar

1. Vá em **Chat**, escolha o assistente, escreva a pergunta e clique em **Enviar** (Enter envia; Shift+Enter quebra a linha).
2. A resposta chega em streaming. **Enquanto o assistente não tiver coleção indexada, ela é sempre a mensagem de "sem fonte"**, marcada como "Respondida sem fonte: o assistente ofereceu abrir chamado.": a regra do produto é não responder sem fonte ([chat.md](../specs/chat.md#regra-de-citações-regra-8-do-agentsmd)). Nesse caso o LLM nem é chamado. Para o assistente responder com citações, indexe uma fonte e ligue a coleção a ele, conforme [indexar-uma-fonte.md](indexar-uma-fonte.md). Para o botão **Abrir chamado** dessas respostas enviar o pedido ao seu sistema de chamados, configure o webhook do assistente ([receber-chamados-por-api.md](receber-chamados-por-api.md#9-receber-abrir-chamado-do-chat)).
3. Avalie a resposta com **Resposta útil** ou **Resposta não ajudou** e, se quiser, um comentário.
4. As suas conversas ficam na lista à esquerda do chat. Owner e administrador veem as conversas de todos os membros, com filtros e totais, em **Conversas**.

### 8. Usar um provedor real (OpenAI, Anthropic ou OpenRouter)

1. Em **Provedores > Novo provedor**, escolha o **Tipo** (`OpenAI`, `Anthropic` ou `OpenRouter`), dê um nome e cole a sua chave de API. **URL base** fica em branco, a menos que use um servidor compatível (ex.: Ollama, vLLM) ou um gateway.
2. Clique em **Testar conexão**: o KnoBridge faz a chamada autenticada mais barata do provedor (listar modelos) e mostra o resultado. Erros comuns: chave recusada, limite de uso, provedor fora do ar.
3. No assistente, troque o **Provedor** e informe o **Modelo** com o identificador exato usado pelo provedor (por exemplo, `gpt-4.1-mini` na OpenAI; para Anthropic e OpenRouter, o identificador da documentação deles).

Enquanto o assistente não tiver coleção com trechos relevantes, o chat continua respondendo "sem fonte" sem chamar o provedor. Para embeddings (coleções), use OpenAI ou OpenRouter: a Anthropic não oferece embeddings ([indexar-uma-fonte.md](indexar-uma-fonte.md)). Use chaves reais só na sua máquina ou num ambiente protegido, e nunca as commite. Lembre que as chaves gravadas dependem de `KNOBRIDGE_SECRET_KEY`: trocar esse segredo exige recadastrar as chaves dos provedores ([ADR 0003](../adr/0003-segredos-cifrados.md)).

## Como verificar

- **Administração da instância > Auditoria da instância** mostra `setup.completed`, os logins e a criação do workspace; **Auditoria** do workspace (owner/admin) mostra o convite aceito, o provedor, o teste de conexão e o assistente.
- **Conversas** (owner/admin) lista a conversa do passo 7, com a avaliação dada.
- Pela API, com o mesmo navegador logado: `http://localhost:5173/v1/me` devolve o seu usuário e os workspaces com o papel em cada um.

## Outros fluxos de conta

- **Esqueci a senha**: em **Entrar**, clique em **Esqueci minha senha**, informe o e-mail e abra o link no Mailpit (vale 1 hora). Redefinir encerra todas as sessões da conta.
- **Verificar e-mail**: contas criadas por convite e o superadmin já nascem verificados. Para reenviar o link de verificação, use **Perfil** (menu do usuário). Hoje a verificação é informativa: nenhuma tela exige e-mail verificado.
- **Sessões**: **Segurança** (menu do usuário) troca a senha, lista as sessões ativas e encerra uma ou todas.

## Como desfazer

Para voltar à instância vazia (apaga banco, usuários, workspaces e conversas):

```bash
docker compose -f deploy/docker-compose.yml down -v
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

Sem apagar tudo: o superadmin pode suspender workspaces e usuários em **Administração da instância**, e o workspace pode excluir assistentes e provedores (um provedor em uso por assistente não pode ser excluído).

## Problemas comuns

- **O e-mail não chegou ao Mailpit**: veja "E-mail não aparece no Mailpit" em [subir-ambiente.md](subir-ambiente.md#problemas-comuns). O envio acontece depois da resposta da API; falhas só aparecem no log da `api` (`email_delivery_failed`).
- **"Muitas tentativas" no login**: depois de 5 senhas erradas para o mesmo e-mail e IP em 15 minutos, o login fica bloqueado até a janela acabar, mesmo com a senha certa. Em dev, espere ou recrie o ambiente.
- **O link do convite diz que é inválido**: o link vale 7 dias, deixa de valer quando o convite é reenviado (vale só o mais novo) ou revogado, e não funciona com o workspace suspenso. Peça um novo em **Membros > Reenviar**.
- **Aceitar convite recusa o meu login**: você está logado com outro e-mail. Saia (menu do usuário > **Sair**) ou use uma janela anônima.
- **O tipo `Fake` é recusado ao salvar o provedor**: a API está com `KNOBRIDGE_ENV=production`. Use um provedor real ou um ambiente de desenvolvimento.
- **Não vejo Provedores, Assistentes ou Conversas no menu**: o menu mostra só o que o seu papel permite (editor para provedores e assistentes, administrador para conversas, configurações e auditoria).
- **O chat diz que não há assistente disponível**: não há assistente ativo no workspace. Crie um ou reative-o em **Assistentes**.
