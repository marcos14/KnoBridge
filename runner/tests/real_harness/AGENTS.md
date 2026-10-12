# runner/tests/real_harness/

**Função**: suíte opt-in que chama o `claude` e o `codex` **reais** (logados na máquina) sobre um repositório sintético pequeno, para conferir flags, formato do JSONL e resgate contra as versões instaladas, o que os falsos não garantem (decisão D17 do [plano 0004](../../../docs/planos/0004-harness-runner-local.md)).

**Entra aqui**: testes marcados `real_harness` (`pytestmark`), com repositório criado em `tmp_path` (`git init`, poucos arquivos de uma regra inventada): `test_real_harness.py` (executor sozinho; também exporta `make_repository`, `tree_digest` e `git`) e `test_real_job.py` (ciclo completo do `Runner` com `HarnessJobProcessor` e `FakeServer`: report, claim, heartbeat, verificação e resultado).
**Não entra aqui**: testes da suíte padrão (vão para `runner/tests/`), código ou repositório real, chaves ou saídas gravadas de CLIs reais.

**Convenções locais**:
- Pulados sem `KNOBRIDGE_RUNNER_REAL_HARNESS=1` (`tests/conftest.py`); a CI nunca liga a variável e o gate de 95% é medido sem eles (`--no-cov`).
- Orçamento até US$ 0,50 e timeout de 300 s por teste; Claude com `haiku` (`KNOBRIDGE_RUNNER_REAL_CLAUDE_MODEL`), Codex com o modelo do CLI ou `KNOBRIDGE_RUNNER_REAL_CODEX_MODEL`.
- Todo teste confere que o checkout ficou intacto (`git status --porcelain` e hash dos arquivos) e imprime custo, tokens e o caminho do log.
- No Windows o repositório sintético recebe leitura para `BUILTIN\Users` (o sandbox do Codex não lê pastas só do dono).

**Como testar**: de `runner/`, `KNOBRIDGE_RUNNER_REAL_HARNESS=1 uv run pytest -m real_harness --no-cov -s`.

**Leia também**: [harness.md, "Suíte opt-in real_harness"](../../../docs/specs/harness.md#suíte-opt-in-real_harness-d17); [runner/tests/AGENTS.md](../AGENTS.md).
