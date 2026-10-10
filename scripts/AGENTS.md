# scripts/

**Função**: automação do repositório, principalmente as checagens que a CI roda além dos gates de cada pacote. É um projeto Python próprio (`knobridge-scripts`, gerenciado por `uv`), separado do backend para não misturar dependências.

**Entra aqui**:
- `check_agents_md.py`: falha se alguma pasta não tiver `AGENTS.md` (regra da seção 4 do [AGENTS.md da raiz](../AGENTS.md)).
- `check_plans.py`: valida o frontmatter de `docs/planos/NNNN-slug.md` contra o [modelo](../docs/planos/0000-modelo.md).
- Outros scripts de checagem ou geração de código usados pela CI ou pelos hooks, cada um com testes em `tests/`.

**Não entra aqui**: código do produto (`backend/`, `frontend/`, `widget/`), infraestrutura (`deploy/`), workflows de CI (`.github/workflows/`), documentação (`docs/`).

**Convenções locais**:
- Um script por arquivo `check_*.py` (ou nome equivalente), sem dependência entre eles, executável com `uv run python <script>.py`.
- Todo script expõe `main(argv: list[str] | None = None) -> int` e devolve o código de saída: 0 ok, 1 problema encontrado, 2 entrada inválida. Só o bloco `__main__` chama `sys.exit`.
- Scripts são CLI: escrever no stdout é permitido aqui (problemas um por linha, caminhos com `/`).
- Caminhos padrão são relativos à raiz do repositório (pai desta pasta), para funcionar de qualquer diretório.
- Testes montam árvores sintéticas em `tmp_path`; só os testes marcados com `repo` olham o repositório real.

**Como testar** (de dentro de `scripts/`):

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest            # inclui --cov --cov-branch --cov-fail-under=95
uv run pytest -m "not repo"   # só os testes sintéticos
uv run python check_agents_md.py && uv run python check_plans.py
```

**Leia também**: seções 3, 4 e 5 do [AGENTS.md da raiz](../AGENTS.md); [docs/planos/AGENTS.md](../docs/planos/AGENTS.md).
