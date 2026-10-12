# runner/src/knobridge_runner/layer0/

**Função**: a camada 0 do harness de código, determinística, sem LLM e sem rede: seleção de arquivos do checkout, inventário, sugestão de módulos com chave estável, extrações baratas por regex, consultas `git` e o briefing de um módulo. Produz o corpo do `report` (`build_report`) e o briefing de uma tarefa (`build_briefing`). Contrato em [harness.md](../../../../docs/specs/harness.md#camada-0) e [runner.md](../../../../docs/specs/runner.md#post-v1runnersourcessource_idreport).

**Entra aqui** (um módulo por responsabilidade):
- `selection.py`: regras de seleção (diretórios padrão, `.gitignore` aninhado com `pathspec`, lockfiles, binários, globs da fonte, 2 MiB, NUL, symlinks); `inventory.py`: decodificação (UTF-8, senão Windows-1252), contagem de linhas, linguagem por extensão e totais.
- `modules.py` (sugestão por pasta com tamanho-alvo, padrões gitwildmatch, limite de 2000 módulos) e `keys.py` (chave estável e colisões).
- `extract.py`: mensagens ao usuário, variáveis de ambiente, rotas HTTP e documentação do módulo, com `arquivo:linha`.
- `git.py`: `GitRepository` (HEAD, branch, commit existe, alterados entre commits, `git log` curto) sobre o `CommandRunner` injetado, sempre com `-c safe.directory=<checkout>`.
- `briefing.py` (texto pt-BR, até 24 000 caracteres, corte de baixo para cima) e `report.py` (entradas de alto nível e pathspecs do `git log`).

**Não entra aqui**: chamada de executor, prompt, verificação de evidências e excertos (ficam em `knobridge_runner/`: `harness/`, `verify.py`, `excerpt.py`); quem decide quando reportar (`reporter.py`, chamado pelo `loop.py`); nada do backend. `changed_paths_since` (em `report.py`) serve ao `report` e aos `changed_paths` do resultado da tarefa (`job.py`).

**Convenções locais**:
- Nada daqui sai da máquina além de caminhos relativos e contagens (`RunnerReportIn`); extrações, `git log` e briefing são só locais. Nunca logue conteúdo de arquivo.
- `git` só pelo `CommandRunner` (sem shell, ambiente por allowlist); crie-o com `GIT_TIMEOUT_SECONDS` (60 s).
- Padrões de módulo sem barra invertida (o protocolo recusa): caracteres de glob em nomes de pasta viram `?`. A pasta de arquivos diretos usa `d/*` + `!d/*/**` (não `!d/*/`: `*` casa em qualquer nível no gitwildmatch).

**Como testar**: de `runner/`, `uv run pytest tests/test_layer0_*.py` (repositórios Git sintéticos em `tmp_path`); o gate de 95% vale para o pacote inteiro com `uv run pytest`.

**Leia também**: [runner/AGENTS.md](../../../AGENTS.md); [docs/specs/harness.md](../../../../docs/specs/harness.md); [docs/specs/conectores.md](../../../../docs/specs/conectores.md#seleção-de-arquivos) (as mesmas regras de seleção no servidor).
