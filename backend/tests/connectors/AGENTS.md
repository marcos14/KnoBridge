# backend/tests/connectors/

**Função**: testes de `src/knobridge/connectors/`: o contrato, a seleção de arquivos e cada conector, sempre sobre árvores sintéticas criadas em `tmp_path`.

**Entra aqui**:
- `connectors_support.py`: `write(root, key, content, tick=)` (arquivo com mtime fixo, `tick` segundos depois de uma base; nunca o relógio real) e `symlink_or_skip`.
- `test_connector_base.py` (valores e erros do contrato), `test_selection.py` (`.gitignore` aninhado, diretórios padrão, binários, zips, lockfiles, documentos PDF/Office mantidos com limite próprio, limite de tamanho, globs, raiz e chaves fora da raiz, escape por symlink e por junção do Windows), `test_folder_connector.py` (mudanças, cursor compacto, atalho por mtime, metadados do `fetch`, settings).
- `contract/`: a suíte de contrato, parametrizada por fonte (ver o `AGENTS.md` dela).
- Um `test_<conector>_connector.py` por conector novo, nesta pasta (o pytest só importa `connectors_support` por basename a partir daqui).

**Não entra aqui**: fakes de conector (`tests/fakes/connector.py`), fixtures com dados reais, repositórios ou pastas fora de `tmp_path`.

**Convenções locais**:
- Testes de symlink usam `symlink_or_skip`: pulam só no Windows sem o privilégio de criar symlink (WinError 1314); a CI Linux sempre os roda. O de junção roda só no Windows.
- Escreva com `write` para o mtime ser determinístico; mudança de conteúdo com o mesmo tamanho precisa de outro `tick`.

**Como testar**: de `backend/`, `uv run pytest tests/connectors`.

**Leia também**: [connectors/AGENTS.md](../../src/knobridge/connectors/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
