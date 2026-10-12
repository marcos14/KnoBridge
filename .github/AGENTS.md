# .github/

**Função**: configuração do GitHub para o repositório. Hoje, só os workflows de CI em `workflows/`, que rodam os gates da seção 8 do [AGENTS.md da raiz](../AGENTS.md) em todo pull request e em todo push na `main`.

**Entra aqui**:
- `workflows/`: workflows do GitHub Actions (ver [workflows/AGENTS.md](workflows/AGENTS.md)).
- Futuramente, se o usuário pedir: modelos de issue e de PR, `CODEOWNERS`, configuração do Dependabot.

**Não entra aqui**:
- Scripts que os workflows chamam: vão para `scripts/` (com testes) ou para o pacote correspondente.
- Hooks locais de pre-commit: `.pre-commit-config.yaml` na raiz.
- Documentação e guias: `docs/`. `CONTRIBUTING.md` fica na raiz.
- Segredos de qualquer tipo: só em *secrets* do GitHub, nunca em arquivo.

**Convenções locais**:
- YAML com indentação de 2 espaços, comentários em inglês.
- Toda mudança aqui passa no `actionlint` antes da entrega.

**Como testar**: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12` na raiz do repositório.

**Leia também**: [workflows/AGENTS.md](workflows/AGENTS.md); seções 8 e 9 do [AGENTS.md da raiz](../AGENTS.md).
