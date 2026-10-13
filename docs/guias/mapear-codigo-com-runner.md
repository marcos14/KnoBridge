# Mapear código com o runner: do checkout local ao conhecimento citado no chat

> Rascunho v0.1 · 2026-10-11 · Em uso (plano 0004)

Passo a passo para quem vai instalar o `knobridge-runner` na máquina que tem o código: instalar, configurar, conferir com o `doctor`, escolher entre login de assinatura e chave de API, entender o que o agente pode fazer e o que sai da sua máquina, controlar custos e, no painel, rodar módulos, revisar e exportar o conhecimento.

O runner roda o harness de código (Claude Code ou Codex) **na sua máquina**, somente leitura, e manda para o servidor só o conhecimento gerado e as evidências `arquivo:linhas`. O servidor nunca recebe o repositório nem as credenciais dos CLIs. Por dentro: arquitetura no [ADR 0005](../adr/0005-runner-local-do-harness.md), protocolo em [runner.md](../specs/runner.md), harness em [harness.md](../specs/harness.md).

## Pré-requisitos

- Um servidor do KnoBridge no ar ([subir-ambiente.md](subir-ambiente.md)) e um workspace onde você é **owner ou admin** (para criar o runner) e uma coleção com credencial de embedding ([indexar-uma-fonte.md](indexar-uma-fonte.md), passos 2 e 3). Editores criam a fonte e rodam módulos; leitores só veem.
- Na máquina do runner:
  - [uv](https://docs.astral.sh/uv/), que instala o Python 3.12 sozinho; no Windows, exporte `PYTHONUTF8=1`;
  - `git` no PATH;
  - um clone do repositório do KnoBridge (o runner é instalado a partir da pasta `runner/`);
  - o checkout do código a mapear, num clone Git comum;
  - pelo menos um executor: [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) (`claude`) ou [Codex CLI](https://developers.openai.com/codex/cli) (`codex`), com login feito ou chave de API (passo 3).
- Acesso HTTPS de saída da máquina até o servidor. O runner não abre porta nenhuma; proxy corporativo funciona pelas variáveis `HTTPS_PROXY` e `NO_PROXY`. `http://` só é aceito para `localhost`.

Use um checkout cujo código você pode analisar com o provedor do executor escolhido: o agente lê os arquivos do módulo e o provedor dele (Anthropic ou OpenAI) recebe esse conteúdo pela sua conta.

## Passos

### 1. Criar o runner no painel

1. Vá em **Runners > Novo runner**, dê um nome que identifique a máquina (ex.: `notebook-ana`) e clique em **Criar runner**.
2. Copie o **token** `kbr_...`. Ele aparece **uma única vez**: o servidor guarda só o hash. Se perder, exclua o runner e crie outro.
3. A mesma tela mostra os comandos dos passos 2 a 5 já com a URL do servidor.

O token identifica o runner e o workspace. Ele só abre as rotas `/v1/runner/*`, nunca o painel nem a API de sessão.

### 2. Instalar

Na raiz do clone do KnoBridge:

```sh
uv tool install ./runner        # ou: pipx install ./runner
knobridge-runner --version
```

Para atualizar depois de um `git pull`: `uv tool install --reinstall ./runner`.

### 3. Escolher como o executor se autentica

As credenciais dos CLIs ficam **só na sua máquina**: o runner verifica se há login, mas nunca lê, guarda nem envia token, chave ou e-mail da conta. Escolha um modo por executor.

| Modo | Claude Code | Codex | Quando usar |
|---|---|---|---|
| Login de assinatura | `claude auth login` (credenciais em `~/.claude`) | `codex login` (credenciais em `~/.codex`) | Uso pessoal ou ensaio, com o limite da sua assinatura. |
| Chave de API | `ANTHROPIC_API_KEY` no ambiente do runner | `CODEX_API_KEY` ou `OPENAI_API_KEY` no ambiente do runner | Uso contínuo ou numa máquina compartilhada, com cobrança por token na conta da chave. |

Com a chave no ambiente, o runner considera o executor autenticado e repassa a variável ao CLI. No modo não interativo que o runner usa, o Claude Code cobra na `ANTHROPIC_API_KEY` mesmo que haja login, e o `codex exec` usa a `CODEX_API_KEY`; para o Codex com `OPENAI_API_KEY`, prefira gravar a chave com `codex login --with-api-key`. Para usar a assinatura, não defina essas variáveis no shell que roda o runner.

Quando a franquia da assinatura acaba ("usage limit", "session limit"), a tarefa é **adiada** até o horário de reset informado pelo CLI (entre 1 minuto e 6 horas; sem horário, 30 minutos) e volta sozinha para a fila. Quando o login expira, a tarefa também é adiada e o executor aparece "sem login" no painel até você entrar de novo.

### 4. Configurar

```sh
knobridge-runner configure --server-url https://knobridge.exemplo.com.br \
  --repo erp=/caminho/do/checkout
```

- O token é pedido no terminal, para não ficar no histórico do shell.
- `--repo NOME=CAMINHO` declara um repositório. Só o **nome** sai da máquina; o caminho absoluto nunca. Nome com letras, números, `.`, `_` ou `-`, até 64 caracteres. Repita a opção para vários repositórios; `--remove-repo NOME` tira um.
- `--disable-executor codex` (ou `claude_code`) desliga um executor que você não quer usar; `--enable-executor` liga de novo.
- `--concurrency N` define quantas tarefas rodam ao mesmo tempo (padrão 1).

O arquivo fica em `%APPDATA%\knobridge-runner\config.toml` no Windows e em `~/.config/knobridge-runner/config.toml` (ou `$XDG_CONFIG_HOME`) nos demais, só com permissão do seu usuário, porque guarda o token. Chaves que o `configure` não cobre (comando explícito do executor, preços do Codex, retenção de logs) se editam no arquivo; referência completa em [runner/README.md](../../runner/README.md#configurar).

No Windows, o runner só acha `claude.exe` e `codex.exe` no PATH. Se o seu CLI foi instalado como shim `.cmd` do npm, informe o executável no arquivo:

```toml
[executors.claude_code]
enabled = true
command = ["C:\\caminho\\para\\claude.exe"]
```

### 5. Conferir com o `doctor`

```sh
knobridge-runner doctor
```

Cada linha sai como `[ok]`, `[aviso]` ou `[falha]`:

- **repositório `<nome>`**: a pasta existe e é um repositório Git;
- **repositório `<nome>` (Codex)**, só no Windows: avisa quando o checkout não dá leitura a `BUILTIN\Users`, que o sandbox do Codex exige, e mostra o `icacls` que resolve;
- **executor `claude_code` / `codex`**: achado no PATH (ou no comando configurado), versão e login. "sem login" mostra o comando para entrar. A verificação usa `claude auth status --json` e `codex login status`, que não chamam o modelo;
- **servidor e token**: o servidor responde, o token vale e quantas fontes estão ligadas ao runner.

Corrija toda `[falha]` antes de seguir.

### 6. Rodar

```sh
knobridge-runner run          # Ctrl+C para parar
```

O runner manda um heartbeat a cada 30 segundos e fica **Online** na tela **Runners** (contato nos últimos 90 segundos), com a versão, os executores e os repositórios informados. Ele pede tarefas por long-poll (espera de até 25 segundos por pedido), então uma tarefa enfileirada começa em segundos.

Deixe o processo rodando enquanto quiser mapear código: as tarefas esperam na fila, sem expirar, enquanto o runner está offline. Para rodar em segundo plano, use o agendador do sistema (Agendador de Tarefas no Windows, `systemd --user` no Linux, `launchd` no macOS). Códigos de saída em [runner/README.md](../../runner/README.md#configurar): 3 é token inválido ou revogado, 4 é workspace suspenso, 5 pede atualizar o runner.

### 7. Criar a fonte runner

1. Vá em **Fontes > Nova fonte**, preencha **Nome** e **Coleção** e escolha o tipo **Runner local**.
2. Em **Runner**, escolha o da sua máquina. Com ele online, **Repositório** lista os nomes declarados no passo 4; offline, digite o nome.
3. Ajuste, se quiser:
   - **Executor padrão**: Claude Code ou Codex;
   - **Modelo** de cada executor: em branco, o padrão do CLI;
   - **Orçamento por tarefa (US$)**: de 0,10 a 100, padrão 5 (veja [Custos](#custos-e-orçamento));
   - **Tempo limite por tarefa**: de 60 a 7200 segundos, padrão 1200;
   - **Linhas de excerto por evidência**: de 0 a 80, padrão 30; 0 não envia excerto nenhum;
   - **Gerar conhecimento a cada commit**: quando o runner relata um HEAD novo, os módulos com arquivos alterados entram na fila sozinhos;
   - **Incluir** e **Excluir**: globs que valem para a leitura do runner (mesma sintaxe das outras fontes).
4. Salve, abra a fonte e use **Testar conexão**: "A fonte ... está acessível." quer dizer runner online servindo o repositório.

### 8. Módulos

Na aba **Módulos**, o runner sugere os módulos pelas pastas do repositório (até 40 arquivos e 6000 linhas por módulo, em geral), no próximo heartbeat depois de criada a fonte e sempre que o HEAD muda. Cada linha mostra os padrões, o tamanho, o último commit mapeado e a última tarefa.

- **Editar** muda título e padrões (sintaxe do `.gitignore`, o último padrão que casa vale). Um módulo sugerido editado vira manual e deixa de ser alterado pelos relatórios.
- **Novo módulo** cria um módulo à mão.
- **Desligar** tira o módulo das execuções, inclusive das automáticas por commit.

Para rodar, marque os módulos (ou **Selecionar os ligados do filtro**), escolha o executor e o modelo, se quiser outro que o da fonte, e clique em **Rodar N módulos**. Módulo que já tem tarefa na fila ou em execução é pulado.

### 9. Tarefas

A aba **Tarefas** acompanha cada execução: **Na fila**, **Reservada**, **Em execução**, **Adiada**, **Concluída**, **Falhou** ou **Cancelada**, com gatilho, executor e modelo, duração, custo, tokens e itens aceitos e rejeitados. A lista se atualiza sozinha enquanto houver tarefa ativa.

- **Detalhes** mostra o commit, as tentativas, o erro (se houve) e os itens **rejeitados** pela verificação, agrupados por motivo (arquivo não encontrado, intervalo inválido, símbolo que não aparece no trecho...).
- **Cancelar** para a tarefa na hora no painel; se ela já estiver no runner, ele mata o executor no próximo contato.
- Falha retentável (runner interrompido, reserva vencida) volta para a fila, até 3 tentativas.

### 10. Revisar o conhecimento

Na aba **Conhecimento**, escolha o **Módulo**. Cada item é uma **regra** (enunciado, quando vale, mensagem exibida, como o usuário resolve, classificação e relevância) ou o **enriquecimento do módulo** (objetivo, fluxo principal, mensagens, perguntas frequentes e dúvidas em aberto), sempre com as **evidências** conferidas no código: arquivo, linhas, símbolo e o excerto.

Todo item nasce com o selo **Inferido**. Revise e use:

- **Aprovar**: o selo vira **Revisado**, inclusive nas citações do chat;
- **Editar**: corrige título e textos (as evidências não se editam);
- **Descartar**: tira o item do índice na próxima sincronização (ele continua listado);
- **Reabrir**: volta para pendente e inferido.

Cada revisão pede uma sincronização da fonte (gatilho **Harness**, visível na aba **Indexação**), que indexa o conhecimento na coleção. A marca **Evidência mudou** aparece quando um arquivo citado mudou depois da revisão: confira e aprove de novo.

Com a coleção ligada a um produto ([indexar-uma-fonte.md](indexar-uma-fonte.md#8-ligar-a-coleção-ao-produto)), o chat cita o item com o selo e as evidências no código. Os níveis contam ([produtos-e-niveis.md](produtos-e-niveis.md#4-ajustar-o-nível-mínimo-das-fontes)): item **inferido** só chega a Suporte e acima; item **revisado** chega também ao Usuário final, mas sem as evidências (caminhos e excertos de código), que ficam para Suporte e acima.

### 11. Exportar

**Exportar .md do módulo** baixa um `.zip` com um arquivo Markdown por item não descartado, com frontmatter (`id`, `tipo`, `modulo`, `fontes`, `confianca`, `gerado_por`, `commit`, `atualizado_em`). Formato em [harness.md](../specs/harness.md#md-exportado). Serve para guardar o conhecimento num repositório de documentação ou levar para outra ferramenta.

## Segurança

O agente roda **somente leitura**, com a pasta de trabalho no checkout:

- **Claude Code**: `--tools Read,Grep,Glob` (só ler, buscar e listar arquivos), `--disallowedTools Edit,Write,Bash` como segunda trava, `--setting-sources user` (hooks e permissões do `.claude/` do repositório analisado não rodam) e `--strict-mcp-config` sem servidores MCP;
- **Codex**: `--sandbox read-only` (os comandos que o agente roda não escrevem nem acessam a rede) e `-c mcp_servers={}`.

Além das flags, o runner vigia cada ação do agente: uma ferramenta fora da lista no Claude Code, ou uma alteração de arquivo ou chamada MCP no Codex, **mata o processo inteiro na hora** e a tarefa falha com `unsafe_tool_use`. O mesmo acontece no tempo limite e no cancelamento. Nada é escrito no checkout: arquivos temporários ficam na pasta de estado do runner e são apagados no fim.

O executor também **não herda o ambiente inteiro** do runner. Passam só as variáveis de sistema (PATH, pastas do usuário, idioma), de proxy e certificados, e as do próprio executor (`ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `CODEX_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`). Nenhuma `KNOBRIDGE_*` passa: o token do runner nunca chega ao agente.

Depois que o agente responde, o runner **confere cada evidência** no checkout: o arquivo existe, é texto e está dentro do repositório, o intervalo de linhas existe e tem até 80 linhas e o símbolo citado aparece ali. Item sem nenhuma evidência válida é rejeitado e nunca vira conhecimento.

Se a máquina for roubada ou o token vazar, revogue o runner em **Runners > Revogar**: o token deixa de valer na requisição seguinte.

## O que sai da sua máquina

Sai, sempre pelos modelos fixos do protocolo:

- versão do runner, plataforma, executores disponíveis com versão e "tem login: sim/não";
- o **nome** declarado de cada repositório, o HEAD, a branch e se há alteração local;
- caminhos **relativos** (padrões de módulo, arquivos alterados, arquivos citados) e contagens de arquivos, linhas e linguagens;
- o conhecimento gerado pelo agente (textos curtos dos itens);
- por evidência: arquivo, linhas, símbolo e um **excerto de até 30 linhas** (configurável de 0 a 80 na fonte), com segredos óbvios trocados por `[REDACTED]` (chaves de nuvem e de API, tokens, JWT, senhas em URL e em atribuições como `password=...`);
- métricas da tarefa: custo, tokens, duração, turnos, chamadas de ferramenta e contagens da verificação; códigos de erro.

**Nunca sai**: o código inteiro ou além do excerto, diffs, o caminho absoluto do checkout, nome de usuário ou da máquina, credenciais e e-mail da conta dos CLIs, o prompt, o briefing e as extrações locais, mensagens e autores de commit, a saída bruta e os logs do agente, stderr, variáveis de ambiente. Arquivos sensíveis pelo nome (`.env`, chaves, certificados, `credentials.json`...) entram como evidência, mas **sem excerto**. Lista completa em [runner.md](../specs/runner.md#o-que-sai-e-o-que-não-sai-da-máquina).

Lembre que o **provedor do executor** (Anthropic ou OpenAI) lê os arquivos do módulo durante a tarefa, pela sua conta: essa leitura é entre a sua máquina e ele, como no uso normal do CLI.

Logs locais, só na sua máquina: o log JSON do runner em `<pasta de estado>/logs` e o JSONL de cada execução do executor (prompt e saída do agente) em `<pasta de estado>/logs/harness`, apagados depois de 14 dias (`log_retention_days`). A pasta de estado é `%LOCALAPPDATA%\knobridge-runner` no Windows e `~/.local/state/knobridge-runner` (ou `$XDG_STATE_HOME`) nos demais.

## Custos e orçamento

O custo do agente é cobrado **na conta de quem roda o runner** (assinatura ou chave de API); o servidor só registra o valor informado em cada tarefa, na aba **Tarefas**.

- **Claude Code**: o **Orçamento por tarefa** vira `--max-budget-usd`. A tarefa para ao atingir o valor e falha com `budget_exceeded`. O custo registrado é o informado pelo CLI. Com assinatura, o valor é uma estimativa do CLI e o limite real é a franquia.
- **Codex**: não há teto de gasto nativo; o limite efetivo é o **Tempo limite por tarefa**. O custo só é estimado se você configurar o preço do modelo no runner (US$ por milhão de tokens):

  ```toml
  [pricing.codex."gpt-5-codex"]
  input = 1.25
  cached_input = 0.125
  output = 10.0
  ```

  Sem preço configurado, a tarefa mostra os tokens e o custo fica em branco.
- A tentativa de resgate (quando o agente não devolve o JSON pedido, o runner pede de novo na mesma sessão, uma vez) usa o que sobrou do orçamento.
- A indexação do conhecimento (embeddings na coleção) é cobrada no provedor da coleção, como nas outras fontes, e aparece na aba **Indexação**.

Execução de referência com um módulo pequeno (2026-10-11): Claude Code com `haiku`, cerca de US$ 0,006 e 30 segundos; Codex, cerca de 55 mil tokens de entrada e 60 segundos. Módulos maiores e modelos maiores custam proporcionalmente mais: comece por poucos módulos e um orçamento baixo, e só então ligue **Gerar conhecimento a cada commit**.

## Como verificar

- **Runners** mostra a máquina **Online**, com os executores sem "sem login" e o repositório declarado.
- **Testar conexão** na fonte responde "A fonte ... está acessível.".
- A aba **Módulos** lista os módulos sugeridos; uma tarefa termina **Concluída** com itens aceitos.
- A aba **Conhecimento** mostra os itens com evidências; depois de aprovar, a aba **Indexação** tem uma execução **Harness** concluída.
- No chat, uma pergunta sobre a regra traz a citação do item com o selo **Revisado**.

## Como desfazer

- **Parar o runner**: Ctrl+C no `run`. Uma tarefa em andamento é devolvida à fila.
- **Revogar o runner** (**Runners > Revogar**): o token deixa de valer na hora, sem volta. Fontes que o usam podem ser editadas para outro runner.
- **Excluir o runner** só funciona quando nenhuma fonte o usa.
- **Excluir a fonte** apaga módulos, tarefas, conhecimento e o que foi indexado dela. O checkout nunca é tocado.
- **Desinstalar**: `uv tool uninstall knobridge-runner`; apague o `config.toml` (tem o token) e a pasta de estado.

## Problemas comuns

- **`[falha] executor claude_code: 'claude' não encontrado no PATH`**: instale o CLI ou, no Windows com shim `.cmd`, configure `command` com o `.exe` (passo 4). Se você não usa esse executor, desligue com `--disable-executor`.
- **"sem login" no `doctor` ou no painel**: rode `claude auth login` ou `codex login` na mesma conta de usuário do runner, ou defina a chave de API no ambiente do runner.
- **`[falha] servidor e token: token inválido ou revogado`** (o `run` sai com código 3): crie outro runner e rode `knobridge-runner configure --token kbr_...`.
- **O runner fica offline no painel**: confira se o `run` está rodando e se a máquina alcança o servidor (proxy em `HTTPS_PROXY`). O `doctor` mostra "servidor inacessível" nesse caso.
- **Nenhum módulo aparece**: o runner relata a fonte no heartbeat seguinte à criação (até 30 segundos). Confira se o nome do repositório na fonte é igual ao do `--repo` e se os globs **Incluir** não excluíram tudo.
- **Tarefa adiada**: franquia esgotada ou login expirado; ela volta sozinha no horário indicado em **Detalhes**. Para rodar já, entre de novo no CLI ou troque o executor ao rodar o módulo.
- **Tarefa falhou com `unsafe_tool_use`**: o agente tentou uma ferramenta proibida e foi interrompido. Rode de novo; se repetir, troque de modelo.
- **Tarefa falhou com `no_structured_output` ou `invalid_output`**: o agente não devolveu o JSON pedido nem no resgate. Rode de novo ou use um modelo maior.
- **Muitos itens rejeitados**: o agente citou linhas que não existem ou símbolos fora do trecho; os motivos estão em **Detalhes** da tarefa. Módulos menores costumam dar citações melhores.
- **Codex no Windows não lê nada ("acesso negado")**: o checkout não dá leitura a `BUILTIN\Users`; o `doctor` mostra o `icacls` que resolve.
- **Codex falha com "requires a newer version of Codex"**: o modelo padrão do seu `~/.codex/config.toml` exige um CLI mais novo. Atualize o CLI ou informe um modelo na fonte.

## Referências

- Claude Code, modo headless e flags da CLI: <https://docs.claude.com/en/docs/claude-code/headless>
- Codex CLI, modo não interativo: <https://developers.openai.com/codex/noninteractive>
- Codex, assinatura e chave de API: <https://developers.openai.com/codex/pricing>
- uv tool: <https://docs.astral.sh/uv/guides/tools/>
