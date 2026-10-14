# Conectar pelo MCP: os produtos no Claude Code, no Cursor e no Codex

> Rascunho v0.1 · 2026-10-14 · Em uso (plano 0010)

Passo a passo para usar os produtos do KnoBridge como ferramentas de um assistente de código ou agente (Claude Code, Cursor, Codex ou qualquer cliente MCP com Streamable HTTP), pelo servidor MCP da instância em `/v1/mcp`. O assistente busca trechos com citações, lê os documentos citados, pede uma resposta pronta e abre chamado, sempre dentro dos produtos e do nível máximo da chave de API.

Contrato completo (ferramentas, entradas, saídas, erros e limites) em [mcp.md](../specs/mcp.md); decisão de arquitetura no [ADR 0009](../adr/0009-canais-mcp-e-widget.md). A chave é a mesma da API pública ([usar-a-api.md](usar-a-api.md)), e os níveis são os de [produtos-e-niveis.md](produtos-e-niveis.md).

## Pré-requisitos

- A stack rodando ([subir-ambiente.md](subir-ambiente.md)) e um produto **ativo** que responda com fontes no chat do painel, com os níveis de resposta configurados ([produtos-e-niveis.md](produtos-e-niveis.md)). Em desenvolvimento, o provedor `fake` serve: `ask` responde `Fake reply to: <pergunta>`, mas as citações são reais.
- Papel **owner** ou **admin** no workspace, para criar a chave.
- O cliente MCP instalado: [Claude Code](https://code.claude.com/docs/en/mcp), [Cursor](https://cursor.com/docs/context/mcp) ou [Codex](https://developers.openai.com/codex/mcp).
- A URL da instância. Nos exemplos, `http://localhost:5173`, o painel do compose: o nginx dele encaminha `/v1` para a API. Em produção, use o endereço do painel com HTTPS (ex.: `https://kb.empresa.com/v1/mcp`).

## Passos

### 1. Criar a chave

1. No workspace, vá em **Chaves de API** > **Nova chave**.
2. Em **Nome**, identifique a pessoa ou a máquina (ex.: `IDE da Ana`). Use **uma chave por pessoa ou por máquina**: as conversas do MCP aparecem com o nome da chave, e revogar uma não derruba as outras.
3. Em **Produtos**, deixe todos ou marque só os que a pessoa deve consultar.
4. Em **Nível máximo**, escolha o nível de quem vai usar. O painel pré-seleciona **Usuário final** (nunca código nem SQL); para quem desenvolve, **Desenvolvimento e produto**; para a equipe de suporte, **Suporte**.
5. Clique em **Salvar**. A chave `kbk_…` aparece **uma única vez**, já com a seção **Conectar por MCP**: a URL do servidor, a linha que define a variável `KNOBRIDGE_API_KEY` com a chave nova e as configurações dos três clientes. Copie o que precisar e clique em **Concluído**.

A mesma seção fica abaixo da lista de chaves, com um marcador no lugar da chave (`kbk_sua_chave`). As configurações nunca levam a chave: elas leem a variável.

### 2. Guardar a chave numa variável de ambiente

```bash
export KNOBRIDGE_API_KEY="kbk_..."          # bash e zsh; ponha no ~/.bashrc ou ~/.zshrc
```

```powershell
$env:KNOBRIDGE_API_KEY = "kbk_..."           # PowerShell, só nesta sessão
[Environment]::SetEnvironmentVariable("KNOBRIDGE_API_KEY", "kbk_...", "User")   # permanente
```

Nunca escreva a chave num arquivo versionado. Abra o cliente MCP depois de definir a variável, para ele herdá-la.

### 3. Conectar o cliente

**Claude Code**, no terminal, com a variável definida:

```sh
claude mcp add --transport http knobridge http://localhost:5173/v1/mcp \
  --header "Authorization: Bearer $KNOBRIDGE_API_KEY"
```

O shell troca `$KNOBRIDGE_API_KEY` pelo valor, então a chave fica gravada na configuração do Claude Code (`~/.claude.json`, ou o `.mcp.json` do projeto com `--scope project`; nesse caso, não versione o arquivo). Confira com `claude mcp list` (o `knobridge` aparece conectado) ou, dentro do Claude Code, com `/mcp`. Para trocar a chave: `claude mcp remove knobridge` e o `add` de novo.

**Cursor**, em `.cursor/mcp.json` do projeto ou em `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "knobridge": {
      "url": "http://localhost:5173/v1/mcp",
      "headers": { "Authorization": "Bearer ${env:KNOBRIDGE_API_KEY}" }
    }
  }
}
```

O Cursor lê a variável ao iniciar. Confira na seção de MCP das configurações do Cursor: o servidor `knobridge` aparece com as cinco ferramentas.

**Codex**, em `~/.codex/config.toml`:

```toml
[mcp_servers.knobridge]
url = "http://localhost:5173/v1/mcp"
bearer_token_env_var = "KNOBRIDGE_API_KEY"
```

O Codex manda `Authorization: Bearer <valor da variável>`. Confira com `codex mcp list`.

Outros clientes: configure um servidor MCP **Streamable HTTP** com a URL `<instância>/v1/mcp` e o header `Authorization: Bearer kbk_…`. O servidor não tem OAuth nesta versão, então não entra como conector no claude.ai nem no ChatGPT.

### 4. Perguntar

Peça ao assistente algo sobre o produto, por exemplo: "Use o KnoBridge e me diga como emitir a segunda via do boleto no ERP, com as fontes". As instruções do servidor orientam o modelo a:

1. chamar `list_products` para saber os produtos e níveis da chave;
2. preferir `search_knowledge` (sem custo de LLM no KnoBridge: quem escreve a resposta é o modelo do seu cliente) e citar cada afirmação com a fonte;
3. ler um documento citado com `get_document` quando o trecho não basta;
4. usar `ask` para uma resposta pronta do KnoBridge e, se ela não resolver, `open_ticket` com um resumo e o e-mail de quem pede.

## As ferramentas

| Ferramenta | O que faz | Custo no KnoBridge | Grava conversa |
|---|---|---|---|
| `list_products` | Produtos que a chave alcança, os níveis permitidos em cada um, o nível padrão e se o produto abre chamado. | Nenhum | Não |
| `search_knowledge` | Até 20 trechos (padrão 8) de um produto, no nível pedido, com a citação de cada um (arquivo e linhas, commit, chamado, card, conhecimento). Sem resultado, traz uma nota mandando não responder sem fonte. | Só o embedding da consulta | Não |
| `get_document` | O conteúdo de um documento citado (pelo `document_id` da citação), só nas partes permitidas ao nível, paginado por `next_offset`. | Nenhum | Não |
| `ask` | A resposta pronta do nível, com citações, como no chat do painel; `conversation_id` continua a conversa. Sem fonte, não chama o LLM e responde que não sabe. | Embedding e LLM do nível | Sim, canal `mcp` |
| `open_ticket` | Abre um chamado pelo webhook do produto a partir de uma resposta de `ask` (`message_id`), com o resumo e o e-mail informados. | Nenhum | O pedido de chamado |

`product` aceita o **id** ou o **nome exato** do produto. Produto inexistente, inativo ou fora do escopo da chave responde `not_found`, igual: a chave não descobre o que não pode usar.

## Níveis

- Sem `level`, vale o **nível máximo da chave**. Um nível acima dele volta como erro da ferramenta `level_not_allowed` (`details.max_level` diz o teto).
- O nível decide as fontes **na própria busca**: um trecho acima do nível nunca sai em `search_knowledge`, `get_document` nem `ask`. Numa chave Usuário final, código e consultas SQL não aparecem nem pelo `get_document`.
- No nível Usuário final, as citações de conhecimento vêm sem evidências de código.
- Mudar o nível máximo ou o escopo da chave no painel vale na próxima chamada.

## Onde aparece no painel

- **Conversas**: as conversas de `ask`, com "MCP · <nome da chave>" no lugar do usuário; o filtro **Canal** tem a opção **MCP**.
- **Uso e custos**: agrupado por **Canal**, a linha **MCP** conta as respostas de `ask`; por **Chave de API**, as respostas da API e do MCP de cada chave. `search_knowledge`, `get_document` e `list_products` não entram (não há resposta de LLM).
- **Chaves de API**: o **Último uso** da chave.
- Pedidos de chamado de `open_ticket`: na conversa, em **Conversas**, e no sistema de chamados com `channel: "mcp"` e o solicitante como informado (`verified: false`); como receber em [receber-chamados-por-api.md](receber-chamados-por-api.md#9-receber-abrir-chamado-do-chat).

## Como desfazer

- Desconectar: `claude mcp remove knobridge`, ou apague o bloco `knobridge` do `mcp.json` do Cursor ou do `config.toml` do Codex.
- Cortar o acesso: em **Chaves de API**, **Revogar** a chave. A próxima chamada recebe 401; as conversas ficam em **Conversas**.

## Problemas comuns

- **401 `invalid_api_key`** (o cliente mostra "Error POSTing to endpoint" ou "unauthorized"): chave ausente, errada ou revogada. Confira se a variável estava definida quando o cliente subiu (`echo $KNOBRIDGE_API_KEY`) e se o header é `Authorization: Bearer kbk_…`. A sessão do painel não abre o MCP.
- **403 `workspace_suspended`**: o workspace da chave foi suspenso na administração da instância.
- **421 ou "Invalid Host header"** atrás de um proxy ou com outro nome: o SDK do MCP só aceita os hosts conhecidos. Por padrão, valem o host de `KNOBRIDGE_PUBLIC_BASE_URL`, `localhost:*` e `127.0.0.1:*`. Com outro nome (ou porta) na frente da API, liste-os em `KNOBRIDGE_MCP_ALLOWED_HOSTS` (separados por vírgula; `host:*` aceita qualquer porta) e recrie a `api`. Confira também se o proxy repassa o header `Host`.
- **403 `origin_not_allowed`**: a requisição veio de uma página de navegador (com header `Origin`), como um inspetor MCP web. Clientes de IDE e de terminal não mandam `Origin`. Para liberar uma origem, ponha-a em `KNOBRIDGE_MCP_ALLOWED_ORIGINS` (`https://host[:porta]`, separadas por vírgula); vazia, toda requisição com `Origin` é recusada (proteção contra DNS rebinding).
- **405 no `GET /v1/mcp`**: esperado. O servidor é sem estado e não abre o stream de notificações; os clientes seguem só com `POST`.
- **`level_not_allowed`**: o nível pedido passa do máximo da chave. Peça sem `level` ou suba o nível máximo da chave em **Chaves de API** > **Editar**.
- **`level_not_configured`** em `ask`: o nível não tem credencial e modelo em **Configurações** > **Níveis de resposta**. `search_knowledge` e `get_document` funcionam mesmo assim.
- **`not_found`**: o produto não existe, está inativo ou está fora do escopo da chave; confira o nome exato com `list_products`.
- **`search_knowledge` sem resultado** para algo que deveria achar: rode a mesma pergunta no chat do painel no mesmo nível e use **Testar busca** na coleção ([indexar-uma-fonte.md](indexar-uma-fonte.md#problemas-comuns)); confira o nível mínimo da fonte ([produtos-e-niveis.md](produtos-e-niveis.md)).
- **`ticket_webhook_not_configured`** em `open_ticket`: o produto não tem o webhook "Abrir chamado" ([receber-chamados-por-api.md](receber-chamados-por-api.md#9-receber-abrir-chamado-do-chat)). `ticket_request_exists`: a resposta já tem um pedido.
- **413 `payload_too_large`**: a requisição passou de 64 KiB; encurte a pergunta ou o resumo.
