# backend/tests/core/

**Função**: testes unitários de `src/knobridge/core/` (settings, logging e erros).

**Entra aqui**: um `test_<módulo>.py` por módulo de `core/` (`test_settings.py`, `test_logging.py`, `test_errors.py`).
**Não entra aqui**: testes de routers do produto (vão para `tests/api/`), testes de integração com banco.

**Convenções locais**:
- Variáveis de ambiente só via `monkeypatch.setenv`; a fixture automática de `tests/conftest.py` limpa as `KNOBRIDGE_*` do host.
- Logging é verificado passando um `io.StringIO` para `configure_logging(..., stream=)` e lendo as linhas JSON.
- Handlers de erro são testados com um app FastAPI mínimo montado no próprio teste.

**Como testar**: de `backend/`, `uv run pytest tests/core`.

**Leia também**: [core/AGENTS.md](../../src/knobridge/core/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
