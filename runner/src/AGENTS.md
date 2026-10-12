# runner/src/

**Função**: raiz do layout `src/` do runner. Existe só para que o pacote `knobridge_runner` seja importado a partir da instalação (`uv sync`, `uv tool install`), e não do diretório corrente.

**Entra aqui**: apenas o pacote [`knobridge_runner/`](knobridge_runner/AGENTS.md).
**Não entra aqui**: módulos soltos, scripts, testes (vão para `runner/tests/`), configuração (fica em `runner/pyproject.toml`).

**Convenções locais**: nenhum outro pacote de primeiro nível; tudo o que é código do runner vive dentro de `knobridge_runner/`.

**Como testar**: de `runner/`, `uv run pytest` (gate de 95% de linhas e branches).

**Leia também**: [runner/AGENTS.md](../AGENTS.md).
