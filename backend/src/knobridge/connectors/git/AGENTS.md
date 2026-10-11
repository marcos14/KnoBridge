# backend/src/knobridge/connectors/git/

**Função**: conector Git (decisão D4 do [plano 0003](../../../../../docs/planos/0003-primeiro-conhecimento.md)): os arquivos do HEAD da branch, com a seleção compartilhada, e os commits como documentos, incremental por SHA, sempre pelo binário `git` em subprocesso.

**Entra aqui**:
- `runner.py`: `GitRunner(binary=, timeout=, env=)` (`asyncio.create_subprocess_exec`, sem shell, timeout com `kill` do processo; `-c safe.directory=<repo>`, `core.fsmonitor=false`, `--literal-pathspecs`, `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`) e `GitCommandError` (`returncode`; o stderr vai para o log e para `.stderr`, nunca para `details`).
- `repository.py`: `Repository`, consultas somente leitura pelos objetos (`resolve`, `tree` via `ls-tree`, `read_blob(s)` via `cat-file`, `changed_paths` via `diff --no-renames`, `commits` via `rev-list`, `is_ancestor`, `commit`), e os parsers.
- `location.py`: `LocalLocation` (`path` dentro de `KNOBRIDGE_LOCAL_SOURCES_ROOT`, lido no lugar) e `RemoteLocation` (`url` clonada em `KNOBRIDGE_GIT_WORKDIR/<sha256(url)[:24]>`).
- `commits.py`: `commit_document` (`RawDocument` de um commit) e `COMMIT_KEY_PREFIX`.
- `connector.py`: `GitConnector`, `GitCursor` e `create_git_connector(config, settings, include_globs=, exclude_globs=)`.

**Não entra aqui**: regras de seleção (`../selection.py`, via `PathRules`), validação da configuração (`ingestion/source_config.py`), banco, parsing.

**Convenções locais**:
- Conteúdo sempre pelos objetos do Git (`ls-tree` + `cat-file`), nunca pelo worktree: o caminho local é montado somente leitura (nada de `fetch`, `checkout` ou escrita nele), mudanças não commitadas não vazam e repositório bare funciona. O caminho tem de ser a raiz do repositório (pasta dentro de um repositório é recusada) e o `git-common-dir` (worktree ligado) também tem de estar dentro da raiz permitida.
- `safe.directory`: a montagem costuma ter outro dono que o usuário do worker, e o git recusa o repositório; o runner passa `-c safe.directory=<caminho>` (escopo protegido, que o git respeita) só para aquele caminho.
- URL: clone parcial (`--filter=blob:none --no-checkout`), `fetch --prune --force` antes de cada listagem e `checkout --detach` do HEAD, que baixa os blobs faltantes num lote só. Produção só aceita `https` (`protocol.allow=never` + `protocol.https.allow=always`); testes injetam `allowed_protocols={"file"}` e `url_rewriter`. `test_connection` usa `ls-remote` sem clonar. Clone pela metade é apagado e refeito.
- Branch: `None` = `HEAD` (local) ou `refs/remotes/origin/HEAD` (URL); nomeada = `refs/heads/<b>` e, no local, `refs/remotes/origin/<b>` como alternativa. Inexistente = `BranchNotFoundError` (422).
- Seleção: `ls-tree` dá caminho e tamanho; `PathRules` aplica diretórios padrão, `.gitignore` lidos da árvore do commit (mesmo para arquivo rastreado), lockfiles, binários por extensão, globs e limites; só blobs novos ou alterados são lidos (em lotes de ~32 MiB) para a checagem de NUL. Symlinks e submódulos ficam de fora.
- Cursor: `{"kind": "git", "version": 1, "head": sha, "commit": sha, "paths": [...]}`. `paths` são as chaves selecionadas no `head`: permitem saber o que remover quando o SHA do cursor sumiu (force-push + gc) e manter a seleção certa quando `.gitignore` ou globs mudam sem o arquivo mudar. Com o `head` presente, os arquivos tocados vêm de `git diff --no-renames` (renomeação = chave antiga removida + nova adicionada); sem ele, reconstrução: tudo que está em `paths` e continua selecionado vai em `changed`, o resto em `added`/`removed`.
- Commits: chave e URI `commit:<sha>`, `DocumentKind.COMMIT`, sempre em `added`; na primeira sincronização (ou na reconstrução) só os `initial_commit_limit` mais recentes, depois todos os novos desde `commit`. Conteúdo: só a mensagem completa (hash = SHA-256 dela, estável porque o commit não muda); SHA, autor (só o nome), datas ISO e arquivos tocados com status (`-M`; merge contra o primeiro pai; até 500, com `files_total`) vão nos `metadata`, de onde `ingestion/commits.py` monta o Markdown. Não repita esses dados no conteúdo: sairiam duas vezes no trecho embedado. E-mail do autor e committer ficam de fora (LGPD, minimização: o nome basta para citar). `fetch` de commit fora da branch é `DocumentNotFoundError`.
- Arquivo: URI = caminho POSIX; `metadata` com `path`, `commit` (HEAD lido), `size_bytes`, `format`.

**Como testar**: de `backend/`, `uv run pytest tests/connectors` (`test_git_connector.py`, `test_git_commits.py`, `test_git_remote.py` e a suíte de contrato, com repositórios sintéticos em `tmp_path`).

**Leia também**: [connectors/AGENTS.md](../AGENTS.md); [tests/connectors/AGENTS.md](../../../../tests/connectors/AGENTS.md).
