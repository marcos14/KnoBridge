# runner/tests/fakes/

**Função**: os `claude` e `codex` falsos que a suíte padrão (e a CI) usa no lugar dos CLIs reais: emitem o JSONL dos executores reais por cenário, sem modelo nem rede. O mesmo par vai para o E2E da stack (plano 0004, F5.1), no PATH do runner. Contrato em [harness.md](../../../docs/specs/harness.md#executáveis-falsos-suíte-padrão-e-ci).

**Entra aqui**:
- `claude` e `codex`: scripts Python sem extensão, com shebang e bit de execução (Linux os acha no PATH; nos testes rodam como `[python, script]`). Só chamam `fake_harness.main`.
- `fake_harness.py`: a lógica. Cenário por `FAKE_HARNESS_SCENARIO` (`success`, `success_stdout_only`, `no_json_then_rescue`, `no_json`, `no_json_no_session`, `invalid_json`, `auth`, `quota`, `hang`, `unsafe_tool`, `budget`, `crash`); grava argumentos, prompt, schema, cwd e variáveis vazadas em `FAKE_HARNESS_ARGV_FILE`; saída de sucesso de `FAKE_HARNESS_OUTPUT` (padrão: saída mínima válida).

**Não entra aqui**: testes (vão para `runner/tests/test_harness_*.py`), saídas ou logs de CLIs reais, código ou chamados reais.

**Convenções locais**:
- Saída só em ASCII (`json.dumps` padrão) e prompt lido em bytes UTF-8: o code page do console do filho não pode mudar nada.
- Cenário novo: acrescente em `SCENARIOS`, na spec (lista dos falsos) e num teste.
- `hang` deixa um neto segurando o stdout: é o que prova o kill da árvore inteira.

**Como testar**: de `runner/`, `uv run pytest tests/test_harness_executors.py tests/test_harness_process.py` (fazem parte do gate de 95%).

**Leia também**: [runner/tests/AGENTS.md](../AGENTS.md); [docs/specs/harness.md](../../../docs/specs/harness.md).
