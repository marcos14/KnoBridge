# runner/tests/

**Função**: testes do runner, um arquivo por área do pacote `knobridge_runner` (`test_client.py`, `test_loop.py`, `test_config.py`, `test_cli.py`, `test_doctor.py`, `test_machine.py`, `test_protocol.py`, `test_logs.py`).

**Entra aqui**:
- `conftest.py`: pula os testes marcados `real_harness` sem `KNOBRIDGE_RUNNER_REAL_HARNESS=1` (D17) e restaura o logging depois de cada teste.
- `runner_support.py`: fakes compartilhados, importados pelo basename: `FakeServer` (rotas de `/v1/runner/*` sobre `httpx.MockTransport`, com as requisições gravadas), `FakeClock`, `FakeSleep` (grava as esperas e avança o relógio sem esperar), `FakeCommandRunner`, `FakeAuth`, `make_client`, `make_config` e corpos de resposta de exemplo.
- `layer0_support.py`: repositório Git sintético em `tmp_path` (`make_repo`, `commit_all`, `write`, `git`), `local_runner` com o timeout do git e `repo_file`; usado por `test_layer0_*.py` (camada 0).
- `harness_support.py`: `FakeRun` (roda os falsos de `fakes/` como `[python, script]`, com relógio e fuso fixos); testes do harness em `test_harness_executors.py`, `test_harness_process.py`, `test_harness_prompt.py` e `test_harness_failures.py`.
- `fakes/` (`claude`/`codex` falsos) e `real_harness/` (suíte opt-in, D17), cada uma com o seu `AGENTS.md`.

**Não entra aqui**: código de produção, chamadas de rede reais, LLM ou CLI real fora de `real_harness`, repositórios ou código reais.

**Convenções locais**:
- Nome `test_<unidade>_<comportamento>`, arrange / act / assert, um comportamento por teste.
- Sem rede, sem `sleep` real, sem hora real, sem aleatoriedade sem semente. Código async roda com `asyncio.run` dentro do teste.
- `git` real só em repositórios criados em `tmp_path`.
- Sem `__init__.py`: basenames de arquivo de teste únicos.

**Como testar**: de `runner/`, `uv run pytest` (cobertura de linhas e branches com `--cov-fail-under=95`).

**Leia também**: seção 5 do [AGENTS.md da raiz](../../AGENTS.md); [runner/AGENTS.md](../AGENTS.md).
