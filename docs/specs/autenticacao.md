# Autenticação, papéis e permissões

> Rascunho v0.1 · 2026-10-10 · Em uso (plano 0002)

Como o painel do KnoBridge autentica pessoas, protege requisições e decide quem pode fazer o quê. As decisões estão nos ADRs [0001](../adr/0001-tenancy-e-rls.md) (tenancy, RLS e modo de sistema), [0002](../adr/0002-sessao-server-side.md) (sessão server-side, tokens de uso único e CSRF) e [0003](../adr/0003-segredos-cifrados.md) (segredos); aqui fica o contrato resultante. Schemas das rotas no [`openapi.json`](openapi.json); tabelas em [modelo-de-dados.md](modelo-de-dados.md).

Código: `backend/src/knobridge/security/` (senhas, sessões, tokens, CSRF, limitação), `backend/src/knobridge/tenancy/` (setup, login, conta, convites, membros, superadmin, `rbac.py`), `backend/src/knobridge/api/deps.py` (dependências de autenticação e papel); no frontend, `frontend/src/lib/api/client.ts` (CSRF), `frontend/src/features/auth/` (guardas de rota) e `frontend/src/app/shell/navItems.ts` (papel mínimo por tela).

Só existe autenticação por e-mail e senha (D12 da [visão](../01-visao-do-projeto.md#9-decisões-chave-adr-lite)); `users.provider` já prevê OIDC.

## Identidades, workspaces e papéis

- **Usuário** é identidade da instância (tabela `users`, sem `workspace_id`) e participa de N workspaces por **membership**, cada uma com um papel.
- **Papéis de workspace**, em hierarquia: `owner` > `admin` > `editor` > `viewer` (na interface: proprietário, administrador, editor, leitor). Cada papel inclui as permissões dos de baixo; as checagens pedem um papel mínimo (`role_at_least` em `tenancy/rbac.py`).
- **Superadmin** é atributo do usuário (`users.is_superadmin`), não papel de workspace. Administra a instância (`/v1/admin/...`), mas **não** ganha acesso aos dados dos workspaces: sem membership, as rotas de workspace respondem 404 também para ele.
- **Suspensão**: usuário suspenso não loga e perde as sessões; workspace suspenso responde 403 `workspace_suspended` em toda rota de workspace para os membros, e os convites pendentes dele deixam de funcionar (`invalid_token`) enquanto durar a suspensão.

Regras que valem para membros e convites:

- Ninguém concede papel acima do próprio nem gerencia (muda papel, remove, revoga ou reenvia convite de) quem tem papel acima do próprio: 403 `role_not_allowed`, com `details.max_role`.
- Todo workspace mantém ao menos um owner: rebaixar ou remover o último dá 409 `last_owner`.
- A instância mantém ao menos um superadmin ativo: rebaixar ou suspender o último dá 409 `last_superadmin`; ninguém suspende a si mesmo.

## Sessão

Sessão server-side ([ADR 0002](../adr/0002-sessao-server-side.md), itens 3 e 4):

| Item | Valor |
|---|---|
| Cookie de sessão | `knobridge_session` (`KNOBRIDGE_SESSION_COOKIE_NAME`), `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` conforme `KNOBRIDGE_COOKIE_SECURE` (padrão `true`; o compose de dev usa `false`). |
| Conteúdo | Token opaco de 32 bytes; no banco só o SHA-256 (`sessions.token_hash`). |
| Expiração | Deslizante: cada requisição autenticada empurra `expires_at` para agora + `KNOBRIDGE_SESSION_TTL` (padrão 7 dias). |
| Dados guardados | Prefixo de rede do IP (IPv4 /24, IPv6 /48) e user-agent truncado em 200 caracteres. |
| Senha | argon2id (t=3, m=64 MiB, p=4), de 12 a 1024 caracteres, sem regra de composição (`weak_password` fora disso). Rehash transparente no login quando os parâmetros mudam. |

Como cada evento afeta as sessões:

| Evento | Rota | Efeito |
|---|---|---|
| Configuração inicial, login, aceite de convite criando conta | `POST /v1/setup`, `POST /v1/auth/login`, `POST /v1/invites/accept` | Cria sessão e entrega os cookies de sessão e de CSRF. |
| Sair | `POST /v1/auth/logout` | Revoga a sessão atual e apaga os cookies. |
| Sair de todos os dispositivos | `POST /v1/auth/logout-all` | Revoga todas as sessões do usuário, inclusive a atual. |
| Encerrar uma sessão | `DELETE /v1/me/sessions/{session_id}` | Revoga uma sessão do próprio usuário (encerrar a atual equivale a sair). |
| Trocar a senha | `POST /v1/me/password` | Exige a senha atual; revoga as outras sessões e mantém a atual. |
| Redefinir a senha por e-mail | `POST /v1/auth/password/reset` | Revoga todas as sessões da conta e apaga os cookies do navegador. |
| Superadmin suspende o usuário | `PATCH /v1/admin/users/{user_id}` | Revoga todas as sessões do usuário. |

`GET /v1/me` devolve o usuário (com `is_superadmin`, `email_verified_at`, idioma e tema) e os workspaces dele com o papel em cada um; o painel usa essa resposta para montar o menu. A dependência `current_user` responde 401 `unauthenticated` sem sessão viva ou com usuário suspenso.

## CSRF

Double-submit assinado ([ADR 0002](../adr/0002-sessao-server-side.md), item 6; `security/csrf.py`):

1. A API grava o cookie legível `knobridge_csrf` (sem `HttpOnly`, `SameSite=Lax`, mesma validade da sessão) com `<nonce>.<HMAC-SHA256(KNOBRIDGE_SECRET_KEY, nonce)>`. Ele é emitido junto com a sessão (setup, login, aceite com conta nova) e renovado por `GET /v1/auth/csrf`, que também devolve o valor no corpo.
2. O frontend copia o cookie para o header `X-CSRF-Token` em toda requisição não segura (`authMiddleware` em `frontend/src/lib/api/client.ts`).
3. A dependência `require_csrf` recusa com 403 `csrf_failed` métodos não seguros sem cookie, sem header, com valores diferentes ou com assinatura inválida. `GET`, `HEAD`, `OPTIONS` e `TRACE` passam.

Exceções, porque não usam o cookie de sessão: `POST /v1/setup`, `POST /v1/auth/login`, `POST /v1/auth/password/forgot`, `POST /v1/auth/password/reset`, `POST /v1/auth/email/verify` e `POST /v1/invites/preview` não exigem o header. `POST /v1/invites/accept` exige o header só quando há sessão (quem já está logado aceitando com a própria conta).

## Tokens de uso único por e-mail

Tokens opacos de 32 bytes (43 caracteres base64url), guardados só como SHA-256 em `user_tokens`, com finalidade, validade e uso único (o consumo é um único `UPDATE ... WHERE used_at IS NULL AND expires_at > agora`). Token inválido, vencido, usado, de outra finalidade ou de convite em workspace suspenso dá sempre 400 `invalid_token`, sem dizer o motivo.

| Finalidade | Validade (variável) | Emitido por | Consumido por |
|---|---|---|---|
| `password_reset` | 1 h (`KNOBRIDGE_PASSWORD_RESET_TTL`) | `POST /v1/auth/password/forgot` | `POST /v1/auth/password/reset` |
| `email_verification` | 24 h (`KNOBRIDGE_EMAIL_VERIFICATION_TTL`) | `POST /v1/auth/email/resend` (logado) | `POST /v1/auth/email/verify` (não exige login) |
| `invitation` | 7 dias (`KNOBRIDGE_INVITATION_TTL`) | Convite, reenvio, criação de workspace pelo superadmin | `POST /v1/invites/accept` |

- **Token no corpo, nunca na rota da API.** O e-mail traz um link do painel com `?token=` (`/reset-password`, `/verify-email`, `/accept-invitation`, a partir de `KNOBRIDGE_PUBLIC_BASE_URL`); a tela lê o token e o envia no corpo JSON de um `POST`. Até a pré-visualização de convite é `POST` (`/v1/invites/preview`, que não gasta o token), para o token não ficar em logs de acesso da API.
- **E-mails fora da requisição.** O envio acontece depois do commit, em tarefa de fundo; falha de SMTP só aparece no log (`email_delivery_failed`), nunca na resposta.
- **"Esqueci a senha" não revela contas.** Responde 204 sempre; só envia se o e-mail tem conta ativa.
- **Limite por endereço.** Até 3 pedidos de cada tipo (redefinição, verificação) por endereço a cada 1 h (`KNOBRIDGE_ACCOUNT_EMAIL_MAX_REQUESTS`, `KNOBRIDGE_ACCOUNT_EMAIL_WINDOW`), contados em `login_attempts` com chave sem IP. Acima disso, o "esqueci a senha" responde igual sem enviar e o reenvio de verificação dá 429 `too_many_attempts`.
- **Verificação de e-mail** é informativa: hoje nenhuma rota exige e-mail verificado. O superadmin da configuração inicial e quem cria conta por convite já nascem verificados; redefinir a senha também marca o e-mail como verificado (o link prova a posse da caixa).

### Convites

Convites são dado de workspace (`invitations`), e o link de cada um é um token `invitation` com o `workspace_id` do convite ([emenda do ADR 0001](../adr/0001-tenancy-e-rls.md#emenda-2026-10-10-tokens-de-convite-com-workspace_id)): convidar, reenviar e revogar acontecem numa só transação do workspace, junto com a auditoria.

- **Convidar** (`POST /v1/workspaces/{id}/invites`, admin+): e-mail e papel (até o papel de quem convida). Reconvidar o mesmo e-mail substitui o convite pendente; e-mail de quem já é membro dá 409 `already_member`.
- **Reenviar** troca o token (o anterior para de funcionar) e recomeça a validade; **revogar** invalida o link. Convite vencido continua listado (marcado como vencido) e pode ser reenviado.
- **Pré-visualizar** (`POST /v1/invites/preview`, público): workspace, papel, quem convidou, validade e se o e-mail já tem conta.
- **Aceitar** (`POST /v1/invites/accept`, público):
  - e-mail sem conta: exige `name` e `password` (422 `account_details_required` ou `weak_password`), cria a conta já verificada, a membership e uma sessão;
  - e-mail com conta: exige estar logado com essa conta (401 `login_required`; logado com outra, 403 `invitation_email_mismatch`) e cria a membership;
  - já membro: 409 `already_member`.
  O token é consumido na mesma transação que cria a membership; qualquer recusa desfaz tudo e o link continua valendo.

## Limitação de login

`POST /v1/auth/login` é limitado por e-mail + IP do cliente (`security/throttle.py`, tabela `login_attempts`, que guarda só o SHA-256 de `lower(email)|ip`):

- Janela fixa contada da primeira falha (`KNOBRIDGE_LOGIN_ATTEMPT_WINDOW`, padrão 15 min). Atingidas `KNOBRIDGE_LOGIN_MAX_ATTEMPTS` falhas (padrão 5) na janela, o login responde 429 `too_many_attempts` com `details.retry_after_seconds` até a janela acabar, **mesmo com a senha certa**. Login bem-sucedido zera o contador.
- Senha errada, e-mail desconhecido e conta suspensa dão a mesma resposta, 401 `invalid_credentials`. E-mail desconhecido gasta o mesmo tempo de uma verificação real de senha. Conta suspensa com a senha certa não conta como falha.
- Toda tentativa é auditada na trilha da instância (`auth.login.succeeded` ou `auth.login.failed`, com o motivo).
- **IP atrás de proxy.** O IP é o do par TCP, a menos que o par seja um proxy confiável: a API roda com `proxy_headers` do uvicorn e aceita `X-Forwarded-For`/`X-Forwarded-Proto` só dos endereços em `KNOBRIDGE_FORWARDED_ALLOW_IPS` (padrão `127.0.0.1`; aceita lista de IPs ou CIDRs, ou `*`). No compose, só o nginx do painel, em endereço fixo (`FRONTEND_IPV4`), é confiável; requisições direto na porta da API contam o IP de quem conectou. Em produção atrás de outro proxy, configure essa variável, senão todos os clientes compartilham o contador do proxy. Detalhes em [subir-ambiente.md](../guias/subir-ambiente.md#configuração-da-api-e-do-worker).

## Configuração inicial e superadmin

- `GET /v1/setup/status` responde `{"needs_setup": true}` enquanto não existe nenhum usuário. O painel leva para `/setup` nesse caso e bloqueia `/setup` depois.
- `POST /v1/setup` (nome, e-mail, senha) cria o **primeiro superadmin**, já com e-mail verificado, e entra com ele. Um advisory lock do Postgres serializa configurações simultâneas; a segunda recebe 409 `setup_already_completed`. Roda em modo de sistema e audita `setup.completed` e `user.created`.
- O superadmin não é membro de nenhum workspace. Para usar um, ele cria o workspace em **Administração da instância > Workspaces** informando um e-mail de proprietário (pode ser o próprio) e aceita o convite recebido. Passo a passo em [primeiro-acesso.md](../guias/primeiro-acesso.md).
- Rotas `/v1/admin/...`: `require_superadmin` (403 `forbidden` para os demais) e depois uma sessão em modo de sistema. Cada mudança é auditada na trilha da instância e, quando afeta um workspace, também na trilha dele.

## Matriz de permissões

Legenda: "público" = sem sessão; "logado" = qualquer sessão viva; nos papéis, o mínimo exigido (os de cima também podem). Toda rota de workspace exige antes a membership no workspace do path (sem ela, 404) e workspace ativo (senão, 403 `workspace_suspended`); papel insuficiente dá 403 `forbidden` com `details.required_role`.

### API

| Rota | Quem |
|---|---|
| `GET /v1/health/live`, `GET /v1/health/ready` | público |
| `GET /v1/setup/status`, `POST /v1/setup` | público (setup só com a instância vazia) |
| `GET /v1/auth/csrf`, `POST /v1/auth/login` | público |
| `POST /v1/auth/password/forgot`, `POST /v1/auth/password/reset`, `POST /v1/auth/email/verify` | público (com token, quando aplicável) |
| `POST /v1/invites/preview`, `POST /v1/invites/accept` | público (com token; sessão opcional no aceite) |
| `POST /v1/auth/logout`, `POST /v1/auth/logout-all`, `POST /v1/auth/email/resend` | logado |
| `GET /v1/me`, `PATCH /v1/me`, `POST /v1/me/password`, `GET /v1/me/sessions`, `DELETE /v1/me/sessions/{id}` | logado (só a própria conta) |
| `GET /v1/admin/workspaces`, `POST /v1/admin/workspaces`, `PATCH /v1/admin/workspaces/{id}` | superadmin |
| `GET /v1/admin/users`, `PATCH /v1/admin/users/{id}`, `GET /v1/admin/audit` | superadmin |
| `GET .../members` | viewer |
| `GET .../assistants`, `GET .../assistants/{id}` | viewer (o leitor só vê assistentes ativos) |
| `POST .../conversations`, `GET .../conversations` | viewer (cada um lista só as próprias) |
| `GET .../conversations/{id}` | viewer, se dono da conversa; admin lê qualquer uma |
| `POST .../conversations/{id}/messages`, `DELETE .../conversations/{id}` | viewer, só o dono da conversa |
| `POST .../conversations/{id}/messages/{message_id}/feedback` | quem pode ler a conversa |
| `POST`, `PATCH`, `DELETE .../assistants[/{id}]` | editor |
| `GET`, `POST .../providers`, `PATCH`, `DELETE .../providers/{id}`, `POST .../providers/{id}/test` | editor |
| `GET .../runners`, `GET .../runners/{id}` | editor |
| `POST .../runners`, `PATCH`, `DELETE .../runners/{id}` | admin |
| `POST /v1/runner/*` | token de runner (`Authorization: Bearer kbr_...`), sem sessão nem CSRF ([runner.md](runner.md#token-de-runner)) |
| `PATCH /v1/workspaces/{id}` (renomear) | admin |
| `PATCH`, `DELETE .../members/{user_id}` | admin (respeitando `role_not_allowed` e `last_owner`) |
| `GET`, `POST .../invites`, `DELETE .../invites/{id}`, `POST .../invites/{id}/resend` | admin (convite até o próprio papel) |
| `GET .../audit` | admin |
| `GET .../admin/conversations`, `GET .../admin/conversations/stats`, `GET .../admin/conversations/{id}` | admin |

`...` = `/v1/workspaces/{workspace_id}`. Todas as rotas não seguras com sessão exigem também o header CSRF (exceções na seção [CSRF](#csrf)).

### Telas do painel

O papel mínimo de cada área do workspace vem de `WORKSPACE_AREAS` em `frontend/src/app/shell/navItems.ts`; o menu e a guarda de rota (`RequireWorkspaceRole`) leem a mesma tabela, então um item escondido também não abre pela URL. A guarda do frontend é conveniência: quem decide é a API.

| Tela (rota) | Papel mínimo | Observação |
|---|---|---|
| Início (`/w/:id`) | viewer | |
| Chat (`/w/:id/chat`) | viewer | O atalho para gerenciar assistentes só aparece para editor+. |
| Conversas (`/w/:id/conversations`) | admin | Visão administrativa. |
| Assistentes (`/w/:id/assistants`) | editor | |
| Provedores (`/w/:id/providers`) | editor | |
| Fontes, Pipelines, Coleções, Canais | viewer | Telas de esqueleto, sem funcionalidade ainda. |
| Membros (`/w/:id/members`) | viewer | Leitor vê a lista; convidar e gerenciar só para admin+. |
| Configurações (`/w/:id/settings`) | admin | |
| Auditoria (`/w/:id/audit`) | admin | |
| Workspaces, Usuários, Auditoria da instância (`/admin/...`) | superadmin | Guarda `RequireSuperadmin`. |
| Perfil e Segurança (`/account/...`) | logado | |
| `/setup` | público | Só enquanto a instância não tem usuário. |
| `/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/accept-invitation` | público | Só depois da configuração inicial. |

## Auditoria

Login (sucesso e falha), logout, troca e redefinição de senha, verificação de e-mail, mudanças de perfil, revogação de sessões, convites, membros, provedores, assistentes, exclusão de conversa e todo o trabalho de superadmin gravam um evento em `audit_events` na mesma transação da mudança, sem segredos (catálogo em `backend/src/knobridge/audit/actions.py`). Owner e admin leem a trilha do workspace; o superadmin lê a da instância.

## Referências

- NIST SP 800-63B (política de senha): <https://pages.nist.gov/800-63-4/sp800-63b.html>
- OWASP, CSRF Prevention Cheat Sheet (double-submit assinado): <https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html>
- OWASP, Password Storage Cheat Sheet (argon2id): <https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html>
- Uvicorn, proxy headers: <https://www.uvicorn.org/settings/#http>
