# backend/src/knobridge/

**Função**: pacote Python do KnoBridge. Cada subpasta é um módulo do produto (layout previsto em [backend/AGENTS.md](../../AGENTS.md)); hoje existem `core/`, `api/`, `tenancy/`, `security/`, `audit/`, `email/` e `workers/`.

**Entra aqui**:
- `__init__.py` com `__version__`, a única fonte da versão (o `pyproject.toml` lê daqui via hatch).
- Um subpacote por módulo do produto, cada um com o seu `AGENTS.md`.

**Não entra aqui**: testes (vão para `backend/tests/`, espelhando esta árvore), documentação (`docs/`), scripts de repositório (`scripts/`), módulos soltos na raiz do pacote além de `__init__.py`.

**Convenções locais**:
- Crie um subpacote só quando ele for necessário, sempre com `AGENTS.md` e testes em `tests/<subpacote>/`.
- Dependências entre módulos apontam para baixo: `api/` e `workers/` usam `core/` e os módulos de domínio; `core/` não importa nenhum outro módulo do pacote.
- Vocabulário do domínio da seção 6.1 do [AGENTS.md da raiz](../../../AGENTS.md) nos nomes.

**Como testar**: de `backend/`, `uv run pytest` (gate de 95% de linhas e branches) e `uv run pyright`.

**Leia também**: [core/AGENTS.md](core/AGENTS.md), [tenancy/AGENTS.md](tenancy/AGENTS.md), [security/AGENTS.md](security/AGENTS.md), [audit/AGENTS.md](audit/AGENTS.md), [email/AGENTS.md](email/AGENTS.md), [api/AGENTS.md](api/AGENTS.md), [workers/AGENTS.md](workers/AGENTS.md).
