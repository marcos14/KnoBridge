# runner/src/knobridge_runner/harness/

**Função**: chamar o Claude Code e o Codex somente leitura sobre o checkout, do mesmo jeito para os dois: prompt e schema `schema_version: 1`, argumentos, ambiente por allowlist, timeout com kill da árvore, resgate na mesma sessão, franquia e login virando adiamento, trava de ferramenta e métricas. Contrato em [harness.md](../../../../docs/specs/harness.md) ("Prompt", "Schema da saída", "Executores").

**Entra aqui**:
- `prompt_v1.txt`, `rescue_prompt_v1.txt`, `schema_v1.json`: cópias literais dos blocos da spec (um teste compara). Mudou a spec, muda o recurso na mesma entrega; versão nova do schema ganha arquivo novo (`_v2`).
- `prompt.py` (`HarnessTask`, `build_prompt`, `schema_json`, `prompt_hash`), `schema_check.py` (validador do subconjunto estrito do schema, sem dependência nova).
- `process.py`: subprocesso com stdin binário em UTF-8, leitura de stdout linha a linha, timeout, trava, `CancelToken` e `kill_tree` (Windows `taskkill /F /T`; POSIX `killpg` SIGTERM, 10 s, SIGKILL).
- `failures.py`: detecção de franquia e login e leitura do horário de reset (relógio e fusos injetados).
- `base.py` (interface `Executor`, `ExecutorSetup`, `ExecutorLimits`, `ExecutorResult`, fluxo comum com resgate), `events.py` (`EventParser`, `AttemptStats`, leitura tipada de campos JSON), `claude_code.py`, `codex.py`; `make_executor` em `__init__.py`.

**Não entra aqui**: briefing e camada 0 (`layer0/`), verificação de fontes, excertos e montagem do resultado (`verify.py`, `excerpt.py`, `items.py`, `job.py`, no pacote acima), conversa com o servidor (`client.py`, `loop.py`).

**Convenções locais**:
- Nunca `shell=True`; argumentos em lista; cwd no checkout; arquivos temporários só em `work_dir` (fora do checkout).
- Ambiente do executor = `commands.child_environment` + `extra_environment` (só testes); nenhuma `KNOBRIDGE_*`.
- Nada de texto livre (stderr, saída do agente, caminho absoluto) sai daqui para o servidor: só códigos e números. O texto completo fica no log JSONL local (`log_dir`).
- Toda hora e todo fuso vêm do `ExecutorSetup` (`clock`, `now`, `zones`).

**Como testar**: de `runner/`, `uv run pytest` (executáveis falsos de `tests/fakes/`, gate de 95%); CLIs reais só com `KNOBRIDGE_RUNNER_REAL_HARNESS=1 uv run pytest -m real_harness --no-cov -s` (D17).

**Leia também**: [runner/AGENTS.md](../../../AGENTS.md); [docs/specs/harness.md](../../../../docs/specs/harness.md); seção 9 do [AGENTS.md da raiz](../../../../AGENTS.md).
