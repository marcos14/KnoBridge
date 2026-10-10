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
| `workspace.created`, `workspace.updated`, `workspace.suspended`, `workspace.reactivated` | workspace (feitos pelo superadmin: também na instância) |
| `auth.login.succeeded`, `auth.login.failed`, `auth.logout.succeeded`, `auth.sessions.revoked` | instância |
| `auth.password.changed`, `auth.password_reset.requested`, `auth.password_reset.completed`, `auth.email.verified`, `auth.email_verification.requested` | instância |
| `membership.invited`, `membership.invitation.accepted`, `membership.invitation.resent`, `membership.invitation.revoked`, `membership.role.changed`, `membership.removed` | workspace |
| `provider.created`, `provider.updated`, `provider.deleted` (credenciais de provedor de LLM; nome, tipo e campos alterados, nunca a chave) | workspace |

**Convenções locais**:
- **Nunca grave segredo** (senha, token, cookie, chave, cabeçalho `Authorization`) nem dado pessoal além do necessário em `metadata`. Prefira ids a e-mails e nomes. Chaves que contêm `password`, `secret`, `token`, `cookie`, `authorization` ou `api_key` são recusadas por `record`.
- `record` roda na transação da mudança: se ela falha, o evento some junto. Nunca abra transação só para auditar algo que já foi commitado.
- Escopo exigido pela RLS: evento de workspace precisa do workspace selecionado (`scoped_session(workspace_id=...)`) ou modo de sistema; evento da instância (`workspace_id=None`) precisa de modo de sistema ou de escopo de usuário em que o ator é o próprio usuário.
- Leitura: eventos de workspace só no escopo daquele workspace; eventos da instância só em modo de sistema (superadmin). Sem política de UPDATE: ninguém altera um evento; DELETE só em modo de sistema (retenção).
- Data do evento vem do `Clock` injetado; IP gravado normalizado (inválido vira nulo).

**Como testar**: de `backend/`, `uv run pytest tests/audit` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md); [modelo de dados](../../../../docs/specs/modelo-de-dados.md); [tests/audit/AGENTS.md](../../../tests/audit/AGENTS.md).
