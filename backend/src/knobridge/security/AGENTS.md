# backend/src/knobridge/security/

**Função**: primitivas de autenticação reutilizáveis, sem rotas: hash e política de senha, tokens opacos, sessões server-side, proteção CSRF e limitação de tentativas de login. Decisões no [ADR 0002](../../../../docs/adr/0002-sessao-server-side.md).

**Entra aqui**:
- `passwords.py`: `PasswordHasher` (argon2id; `hash`, `verify`, `needs_rehash`, `verify_and_update` para rehash transparente, `verify_dummy` para igualar o tempo quando o e-mail não existe), `Argon2Params` e `validate_password` (12 a 1024 caracteres; `WeakPasswordError` 422).
- `tokens.py`: `generate_token` (32 bytes, base64url), `hash_token` (SHA-256 hex) e `UserTokenService` (`issue`, com `workspace_id` só em convites; `consume` atômico de uso único; `find_valid`, que só consulta, para pré-visualizações; `InvalidTokenError` 400 sem revelar o motivo).
- `models.py`: `Session` (tabela `sessions`; desde a `0017`, o acesso de superadmin da sessão em `superadmin_workspace_id`, `ON DELETE SET NULL`, e `superadmin_entered_at`, obrigatório com acesso), `UserToken` (tabela `user_tokens`, `TokenPurpose`) e `LoginAttempt` (tabela `login_attempts`, uma linha por chave de limitação). Só hashes são gravados.
- `throttle.py`: `throttle_key(email, ip, scope=None)` (SHA-256 de `lower(email)|ip`, prefixado pelo `scope` quando há; o login não usa escopo, `tenancy/account.py` usa `password_reset` e `email_verification` com `ip=None` para limitar e-mails por endereço) e `LoginThrottle(clock, max_attempts=, window=)` com `retry_after`, `register_failure` (upsert atômico; janela fixa contada da primeira falha) e `reset`. Roda em `system_session`.
- `sessions.py`: `SessionService` (`create`, `validate` com expiração deslizante, `revoke` com filtro opcional por `user_id`, `revoke_all` com `except_session_id`, `list_active` paginado com total; `InvalidSessionError` 401), `set_session_cookie` e os resumos `summarize_ip`/`summarize_user_agent`.
- `csrf.py`: double-submit assinado (`issue_csrf_token`, `set_csrf_cookie`, `check_csrf`) e a dependência FastAPI `require_csrf`, que lê `app.state.settings`.

**Não entra aqui**: rotas de login, logout e conta (vão para `api/`), o fluxo de login e as regras de usuário, workspace e membership (`tenancy/`), envio de e-mail, leitura de variável de ambiente (`core/settings.py`).

**Convenções locais**:
- Toda lógica de expiração recebe um `Clock` (`core/clock.py`); nunca `datetime.now()` aqui.
- Os serviços recebem a `AsyncSession` de quem chama. Busca por token (login, validar sessão, emitir ou consumir token de e-mail) roda em `system_session`; listar ou revogar as próprias sessões roda em `scoped_session(user_id=...)`. `sessions` e `user_tokens` têm RLS forçada por `user_id` (em `user_tokens`, também pelo `workspace_id` dos tokens de convite, para o workspace que convida emitir e revogar o link na sua transação; migração `0006`); `login_attempts` tem RLS forçada só para modo de sistema.
- Token em claro só existe no valor devolvido (`IssuedSession.token`, `IssuedToken.token`): nunca gravar, logar nem devolver em listagem.
- Erros de autenticação são vagos de propósito (não dizer se o token expirou, foi usado ou não existe).
- Mudou modelo: migração nova e `docs/specs/modelo-de-dados.md` na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/security` (unitários e integração com Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ADR 0002](../../../../docs/adr/0002-sessao-server-side.md); [ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md); [core/AGENTS.md](../core/AGENTS.md); [tests/security/AGENTS.md](../../../tests/security/AGENTS.md).
