# backend/tests/workers/

**Função**: testes de `src/knobridge/workers/`: workflows, activities e o processo worker, e os do motor de ingestão de `src/knobridge/ingestion/` (`runs`, `indexer`, `store`, `sync`), que compartilham o harness do workflow.

**Entra aqui**: `test_health_workflow.py` (workflow e activity de saúde, incluindo retry), `test_worker.py` (`build_worker`, `connect`, `run`, `main`), `test_ingestion_workflow.py` (workflow de ingestão de ponta a ponta: indexa, reprocessa só o alterado, pula hash igual, remove, cache de embedding por hash de chunk, erro por documento, cursor só no sucesso, retry de falha transitória, cancelamento, uma execução por fonte, tokens e custo, lotes), `test_ingestion_steps.py` (sem Temporal: `start_sync`, idempotência de `open`/`list_changes`/`finish`/`process_batch`, casos de borda e os auxiliares puros), `ingestion_harness.py` (`database`: Postgres com workspace, credencial `fake` cifrada, coleção e fonte, conector `ScriptedConnector` e `RecordingEmbeddingFactory`, `RecordingStarter`; `harness`: o mesmo mais o servidor de teste do Temporal e um worker) e um arquivo por módulo novo de workflows. Nomes de arquivo não podem repetir os de outras pastas de teste (ex.: `test_health.py` já existe em `tests/api/`).
**Não entra aqui**: testes da lógica de domínio sem relação com a ingestão orquestrada (ficam na pasta do módulo correspondente, como parsing e chunking em `tests/ingestion/`).

**Convenções locais**:
- Workflow roda contra o servidor de teste do SDK: `WorkflowEnvironment.start_time_skipping()` dentro de `asyncio.run`, com um `Worker` na task queue do teste. Esses testes levam `@pytest.mark.integration` (baixam o binário na primeira execução). O time-skipping avança timers e backoff de retry, então nada de `sleep` nem hora real.
- O backoff entre tentativas de uma activity corre em tempo real no servidor de teste: teste de retry no workflow usa no máximo uma falha; esgotar tentativas se testa no passo isolado.
- Activity isolada: `ActivityEnvironment().run(activity, ...)`, sem servidor; os passos da ingestão são testados chamando `RunLifecycle`/`Indexer` direto.
- Para simular falha, registre uma activity fake com o mesmo `name` da real, ou configure os fakes (`ScriptedConnector.missing`, `fetch_unavailable`, `gate`; `RecordingEmbeddingProvider.error`, `fail_times`).
- Cancelamento: o worker do harness usa throttle de heartbeat de 50 ms e as activities, intervalo de 50 ms, para o pedido de cancelamento chegar logo.
- `run` e `main` são testados com client e worker fakes injetados (`connect_client=`, `worker_factory=`, ou `monkeypatch` em `worker.run`); nunca conecte num Temporal real.

**Como testar**: de `backend/`, `uv run pytest tests/workers` (exige Docker para o Postgres).

**Leia também**: [workers/AGENTS.md](../../src/knobridge/workers/AGENTS.md); [ingestion/AGENTS.md](../../src/knobridge/ingestion/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
