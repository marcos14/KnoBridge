# backend/tests/usage/

**Função**: testes unitários de `src/knobridge/usage/`: o período das consultas de uso, o CSV do relatório e as checagens de saúde da instância.

**Entra aqui**: `test_usage_period.py` (padrão de 30 dias, UTC, `from < to`, limite de 366 dias e `usage_period_too_long`), `test_usage_csv_export.py` (cabeçalho, linha `total`, nulos vazios, 6 casas, aspas RFC 4180, proteção contra fórmula e nome do arquivo) e `test_instance_health.py` (checagens em paralelo com o `FakeTemporalProbe` e um ping falso: tudo ok, banco fora sem a mensagem do driver, worker sem poller recente, fila ilegível, Temporal fora com worker `unknown` e timeout com `check_timeout=0`; reranker `disabled` sem sonda, `reranker not ready` e `reranker unreachable` sem a mensagem do erro, com o `FakeRerankerProbe`).
**Não entra aqui**: as agregações contra Postgres real e as rotas (ficam em `tests/api/test_usage.py`, `test_usage_csv.py`, `test_dashboard.py` e `test_admin_dashboard.py`, porque o caminho natural de montar os dados é o mundo das APIs), o `TemporalHealthProbe` e o `LazyTemporalHealthProbe` (`tests/workers/test_temporal_health.py`).

**Convenções locais**:
- Nomes de arquivo únicos na suíte inteira (`tests/` não tem `__init__.py`): por isso `test_instance_health.py`, e não `test_health.py`.
- Sem banco nem rede; relógio `FrozenClock`; sem `sleep` (o timeout usa um evento nunca disparado com `check_timeout=0`).

**Como testar**: de `backend/`, `uv run pytest tests/usage` (gate da suíte inteira: `uv run pytest`).

**Leia também**: [usage/AGENTS.md](../../src/knobridge/usage/AGENTS.md); [tests/AGENTS.md](../AGENTS.md); [docs/specs/uso-e-custos.md](../../../docs/specs/uso-e-custos.md).
