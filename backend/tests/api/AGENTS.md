# backend/tests/api/

**Função**: testes de `src/knobridge/api/`: factory da aplicação, montagem dos routers sob `/v1`, CORS e cada endpoint.

**Entra aqui**: `test_app.py` (factory e `serve`) e um `test_<router>.py` por módulo de router (hoje `test_health.py`).
**Não entra aqui**: testes da lógica de domínio chamada pelos routers (ficam na pasta do módulo correspondente), testes dos handlers de erro genéricos (`tests/core/test_errors.py`).

**Convenções locais**:
- Use a fixture `client` de `tests/conftest.py`; chamadas sempre pelo caminho completo (`/v1/...`).
- Confira status HTTP e corpo inteiro da resposta; erros sempre no formato `{"error": {...}}`.
- Nada de servidor real nem porta aberta: `uvicorn.run` é substituído por fake nos testes de `serve`.
- Falha de dependência em teste unitário: substitua a função chamada pelo router (ex.: `monkeypatch.setattr(health, "ping", ...)`); o caminho feliz com banco real é teste de integração com `postgres_url` e `create_app(settings com database_url)`.

**Como testar**: de `backend/`, `uv run pytest tests/api`.

**Leia também**: [api/AGENTS.md](../../src/knobridge/api/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
