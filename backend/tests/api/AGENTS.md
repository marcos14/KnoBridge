# backend/tests/api/

**Função**: testes de `src/knobridge/api/`: factory da aplicação, montagem dos routers sob `/v1`, CORS e cada endpoint.

**Entra aqui**: `test_app.py` (factory e `serve`), um `test_<router>.py` por módulo de router (`test_health.py`, `test_setup.py`, `test_auth.py`, `test_me.py`, `test_recovery.py`, `test_account.py`, `test_audit_routes.py`, com nome distinto de `tests/audit/`), `test_deps.py` (dependências compartilhadas, por rotas de sonda adicionadas ao app real), `conftest.py` com as fixtures `api` (app com `FrozenClock`, argon2 barato, `FakeEmailSender` e `cookie_secure=False` sobre o banco compartilhado `app_database_url`) e `empty_api` (o mesmo sobre `empty_database_url`), e `api_support.py` (`ApiEnv` com `emails` (o fake), `create_user`, `create_workspace`, `set_user_status`, `login`, `csrf_headers`, `emailed_token`, `sessions`, `user`, `audit_actions`; `run_db`; constantes).
**Não entra aqui**: testes da lógica de domínio chamada pelos routers (ficam na pasta do módulo correspondente), testes dos handlers de erro genéricos (`tests/core/test_errors.py`).

**Convenções locais**:
- Sem banco, use a fixture `client` de `tests/conftest.py`; com banco, `api` ou `empty_api` (marque `@pytest.mark.integration`). Chamadas sempre pelo caminho completo (`/v1/...`).
- Banco compartilhado: crie usuários e workspaces pelo `ApiEnv` (e-mails e slugs únicos) e não conte linhas globais. Tempo só por `api.clock.advance`.
- Eventos de auditoria gravados no mesmo instante do `FrozenClock` não têm ordem garantida entre si: confira com `in`/subconjunto, não pela posição.
- E-mails: confira `api.emails` (o fake) e pegue o token do link com `api.emailed_token(endereço)`.
- Rota não segura autenticada: mande `headers=api.csrf_headers()` e teste também a recusa sem o header.
- Confira status HTTP e corpo inteiro da resposta; erros sempre no formato `{"error": {...}}`.
- Nada de servidor real nem porta aberta: `uvicorn.run` é substituído por fake nos testes de `serve`.
- Falha de dependência em teste unitário: substitua a função chamada pelo router (ex.: `monkeypatch.setattr(health, "ping", ...)`); o caminho feliz com banco real é teste de integração com `postgres_url` e `create_app(settings com database_url)`.

**Como testar**: de `backend/`, `uv run pytest tests/api`.

**Leia também**: [api/AGENTS.md](../../src/knobridge/api/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
