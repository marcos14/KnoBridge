# runner/src/knobridge_runner/

**Função**: o pacote do `knobridge-runner`: configuração, protocolo com o servidor, laço principal, descoberta da máquina (executores e repositórios) e CLI.

**Entra aqui** (um módulo por responsabilidade, até ~400 linhas cada):
- `config.py`: `RunnerConfig` (TOML na pasta de configuração do usuário + `KNOBRIDGE_RUNNER_URL`/`_TOKEN`/`_CONCURRENCY`/`_CONFIG`), pastas padrão por plataforma, gravação com permissão só do usuário.
- `formats.py`, `protocol.py`, `protocol_result.py`: modelos Pydantic de `/v1/runner/*` com os nomes dos schemas da spec (requisições recusam campos desconhecidos; respostas os ignoram).
- `client.py`: `RunnerClient` (httpx, Bearer, `KnoBridge-Runner-Protocol: 1`, TLS verificado, proxy pelas variáveis padrão), long-poll de claim, retentativas por `RetryPolicy` e mapeamento de status para `errors.py`; `backoff.py` com o backoff (1 s, ×2, teto 60 s, jitter ±20% com `random.Random` injetável), o relógio e a espera injetáveis.
- `loop.py`: `Runner` (heartbeat do runner, laços de claim por concorrência, heartbeat da tarefa em segundo plano, entrega de resultado/falha/adiamento, Ctrl+C vira `fail` `interrupted` retentável); `processor.py`: interface `JobProcessor`, `JobContext` e os desfechos.
- `commands.py` (comandos curtos sem shell, ambiente por allowlist), `executors.py` (executável, versão, login via `AuthChecker`), `git.py` (HEAD, branch, alterações locais), `status.py` (`MachineStatus`, com login reconferido a cada 5 min).
- `layer0/`: camada 0 determinística (seleção, inventário, módulos e chaves, extrações, git, briefing, corpo do `report`); entradas `build_report` e `build_briefing`. Ver [layer0/AGENTS.md](layer0/AGENTS.md).
- `harness/`: executores Claude Code e Codex somente leitura (prompt e schema versionados, timeout com kill da árvore, resgate, franquia e login, trava de ferramenta); ver [harness/AGENTS.md](harness/AGENTS.md).
- `doctor.py` e `cli.py` (`configure | run | doctor`, códigos de saída em `errors.py`); `logs.py` (JSON em stderr e arquivo diário com retenção).

**Não entra aqui**: código do servidor, testes (vão para `runner/tests/`), executáveis falsos (vão para `runner/tests/fakes/`).

**Convenções locais**: tipos estritos (pyright strict); nada de `print` fora de `cli.py`; mensagens de `fail`/`defer` vêm de modelos fixos (nunca stderr, saída do agente ou caminho absoluto); toda espera passa pela `Sleep` injetada e toda hora pelo `Clock` injetado.

**Como testar**: de `runner/`, `uv run pytest` (gate de 95% de linhas e branches).

**Leia também**: [runner/AGENTS.md](../../AGENTS.md); [docs/specs/runner.md](../../../docs/specs/runner.md).
