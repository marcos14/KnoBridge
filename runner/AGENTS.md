# runner/

**Função**: o `knobridge-runner`, que roda na máquina do usuário (onde estão o checkout e o login do Claude Code ou do Codex), conversa com o servidor só por HTTPS de saída (`/v1/runner/*`) e executa o harness de código somente leitura. Projeto `uv` próprio, separado do backend para não levar FastAPI, SQLAlchemy, MarkItDown e tree-sitter à máquina do usuário ([ADR 0005](../docs/adr/0005-runner-local-do-harness.md), decisões D7 e D16 do [plano 0004](../docs/planos/0004-harness-runner-local.md)). Estado: configuração, cliente do protocolo com retentativas, laço principal com processador injetável e CLI `configure | run | doctor` (F3.1); camada 0, executores e verificação vêm nas F3.2 a F3.4.

**Entra aqui**: código em `src/knobridge_runner/`, testes em `tests/`, `pyproject.toml`, `uv.lock`, `README.md` (instalar, configurar, rodar).
**Não entra aqui**: código do servidor (fila, rotas e validação do resultado ficam em `backend/`), documentação e specs (vão para `docs/`, em especial [runner.md](../docs/specs/runner.md) e [harness.md](../docs/specs/harness.md)), checkouts ou código real de terceiros.

**Convenções locais**:
- Nunca importe `knobridge` (o backend). O contrato com o servidor são os modelos de `protocol.py`/`protocol_result.py`, iguais à spec; pequenas duplicações (formatos, padrões de seleção) são aceitas.
- Dependências mínimas: `httpx` e `pydantic` (e `pathspec` quando a camada 0 chegar). Nada de framework de LLM.
- Tudo que fala com o mundo é injetado: transporte HTTP, relógio, espera, comandos locais (`CommandRunner`), verificação de login (`AuthChecker`), `which`, processador de tarefa (`JobProcessor`). O `World` da CLI junta essas dependências.
- Nada sai da máquina além do que a spec lista em "O que sai e o que não sai": nada de caminho absoluto, conteúdo de arquivo, prompt, stderr ou e-mail da conta em payload ou log.
- Logs JSON (`logs.py`) com ids, códigos e contagens; `print` só em `cli.py` (saída para o usuário, em pt-BR).
- Variáveis `KNOBRIDGE_RUNNER_*` só são lidas em `config.py`; subprocessos recebem o ambiente por allowlist (`commands.child_environment`).

**Como testar** (de dentro de `runner/`, com `PYTHONUTF8=1` no Windows):

```sh
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest            # inclui --cov --cov-branch --cov-fail-under=95
KNOBRIDGE_RUNNER_REAL_HARNESS=1 uv run pytest -m real_harness --no-cov   # opt-in, CLIs reais (D17)
```

A suíte padrão não chama rede, LLM nem CLI real: servidor por `httpx.MockTransport`, executores e login por fakes, `git` real só em repositórios criados em `tmp_path`. Testes marcados `real_harness` são pulados sem a variável; a CI nunca a liga.

**Leia também**: seções 2, 5, 6 e 9 do [AGENTS.md da raiz](../AGENTS.md); [docs/specs/runner.md](../docs/specs/runner.md); [docs/specs/harness.md](../docs/specs/harness.md); CI em `.github/workflows/ci.yml` (job `runner`).
