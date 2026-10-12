# backend/tests/audit/

**Função**: testes de `src/knobridge/audit/`: gravação na mesma transação, consulta com filtros e paginação, e isolamento por RLS de `audit_events`.

**Entra aqui**: `test_audit_service.py` (`record`, imutabilidade, retenção), `test_audit_queries.py` (`list_audit_events`), `test_audit_rls.py` (isolamento entre workspaces e eventos da instância); `conftest.py` com `run_db` (papel dono), `run_rls_db` (parametrizada: dono e não dono), `clock` (`FrozenClock`) e `audit` (`AuditService` com esse relógio); `audit_support.py` com `RunScenario`, `SessionFactory`, `START`, `Tenants` e `seed_tenants`.
**Não entra aqui**: testes da futura rota de consulta (`tests/api/`), da cadeia de migrações (`tests/migrations/`).

**Convenções locais**:
- Testes com banco levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces e usuários (`seed_tenants`) e filtra por eles, nunca conta linhas globais (exceto `>=`).
- Testes de RLS usam `run_rls_db` e conferem workspace alheio, sessão sem escopo e eventos da instância.
- Tempo só pelo `FrozenClock` (`advance`); nunca `sleep`.

**Como testar**: de `backend/`, `uv run pytest tests/audit` (exige Docker).

**Leia também**: [audit/AGENTS.md](../../src/knobridge/audit/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
