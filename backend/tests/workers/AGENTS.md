# backend/tests/workers/

**Função**: testes de `src/knobridge/workers/`: workflows, activities e o processo worker.

**Entra aqui**: `test_health_workflow.py` (workflow e activity de saúde, incluindo retry), `test_worker.py` (`build_worker`, `connect`, `run`, `main`) e um arquivo por módulo novo de workflows. Nomes de arquivo não podem repetir os de outras pastas de teste (ex.: `test_health.py` já existe em `tests/api/`).
**Não entra aqui**: testes da lógica de domínio que as activities chamam (ficam na pasta do módulo correspondente).

**Convenções locais**:
- Workflow roda contra o servidor de teste do SDK: `WorkflowEnvironment.start_time_skipping()` dentro de `asyncio.run`, com um `Worker` na task queue do teste. Esses testes levam `@pytest.mark.integration` (baixam o binário na primeira execução). O time-skipping avança timers e backoff de retry, então nada de `sleep` nem hora real.
- Activity isolada: `ActivityEnvironment().run(activity, ...)`, sem servidor.
- Para simular falha, registre uma activity fake com o mesmo `name` da real.
- `run` e `main` são testados com client e worker fakes injetados (`connect_client=`, `worker_factory=`, ou `monkeypatch` em `worker.run`); nunca conecte num Temporal real.

**Como testar**: de `backend/`, `uv run pytest tests/workers`.

**Leia também**: [workers/AGENTS.md](../../src/knobridge/workers/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
