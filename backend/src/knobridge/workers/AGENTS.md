# backend/src/knobridge/workers/

**Função**: processo worker do Temporal (`knobridge-worker`) e os workflows e activities que ele executa. Hoje só o workflow de saúde; os workflows de pipeline chegam com `pipelines/`.

**Entra aqui**:
- `worker.py`: registro central (`WORKFLOWS`, `ACTIVITIES`), `connect(settings)` (`Client` em `temporal_address`/`temporal_namespace`), `build_worker(client, settings)` (worker na `temporal_task_queue`), `run(settings=None, *, connect_client=, worker_factory=)` assíncrono com dependências injetáveis e `main()`, o entry point `knobridge-worker`.
- `health.py`: `HealthWorkflow` (`knobridge.health.v1`), que executa a activity `ping` (`knobridge.health.ping.v1`) com timeout e `RetryPolicy` explícitos.
- Um módulo por grupo de workflows e activities quando surgirem (ex.: `pipeline_runs.py`).

**Não entra aqui**: lógica de domínio (fica no módulo do domínio; a activity só a chama), modelo e compilação do grafo de pipeline (`pipelines/`), adaptadores de provedores externos (`llm/`, `connectors/`, `channels/`).

**Convenções locais**:
- Workflows são determinísticos: sem IO, sem hora real (`workflow.now()`), sem aleatoriedade fora de `workflow.random()`. O módulo de um workflow importa só `temporalio`, a biblioteca padrão e código igualmente puro, porque roda no sandbox do SDK.
- IO só em activities. Toda activity é idempotente (hash por documento, upsert por chave natural) e chamada com `start_to_close_timeout` e `RetryPolicy` explícitos, nunca com o padrão do SDK.
- Nomes de workflow e activity são estáveis e versionados (`knobridge.<area>.<nome>.vN`) via `@workflow.defn(name=...)` e `@activity.defn(name=...)`. Mudança incompatível = nome novo `vN+1` (ou `workflow.patched`), mantendo o antigo registrado até as execuções em curso terminarem.
- Todo workflow e activity novo entra em `WORKFLOWS`/`ACTIVITIES` de `worker.py`, com teste.
- Logs com `workspace_id` e `run_id` via `log_context` nas activities.

**Como testar**: de `backend/`, `uv run pytest tests/workers` (usa `WorkflowEnvironment.start_time_skipping()`, que baixa o servidor de teste na primeira execução; gate de cobertura na suíte inteira com `uv run pytest`).

**Leia também**: [backend/AGENTS.md](../../../AGENTS.md) (convenções Temporal); [tests/workers/AGENTS.md](../../../tests/workers/AGENTS.md); seção 6 da [visão](../../../../docs/01-visao-do-projeto.md).
