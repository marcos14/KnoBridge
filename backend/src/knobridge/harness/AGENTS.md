# backend/src/knobridge/harness/

**Função**: o lado servidor do harness de código ([ADR 0005](../../../../docs/adr/0005-runner-local-do-harness.md)): runners, módulos das fontes do tipo `runner`, a fila de tarefas com reserva, os itens de conhecimento aceitos e as rejeições. O agente (Claude Code ou Codex) roda na máquina do usuário, no pacote `runner/`; aqui só se guarda e serve o que ele pede e devolve. Contratos em [runner.md](../../../../docs/specs/runner.md) e [harness.md](../../../../docs/specs/harness.md).

**Entra aqui**:
- `models.py`: `Runner` (`runners`: nome único no workspace, `token_prefix` único na instância, `token_hash` SHA-256 hex, `last_seen_at`, `version`, `capabilities`, `revoked_at`, `created_by`), `HarnessModule` (`harness_modules`: `key` única por fonte, título, `paths` de 1 a 50 padrões gitwildmatch, `suggested`, `enabled`, `last_commit`, `inventory`), `HarnessJob` (`harness_jobs`: módulo, runner da reserva, executor, modelo, gatilho, status, `attempts`, `not_before`, `lease_expires_at`, `commit_sha`, tokens, custo, duração, `metrics` com o resto das métricas, contagens de itens e `error`), `KnowledgeItem` (`knowledge_items`: `kind` `rule`/`module`, `key` `<módulo>.R001`/`.E001` única por fonte, `content`, `evidence`, `confidence` `inferido`/`revisado`, `review_status`, `edited`, `evidence_changed`, `commit_sha`, `generated_by`) e `HarnessRejection` (`harness_rejections`: bloco, `item_index`, rótulo, código, motivo, `sources`), com os enums `HarnessExecutor`, `HarnessJobTrigger`, `HarnessJobStatus`, `KnowledgeItemKind`, `KnowledgeConfidence`, `KnowledgeReviewStatus` e `RejectionBlock` e os padrões `COMMIT_PATTERN`, `MODULE_KEY_PATTERN` e `ITEM_KEY_PATTERN`.
- `tokens.py`: `generate_runner_token` (`kbr_<8 [a-z0-9]>_<token_urlsafe(32)>`, com prefixo e SHA-256 hex do token inteiro), `token_prefix` (prefixo de um token bem formado, senão `None`) e `token_matches` (comparação em tempo constante, inclusive quando o prefixo não existe).
- `runners.py`: `RunnerService` do painel (`list_runners`, `get`, `create` → `IssuedRunner(runner, token)`, `update` com nome e revogação irreversível, `delete` recusado com `runner_in_use`), auditado na transação; `is_online` (janela `ONLINE_WINDOW` de 90 s) e `uses_runner` (condição "fonte `runner` cujo `config.runner_id` é este runner").
- `presence.py`: `authenticate_runner` (em modo de sistema; 401 `invalid_runner_token` igual para token malformado, desconhecido, hash diferente ou revogado, com log `runner_auth_failed` só com motivo e prefixo; 403 `workspace_suspended`; `last_seen_at` no máximo uma escrita a cada 10 s), `record_heartbeat` e `runner_sources` (fontes ativas do workspace do runner ligadas a ele).
- A seguir (plano 0004): fila (reserva, heartbeat, resultado, falha, adiamento), módulos e o conector interno `knowledge`.

**Não entra aqui**: routers e schemas (`api/`), o modelo `Source` e a configuração por tipo (`ingestion/`), o runner e o que roda na máquina do usuário (`runner/`), migrações (`backend/migrations/`).

**Convenções locais**:
- Cinco tabelas com RLS forçada e a política padrão de workspace. A busca do runner pelo token roda em `system_session` (o workspace ainda não é conhecido) só por `token_prefix`; o resto da requisição roda no escopo do workspace do runner.
- Referências compostas `(workspace_id, <pai>_id)`. Módulos, tarefas e itens cascateiam da fonte; rejeições, da tarefa. `harness_jobs.runner_id` e `knowledge_items.job_id` usam `ON DELETE SET NULL (<coluna>)`, que anula só essa coluna da chave composta (`workspace_id` é NOT NULL).
- Fila no Postgres, não no Temporal (decisão D14): estados e transições só pelas funções da fila, nunca por `UPDATE` solto nas rotas.
- O token de runner nunca é gravado nem logado; só `token_prefix` e `runner_id`.
- Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/harness` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ingestion/AGENTS.md](../ingestion/AGENTS.md); [tests/harness/AGENTS.md](../../../tests/harness/AGENTS.md).
