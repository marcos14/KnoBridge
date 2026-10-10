# backend/src/

**Função**: raiz do layout `src/` do backend. Existe só para que o pacote `knobridge` seja importado a partir da instalação (`uv sync`), e não do diretório corrente.

**Entra aqui**: apenas o pacote [`knobridge/`](knobridge/AGENTS.md).
**Não entra aqui**: módulos soltos, scripts, testes (vão para `backend/tests/`), configuração (fica em `backend/pyproject.toml`).

**Convenções locais**: nenhum outro pacote de primeiro nível sem ADR; tudo o que é código do produto vive dentro de `knobridge/`.

**Como testar**: de `backend/`, `uv run pytest` (gate de 95% de linhas e branches).

**Leia também**: [backend/AGENTS.md](../AGENTS.md).
