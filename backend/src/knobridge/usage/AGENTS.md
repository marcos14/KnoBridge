# backend/src/knobridge/usage/

**Função**: os números do painel. Consultas agregadas sobre `runs` e `messages` (sem tabela de métricas, D7 do [plano 0008](../../../../docs/planos/0008-telas-de-uso-e-administracao.md)) para **Uso e custos**, o painel do workspace (Início) e o painel da instância do superadmin, e as checagens de saúde dos serviços. Contrato em [docs/specs/uso-e-custos.md](../../../../docs/specs/uso-e-custos.md).

**Entra aqui**:
- `period.py`: `resolve_period(now, start, end)`: `[from, to)` em UTC (sem fuso = UTC), padrão de 30 dias antes de `to` (ou do relógio), `from >= to` → 422 `validation_error`, mais de 366 dias → `UsagePeriodTooLongError` (422 `usage_period_too_long`).
- `report.py`: `UsageGroup` (`source`, `collection`, `assistant`, `channel`, `api_key`, `model`, `day`), `EmbeddingUsage`, `ChatUsage`, `UsageTotals`, `UsageRow` (lado que não se aplica = `None`), `runs_in`/`answers_in` (execuções fechadas no período por `finished_at`; respostas com `model` por `created_at`; com `workspace_id=None`, a instância inteira), `usage_totals` (um statement) e `usage_rows` (um statement: o lado de embeddings e o de chat numa `UNION ALL` com cinco colunas genéricas, juntados em Python por `key`; `day` e `channel` saem com todas as linhas, dias vazios e os dois canais com zeros).
- `csv_export.py`: `usage_csv` (RFC 4180, `\r\n`, sem BOM, nulos vazios, US$ com 6 casas, linha `total`), `safe_text` (`'` antes de `=`, `+`, `-`, `@`) e `csv_filename`.
- `dashboard.py`: `workspace_dashboard(db, workspace_id=, now=, with_cost=)`: cartões (um statement de subconsultas escalares, com o custo do mês e `partial`) e checklist (um statement de `EXISTS`, ordem `CHECKLIST_KEYS`).
- `instance.py`: `instance_dashboard(db, now=, period=)` em modo de sistema: contagens, as 10 falhas mais recentes, totais do período e os 10 workspaces de maior custo (quatro statements).
- `health.py`: `TemporalProbe` (`Protocol`: `check_namespace`, `last_poller_seen`), `TemporalUnreachableError`, `instance_health` (banco, Temporal e worker em paralelo, `check_timeout` de 2 s cada; worker `ok` com poller nos últimos 60 s, `unknown` com o Temporal fora; `detail` curto e nosso, falha logada só pelo tipo). A implementação sobre o Temporal fica em `workers/temporal_health.py` (`TemporalHealthProbe`) e `workers/sync_client.py` (`LazyTemporalHealthProbe`).
- Sem routers (a API fica em `api/usage.py`, `api/dashboard.py` e `api/admin_dashboard.py`).

**Não entra aqui**: tabelas de preço (`llm/pricing.py`, `llm/chat_pricing.py`) e o cálculo do custo, gravado na execução (`ingestion/runs.py`) e na resposta (`conversations/chat.py`); totais de conversas e feedback da visão administrativa (`conversations/stats.py`); cliente Temporal (`workers/`).

**Convenções locais**:
- Custo desconhecido nunca vira zero na linha: as somas usam só os custos conhecidos (`COALESCE(SUM, 0)`) e os itens sem preço são contados à parte (`unpriced_runs`, `unpriced_answers`; `partial` no Início).
- Número constante de statements, qualquer que seja o número de linhas; testes contam os statements.
- Rotas de workspace rodam no escopo do workspace e filtram por `workspace_id`; o painel da instância roda em `system_session` só depois de `require_superadmin`.
- Expressões repetidas no `SELECT` e no `GROUP BY` usam constantes embutidas (`literal_column`), não parâmetros, para o Postgres reconhecer a mesma expressão.
- Este pacote importa os modelos de `ingestion/`, `conversations/`, `assistants/`, `apikeys/`, `llm/`, `tenancy/` e `security/` (só leitura); nenhum deles importa `usage/`.

**Como testar**: de `backend/`, `uv run pytest tests/usage tests/api/test_usage.py tests/api/test_usage_csv.py tests/api/test_dashboard.py tests/api/test_admin_dashboard.py tests/workers/test_temporal_health.py` (os de `tests/api` usam Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [docs/specs/uso-e-custos.md](../../../../docs/specs/uso-e-custos.md); [tests/usage/AGENTS.md](../../../tests/usage/AGENTS.md); [conversations/AGENTS.md](../conversations/AGENTS.md); [ingestion/AGENTS.md](../ingestion/AGENTS.md).
