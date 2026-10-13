# backend/src/knobridge/audit/

**Função**: trilha de auditoria do KnoBridge. Todo evento relevante (login, mudança de workspace, membership, convite, setup) vira uma linha imutável em `audit_events`, gravada na mesma transação da mudança. Sem rotas: a consulta HTTP entra em `api/` (F2.1 do plano 0002).

**Entra aqui**:
- `actions.py`: `AuditAction`, o catálogo de ações (abaixo).
- `models.py`: `AuditEvent` (tabela `audit_events`) e o tipo `JSONValue`.
- `service.py`: `AuditService(clock).record(db, action=, workspace_id=, actor_user_id=, target=AuditTarget(type, id), metadata=, ip=)`, que só faz `add` + `flush` na sessão de quem chama (sem commit); `normalize_ip`; `UnsafeAuditMetadataError` (422).
- `queries.py`: `list_audit_events(db, workspace_id=, filters=AuditFilter(action, actor_user_id, occurred_from, occurred_to), limit=, offset=)` → `AuditPage(items, total, limit, offset)`, mais recente primeiro; `limit` de 1 a `MAX_LIMIT` (200).

**Não entra aqui**: rotas e schemas (`api/`), logs de aplicação (`core/logging.py`), regras de negócio de quem gera o evento.

**Catálogo de ações** (formato `<área>.<objeto>[.<detalhe>].<verbo no particípio>`; valor estável, nunca renomeado nem reaproveitado; ação nova entra no `AuditAction` e nesta lista na mesma entrega):

| Ação | Escopo |
|---|---|
| `setup.completed`, `user.created`, `user.suspended`, `user.reactivated`, `user.superadmin.granted`, `user.superadmin.revoked`, `user.profile.updated` | instância |
| `workspace.created`, `workspace.updated`, `workspace.suspended`, `workspace.reactivated` | workspace (feitos pelo superadmin, e o primeiro workspace do setup: também na instância) |
| `superadmin.workspace_entered`, `superadmin.workspace_exited` (acesso de superadmin a um workspace; na saída, `reason` `exit` ou `switched`; alvo `workspace`) | instância e workspace (sempre nas duas trilhas) |
| `auth.login.succeeded`, `auth.login.failed`, `auth.logout.succeeded`, `auth.sessions.revoked` | instância |
| `auth.password.changed`, `auth.password_reset.requested`, `auth.password_reset.completed`, `auth.email.verified`, `auth.email_verification.requested` | instância |
| `membership.invited` (`role` e `product_levels`), `membership.invitation.accepted`, `membership.invitation.resent`, `membership.invitation.revoked`, `membership.role.changed`, `membership.removed` | workspace |
| `provider.created`, `provider.updated`, `provider.deleted`, `provider.tested` (credenciais de provedor de LLM; nome, tipo, campos alterados e, no teste de conexão, `ok` e `error_code`; nunca a chave) | workspace |
| `assistant.created`, `assistant.updated`, `assistant.deleted` (aposentadas no plano 0009, ficam na trilha como gravadas: nome; na criação, `model` e `provider_id`; na alteração, `fields`; nunca prompt nem mensagens) | workspace |
| `product.created` (`name`, `collection_ids`, `duplicated_from` ao duplicar), `product.updated` (`name`, `fields`), `product.deleted` (`name`, `conversation_count`); nunca o texto das instruções nem a URL do webhook. `product.ticket_webhook_secret_rotated` e `product.ticket_webhook_tested` estão no catálogo, mas o segredo e o teste ainda gravam as `assistant.*` abaixo até `tickets/webhook.py` mudar | workspace |
| `workspace_level.updated` (configuração de um nível: `level`, `fields` e, quando mudaram, `provider_id` e `model`; nunca o texto das instruções; alvo `workspace_level` com o nome do nível), `member_level.updated` (nível máximo de um membro: `user_id` e `changes` `[{product_id, from, to}]`, `null` = padrão do papel; alvo `membership`) | workspace |
| `assistant.ticket_webhook_secret_rotated` (segredo `kbw_` do webhook de chamados gerado ou trocado: só `name`; nunca o segredo), `assistant.ticket_webhook_tested` (evento de teste do webhook: `name`, `ok`, `status` e `error_code`; nunca a URL nem o segredo) | workspace |
| `ticket_request.created` (pedido de chamado feito no chat: `conversation_id`, `message_id` e `assistant_id`; nunca a pergunta, o resumo nem os dados de quem pediu) | workspace |
| `collection.created`, `collection.updated`, `collection.deleted` (nome; na criação, `embedding_model` e `provider_id`; na alteração, `fields`) | workspace |
| `source.created`, `source.updated`, `source.deleted`, `source.tested`, `source.sync.started`, `source.sync.cancelled`, `source.reindex.started` (nome, `kind`, `collection_id`, `fields`, `ok`/`error_code` do teste, `run_id`/`trigger` da sincronização, nome e `run_id` da reindexação (que também grava o `source.sync.started`), `documents` e `cancelled_run_id` na exclusão; nunca a `config`, com caminhos e URLs, nem conteúdo de documento; documento indexado não é auditado) | workspace |
| `source.ingest_token_rotated` (token de envio `kbi_` de fonte `tickets` emitido ou girado: `name` e `prefix`, o prefixo público; nunca o token nem o hash) | workspace |
| `source.tickets_uploaded` (arquivo de chamados enviado no painel: `name` da fonte, `filename`, `format`, `total` e `counts` por status; nunca o conteúdo) | workspace |
| `runner.created`, `runner.updated`, `runner.revoked`, `runner.deleted` (runners do harness: `name`, `prefix` (o prefixo público do token; a chave não pode conter `token`) e, na alteração, `fields`; nunca o token nem o hash) | workspace |
| `api_key.created`, `api_key.updated`, `api_key.revoked` (chaves da API pública: `name`, `key_prefix` (o prefixo público; a chave não pode conter `api_key`), `assistant_ids` na criação, `fields` na alteração; a revogação só na primeira vez; nunca a chave nem o hash; o uso da chave não é auditado) | workspace |
| `harness_job.cancelled` (tarefa do harness cancelada no painel: `module_key` e `source_id`; nunca conteúdo de conhecimento), `harness_job.enqueued` (um evento por lote do painel: `source_id`, `module_keys`, `executor`, `trigger`; o enfileiramento por commit do runner não é auditado) | workspace |
| `harness_module.created`, `harness_module.updated` (módulos de fonte `runner` no painel: `key`, `source_id` e, na alteração, `fields`) | workspace |

**Convenções locais**:
- **Nunca grave segredo** (senha, token, cookie, chave, cabeçalho `Authorization`) nem dado pessoal além do necessário em `metadata`. Prefira ids a e-mails e nomes. Chaves que contêm `password`, `secret`, `token`, `cookie`, `authorization` ou `api_key` são recusadas por `record`.
- `record` roda na transação da mudança: se ela falha, o evento some junto. Nunca abra transação só para auditar algo que já foi commitado.
- Escopo exigido pela RLS: evento de workspace precisa do workspace selecionado (`scoped_session(workspace_id=...)`) ou modo de sistema; evento da instância (`workspace_id=None`) precisa de modo de sistema ou de escopo de usuário em que o ator é o próprio usuário.
- Leitura: eventos de workspace só no escopo daquele workspace; eventos da instância só em modo de sistema (superadmin). Sem política de UPDATE: ninguém altera um evento; DELETE só em modo de sistema (retenção).
- Data do evento vem do `Clock` injetado; IP gravado normalizado (inválido vira nulo).

**Como testar**: de `backend/`, `uv run pytest tests/audit` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md); [modelo de dados](../../../../docs/specs/modelo-de-dados.md); [tests/audit/AGENTS.md](../../../tests/audit/AGENTS.md).
