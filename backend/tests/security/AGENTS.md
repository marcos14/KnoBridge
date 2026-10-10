# backend/tests/security/

**Função**: testes de `src/knobridge/security/`: senha, tokens, sessões, CSRF, limitação de login e o isolamento por RLS de `sessions`, `user_tokens` (por usuário e, nos tokens de convite, por workspace) e `login_attempts`.

**Entra aqui**: um `test_<módulo>.py` por módulo (`test_passwords.py`, `test_tokens.py`, `test_sessions.py`, `test_csrf.py`, `test_throttle.py`); `conftest.py` com as fixtures `run_db` (banco migrado, papel dono), `run_rls_db` (parametrizada: dono e não dono) e `clock` (`FrozenClock`); `security_support.py` com tipos e helpers compartilhados (`RunScenario`, `SessionFactory`, `START`, `create_user`), importado pelo nome porque o pytest põe esta pasta no `sys.path`.
**Não entra aqui**: testes das futuras rotas de autenticação (`tests/api/`), da cadeia de migrações (`tests/migrations/`), do `Clock` (`tests/core/test_clock.py`).

**Convenções locais**:
- Testes com banco levam `@pytest.mark.integration` e rodam o cenário async por `run_db(scenario)` ou `run_rls_db(scenario)`; usuários são criados com e-mails únicos (banco compartilhado pela sessão de testes).
- Tempo só pelo `FrozenClock` da fixture `clock` (`advance` para simular espera); nunca `sleep`.
- argon2 com parâmetros baratos (`CHEAP`) para a suíte ser rápida; os padrões de produção são verificados por igualdade.
- Testes de RLS usam `run_rls_db` e conferem que outro usuário e uma sessão sem escopo não veem as linhas.

**Como testar**: de `backend/`, `uv run pytest tests/security` (exige Docker).

**Leia também**: [security/AGENTS.md](../../src/knobridge/security/AGENTS.md); [tests/AGENTS.md](../AGENTS.md); [ADR 0002](../../../docs/adr/0002-sessao-server-side.md).
