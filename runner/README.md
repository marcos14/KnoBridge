# KnoBridge — runner local

O `knobridge-runner` roda na máquina que tem o checkout do código e o login do Claude Code ou do Codex. Ele conversa com o servidor do KnoBridge só por HTTPS de saída (heartbeat, pedido de tarefa por long-poll, resultado) e executa o harness de código ali mesmo, somente leitura. Arquitetura no [ADR 0005](../docs/adr/0005-runner-local-do-harness.md); protocolo em [docs/specs/runner.md](../docs/specs/runner.md); harness em [docs/specs/harness.md](../docs/specs/harness.md).

> Estado (plano 0004, F3.4): o `run` mantém o runner online (heartbeat), relata cada fonte ao iniciar e quando o HEAD muda (módulos sugeridos, arquivos alterados, contagens), pede tarefas e as executa: camada 0 e briefing, Claude Code ou Codex somente leitura, verificação mecânica das fontes, excertos com segredos redigidos e envio do resultado (ou falha ou adiamento).

## Instalar

Requer [uv](https://docs.astral.sh/uv/) (ele instala o Python 3.12 sozinho). No Windows, exporte `PYTHONUTF8=1`.

```sh
uv tool install ./runner        # ou: pipx install ./runner
knobridge-runner --version
```

## Configurar

Crie o runner no painel (Fontes → Runners) e copie o token `kbr_...`, mostrado uma única vez.

```sh
knobridge-runner configure --server-url https://knobridge.exemplo.com.br \
  --repo erp=/caminho/do/checkout          # o token é pedido no terminal
knobridge-runner doctor                    # repositórios, executores (PATH e login), servidor e token
knobridge-runner run                       # Ctrl+C para parar
```

Arquivo: `%APPDATA%\knobridge-runner\config.toml` no Windows, `$XDG_CONFIG_HOME/knobridge-runner/config.toml` ou `~/.config/knobridge-runner/config.toml` nos demais (outro caminho com `--config` ou `KNOBRIDGE_RUNNER_CONFIG`). Fica só com permissão do usuário, porque guarda o token.

```toml
server_url = "https://knobridge.exemplo.com.br"
token = "kbr_..."
concurrency = 1                 # tarefas simultâneas
log_retention_days = 14         # logs JSON em <state_dir>/logs

[repositories]                  # nome declarado = caminho absoluto; só o nome sai da máquina
"erp" = "/caminho/do/checkout"

[executors.claude_code]
enabled = true
# command = ["/caminho/claude"] # opcional: comando explícito em vez do PATH

[executors.codex]
enabled = true

[pricing.codex."gpt-5-codex"]   # US$ por milhão de tokens, para estimar o custo do Codex
input = 1.25
cached_input = 0.125
output = 10.0
```

Variáveis que sobrepõem o arquivo: `KNOBRIDGE_RUNNER_URL`, `KNOBRIDGE_RUNNER_TOKEN`, `KNOBRIDGE_RUNNER_CONCURRENCY`. Nenhuma `KNOBRIDGE_*` é repassada aos executores. Pasta de estado padrão: `%LOCALAPPDATA%\knobridge-runner` no Windows, `$XDG_STATE_HOME/knobridge-runner` ou `~/.local/state/knobridge-runner` nos demais.

Logs: JSON do runner em `<state_dir>/logs` e JSONL de cada execução do executor em `<state_dir>/logs/harness` (prompt e saída do agente ficam só aí, na máquina), apagados depois de `log_retention_days`. Arquivos temporários de uma tarefa ficam em `<state_dir>/work/<job_id>` e são apagados no fim.

No Windows, o sandbox do Codex só lê arquivos com leitura para `BUILTIN\Users` (como num clone comum); o `doctor` avisa quando o checkout não tem essa permissão e mostra o `icacls` que resolve.

Códigos de saída do `run`: 0 parado, 2 configuração inválida, 3 token inválido ou revogado, 4 workspace suspenso, 5 protocolo não suportado (atualize o runner), 130 Ctrl+C.

## Desenvolver

Regras e comandos de teste em [AGENTS.md](AGENTS.md).
