# Autenticação, papéis e permissões

> Rascunho v0.4 · 2026-10-14 · Em uso (planos 0002, 0008 e 0009; plano 0010 em implementação)
>
> **Mudanças da v0.4** (plano 0010, F1.1): na matriz, o servidor MCP (`/v1/mcp`, chave de API; [mcp.md](mcp.md)), a gestão dos widgets (admin) e as rotas públicas do widget (`/v1/widget/*`, sem sessão: `Origin` permitido e token de conversa do visitante; [widget.md](widget.md)); a tela **Widget**. Nenhuma das rotas novas lê o cookie de sessão nem exige CSRF.
>
> **Mudanças da v0.3** (plano 0009, F1.1; implementação na F2.1): **nível máximo por membro e produto**, com padrão pelo papel e valor gravado pelo admin ([produtos-e-niveis.md](produtos-e-niveis.md#nível-por-membro-e-produto)); convites com `product_levels` ([Convites](#convites)); `GET /v1/me` com o nível de cada produto ([Nível por produto no `/v1/me`](#nível-por-produto-no-v1me)); na matriz, as rotas de produtos no lugar das de assistentes, a configuração dos níveis, a tabela de níveis dos membros, o nível mínimo das fontes (admin) e "testar busca" para editor.
>
> **Mudanças da v0.2** (plano 0008, F1.1; implementação nas F2.1 a F2.5): a configuração inicial cria também o primeiro workspace, com o superadmin como owner ([Configuração inicial e superadmin](#configuração-inicial-e-superadmin)); o superadmin entra em qualquer workspace como admin efetivo, sem membership e auditado ([Acesso de superadmin a um workspace](#acesso-de-superadmin-a-um-workspace)); chaves de API para a API pública ([api-publica.md](api-publica.md)); rotas novas de uso e custos, painéis, ações e chaves na matriz.

Como o painel do KnoBridge autentica pessoas, protege requisições e decide quem pode fazer o quê. As decisões estão nos ADRs [0001](../adr/0001-tenancy-e-rls.md) (tenancy, RLS e modo de sistema), [0002](../adr/0002-sessao-server-side.md) (sessão server-side, tokens de uso único e CSRF) e [0003](../adr/0003-segredos-cifrados.md) (segredos); aqui fica o contrato resultante. Schemas das rotas no [`openapi.json`](openapi.json); tabelas em [modelo-de-dados.md](modelo-de-dados.md).

Código: `backend/src/knobridge/security/` (senhas, sessões, tokens, CSRF, limitação), `backend/src/knobridge/tenancy/` (setup, login, conta, convites, membros, superadmin, `rbac.py`), `backend/src/knobridge/api/deps.py` (dependências de autenticação e papel); no frontend, `frontend/src/lib/api/client.ts` (CSRF), `frontend/src/features/auth/` (guardas de rota) e `frontend/src/app/shell/navItems.ts` (papel mínimo por tela).

Só existe autenticação por e-mail e senha (D12 da [visão](../01-visao-do-projeto.md#9-decisões-chave-adr-lite)); `users.provider` já prevê OIDC.

## Identidades, workspaces e papéis

- **Usuário** é identidade da instância (tabela `users`, sem `workspace_id`) e participa de N workspaces por **membership**, cada uma com um papel.
- **Papéis de workspace**, em hierarquia: `owner` > `admin` > `editor` > `viewer` (na interface: proprietário, administrador, editor, leitor). Cada papel inclui as permissões dos de baixo; as checagens pedem um papel mínimo (`role_at_least` em `tenancy/rbac.py`).
- **Superadmin** é atributo do usuário (`users.is_superadmin`), não papel de workspace. Administra a instância (`/v1/admin/...`), mas **não** ganha acesso aos dados dos workspaces só por ser superadmin: sem membership, as rotas de workspace respondem 404 também para ele, até ele **entrar** no workspace pela administração ([Acesso de superadmin a um workspace](#acesso-de-superadmin-a-um-workspace)).
- **Suspensão**: usuário suspenso não loga e perde as sessões; workspace suspenso responde 403 `workspace_suspended` em toda rota de workspace para os membros, e os convites pendentes dele deixam de funcionar (`invalid_token`) enquanto durar a suspensão.

Regras que valem para membros e convites:

- Ninguém concede papel acima do próprio nem gerencia (muda papel, remove, revoga ou reenvia convite de) quem tem papel acima do próprio: 403 `role_not_allowed`, com `details.max_role`.
- Todo workspace mantém ao menos um owner: rebaixar ou remover o último dá 409 `last_owner`.
- **Lista de membros** (`GET .../members`, viewer): paginada como as demais, por nome por padrão; desde a v0.2 aceita `query` (nome ou e-mail, até 200 caracteres, sem diferenciar maiúsculas, com `%`, `_` e `\` escapados), `role` e `sort` (`name` (padrão), `-name`, `email`, `-email`, `role`, `-role` (pela hierarquia, owner primeiro), `joined_at`, `-joined_at`). Empate pelo `id`; valor fora da lista: 422 `validation_error`.
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
| Superadmin entra num workspace ou sai dele | `POST /v1/admin/workspaces/{id}/enter`, `DELETE /v1/admin/workspace-access` | Grava ou limpa o acesso de superadmin na sessão atual (só nela). |
| Sair | `POST /v1/auth/logout` | Revoga a sessão atual e apaga os cookies. |
| Sair de todos os dispositivos | `POST /v1/auth/logout-all` | Revoga todas as sessões do usuário, inclusive a atual. |
| Encerrar uma sessão | `DELETE /v1/me/sessions/{session_id}` | Revoga uma sessão do próprio usuário (encerrar a atual equivale a sair). |
| Trocar a senha | `POST /v1/me/password` | Exige a senha atual; revoga as outras sessões e mantém a atual. |
| Redefinir a senha por e-mail | `POST /v1/auth/password/reset` | Revoga todas as sessões da conta e apaga os cookies do navegador. |
| Superadmin suspende o usuário | `PATCH /v1/admin/users/{user_id}` | Revoga todas as sessões do usuário. |

`GET /v1/me` devolve o usuário (com `is_superadmin`, `email_verified_at`, idioma e tema), os workspaces dele com o papel em cada um e, desde a v0.2, o acesso de superadmin ativo na sessão (`superadmin_access`); o painel usa essa resposta para montar o menu. A dependência `current_user` responde 401 `unauthenticated` sem sessão viva ou com usuário suspenso.

### Nível por produto no `/v1/me`

Desde a v0.3 (plano 0009), cada item de `workspaces` em `GET /v1/me` (e nas respostas de login, setup, `enter` e `workspace-access`) traz `product_levels`: o nível máximo de quem está logado em cada produto **ativo** daquele workspace, por nome do produto:

```json
{"id": "…", "name": "Cliente Alfa", "role": "editor", "access": "member",
 "product_levels": [{"product_id": "…", "product_name": "ERP", "max_level": "support", "explicit": true}]}
```

- `max_level` segue a regra de [produtos-e-niveis.md](produtos-e-niveis.md#nível-por-membro-e-produto): o valor gravado pelo admin ou, sem ele, o padrão do papel (`product_dev` para owner e admin, inclusive o admin efetivo do superadmin; `end_user` para editor e leitor). `explicit` diz qual dos dois.
- A consulta lê produtos e níveis de vários workspaces, então roda em modo de sistema, **filtrada pelos ids dos workspaces da própria resposta** (as memberships do usuário e o workspace do acesso de superadmin), num número constante de statements. Há teste de que um workspace de que o usuário não participa nunca aparece.
- Workspace suspenso vem com `product_levels: []`.

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

- **Convidar** (`POST /v1/workspaces/{id}/invites`, admin+): e-mail e papel (até o papel de quem convida) e, desde a v0.3, `product_levels` opcional (`[{product_id, max_level}]`, até 200, produto do workspace, senão 422 `invite_product_invalid`): o nível máximo da pessoa em cada produto, gravado no aceite; sem ele, vale o padrão do papel ([produtos-e-niveis.md](produtos-e-niveis.md#convites-com-nível)). `GET .../invites` devolve `product_levels` de cada convite. Reconvidar o mesmo e-mail substitui o convite pendente; e-mail de quem já é membro dá 409 `already_member`.
- **Reenviar** troca o token (o anterior para de funcionar) e recomeça a validade; **revogar** invalida o link. Convite vencido continua listado (marcado como vencido) e pode ser reenviado.
- **Pré-visualizar** (`POST /v1/invites/preview`, público): workspace, papel, quem convidou, validade e se o e-mail já tem conta.
- **Aceitar** (`POST /v1/invites/accept`, público):
  - e-mail sem conta: exige `name` e `password` (422 `account_details_required` ou `weak_password`), cria a conta já verificada, a membership e uma sessão;
  - e-mail com conta: exige estar logado com essa conta (401 `login_required`; logado com outra, 403 `invitation_email_mismatch`) e cria a membership;
  - já membro: 409 `already_member`.
  O token é consumido na mesma transação que cria a membership e grava os níveis do convite (produtos excluídos nesse meio tempo são ignorados); qualquer recusa desfaz tudo e o link continua valendo.

## Limitação de login

`POST /v1/auth/login` é limitado por e-mail + IP do cliente (`security/throttle.py`, tabela `login_attempts`, que guarda só o SHA-256 de `lower(email)|ip`):

- Janela fixa contada da primeira falha (`KNOBRIDGE_LOGIN_ATTEMPT_WINDOW`, padrão 15 min). Atingidas `KNOBRIDGE_LOGIN_MAX_ATTEMPTS` falhas (padrão 5) na janela, o login responde 429 `too_many_attempts` com `details.retry_after_seconds` até a janela acabar, **mesmo com a senha certa**. Login bem-sucedido zera o contador.
- Senha errada, e-mail desconhecido e conta suspensa dão a mesma resposta, 401 `invalid_credentials`. E-mail desconhecido gasta o mesmo tempo de uma verificação real de senha. Conta suspensa com a senha certa não conta como falha.
- Toda tentativa é auditada na trilha da instância (`auth.login.succeeded` ou `auth.login.failed`, com o motivo).
- **IP atrás de proxy.** O IP é o do par TCP, a menos que o par seja um proxy confiável: a API roda com `proxy_headers` do uvicorn e aceita `X-Forwarded-For`/`X-Forwarded-Proto` só dos endereços em `KNOBRIDGE_FORWARDED_ALLOW_IPS` (padrão `127.0.0.1`; aceita lista de IPs ou CIDRs, ou `*`). No compose, só o nginx do painel, em endereço fixo (`FRONTEND_IPV4`), é confiável; requisições direto na porta da API contam o IP de quem conectou. Em produção atrás de outro proxy, configure essa variável, senão todos os clientes compartilham o contador do proxy. Detalhes em [subir-ambiente.md](../guias/subir-ambiente.md#configuração-da-api-e-do-worker).

## Configuração inicial e superadmin

- `GET /v1/setup/status` responde `{"needs_setup": true}` enquanto não existe nenhum usuário. O painel leva para `/setup` nesse caso e bloqueia `/setup` depois.
- `POST /v1/setup` recebe `name`, `email`, `password` e, desde a v0.2, **`workspace_name`** (obrigatório, 1 a 200 caracteres sem espaços nas pontas). Numa única transação, em modo de sistema, ele cria:
  1. o **primeiro superadmin**, já com e-mail verificado;
  2. o **primeiro workspace**, com esse nome e o slug gerado dele (a mesma `slugify` da criação pela administração; a instância está vazia, então não há colisão);
  3. a **membership `owner`** do superadmin nesse workspace, direto, sem convite e sem e-mail;
  4. a sessão, que já entra com ele.

  Qualquer falha desfaz tudo. Um advisory lock do Postgres serializa configurações simultâneas; a segunda recebe 409 `setup_already_completed`. Erros de corpo: 422 `validation_error` (inclusive sem `workspace_name`) ou `weak_password`. Auditoria: `setup.completed` e `user.created` na trilha da instância, e `workspace.created` (com `name`, `slug` e `owner_user_id`) nas trilhas da instância e do workspace.
- A resposta (201) é o `MeResponse`, já com o workspace (papel `owner`). O painel leva direto ao Início dele (`/w/:id`).
- Outros workspaces o superadmin cria em **Administração da instância > Workspaces**, informando um e-mail de proprietário, que recebe convite. Para administrar um workspace do qual não é membro, ele **entra** nele (seção seguinte). Passo a passo em [primeiro-acesso.md](../guias/primeiro-acesso.md).
- Rotas `/v1/admin/...`: `require_superadmin` (403 `forbidden` para os demais) e depois uma sessão em modo de sistema. Cada mudança é auditada na trilha da instância e, quando afeta um workspace, também na trilha dele.

## Acesso de superadmin a um workspace

O superadmin entra em qualquer workspace ativo pela administração, com **papel admin efetivo**, sem virar membro (D5 do [plano 0008](../planos/0008-telas-de-uso-e-administracao.md)).

**Marca na sessão.** O acesso é um estado da **sessão atual**, não do usuário: colunas `sessions.superadmin_workspace_id` (FK `workspaces.id`, `ON DELETE SET NULL`) e `sessions.superadmin_entered_at`. Uma sessão tem no máximo um acesso; as outras sessões do mesmo usuário (outro navegador) não o herdam.

**Rotas** (sessão, CSRF, superadmin; 403 `forbidden` para os demais):

| Rota | Efeito |
|---|---|
| `POST /v1/admin/workspaces/{workspace_id}/enter` | Grava o acesso na sessão atual e responde 200 `MeResponse`. Workspace inexistente: 404 `not_found`; suspenso: 403 `workspace_suspended` (reative antes). Se a sessão estava em outro workspace, troca, auditando a saída do anterior. Entrar de novo no mesmo workspace é idempotente, sem novo evento. |
| `DELETE /v1/admin/workspace-access` | Limpa o acesso da sessão e responde 200 `MeResponse`. Sem acesso ativo, responde igual, sem evento. |

**Papel efetivo.** Em `workspace_context` (`api/deps.py`), quando o usuário é superadmin **e** a sessão tem acesso àquele workspace, o papel é o maior entre o da membership (se houver) e `admin`. Sem a marca, vale só a membership, como antes. A checagem é por requisição: perder o superadmin (`PATCH /v1/admin/users/{id}`) torna o acesso inerte na hora, mesmo com a marca gravada. Workspace suspenso depois da entrada responde 403 `workspace_suspended`, como para os membros.

**O que o admin efetivo pode.** Exatamente o que um admin membro pode (matriz abaixo), com as mesmas regras: não concede `owner` nem gerencia owners (`role_not_allowed`), lê as conversas de todos na visão administrativa e conversa no chat em nome próprio. Ele **não** aparece na lista de membros, não conta como owner (`last_owner`) e não recebe e-mails do workspace.

**RLS.** Nada muda no banco: a transação continua com `SET LOCAL app.workspace_id` (o workspace do path) e `app.user_id` (o superadmin), como para um membro. As políticas filtram por `workspace_id`, então o escopo é o de qualquer membro, e `workspaces_select` aceita o workspace selecionado. As rotas de workspace não usam modo de sistema.

**`GET /v1/me`** (e as respostas de login, setup, `enter` e `workspace-access`):

- `superadmin_access`: `null` ou `{"workspace_id", "workspace_name", "entered_at"}`, só quando o usuário ainda é superadmin e o workspace existe;
- em `workspaces`, cada item ganha `access`: `member` (papel da membership) ou `superadmin` (papel efetivo `admin`, vindo do acesso). O workspace do acesso aparece na lista mesmo sem membership. Com membership abaixo de admin, o item mostra `role: admin` e `access: superadmin`.

O painel mostra uma faixa "Acesso de superadmin" no topo enquanto `superadmin_access` não é nulo, com o botão **Sair** (`DELETE /v1/admin/workspace-access`).

**Fim do acesso**: sair, entrar em outro workspace, encerrar a sessão (logout, expiração, revogação) ou excluir o workspace.

**Auditoria**: `superadmin.workspace_entered` e `superadmin.workspace_exited` (com `reason`: `exit` ou `switched`), cada um gravado **nas duas trilhas**: na da instância (`workspace_id` nulo, alvo `workspace`) e na do workspace, para owners e admins verem quem entrou. As ações feitas durante o acesso são auditadas normalmente, com o superadmin como ator. O fim por logout ou expiração não gera evento de saída.

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
| `POST /v1/admin/workspaces/{id}/enter`, `DELETE /v1/admin/workspace-access` | superadmin ([acesso a um workspace](#acesso-de-superadmin-a-um-workspace)) |
| `GET /v1/admin/dashboard`, `GET /v1/admin/health` | superadmin ([uso-e-custos.md](uso-e-custos.md#painel-da-instância-administração)) |
| `GET .../dashboard` | viewer (`cost_month` só para admin; [uso-e-custos.md](uso-e-custos.md#painel-do-workspace-início)) |
| `GET .../usage`, `GET .../usage.csv` | admin ([uso-e-custos.md](uso-e-custos.md#uso-e-custos-do-workspace)) |
| `GET .../members` | viewer |
| `GET .../products`, `GET .../products/{id}` | viewer (o leitor só vê produtos ativos; v0.3, no lugar de `.../assistants`, que saíram) |
| `POST .../conversations`, `GET .../conversations` | viewer (cada um lista só as próprias) |
| `GET .../conversations/{id}` | viewer, se dono da conversa; admin lê qualquer uma |
| `POST .../conversations/{id}/messages`, `DELETE .../conversations/{id}` | viewer, só o dono da conversa; perguntar exige o nível da conversa até o máximo do dono no produto ([produtos-e-niveis.md](produtos-e-niveis.md#chat-com-produto-e-nível)) |
| `POST .../conversations/{id}/messages/{message_id}/feedback` | quem pode ler a conversa |
| `POST`, `PATCH`, `DELETE .../products[/{id}]`, `POST .../products/{id}/duplicate`, `POST .../products/{id}/ticket-webhook/test` | editor ([produtos-e-niveis.md](produtos-e-niveis.md#rotas)) |
| `POST .../products/{id}/ticket-webhook/secret` | admin |
| `GET .../levels`, `PATCH .../levels/{level}` | admin ([configuração dos níveis](produtos-e-niveis.md#configuração-dos-níveis-no-workspace)) |
| `GET .../member-levels`, `PUT .../members/{user_id}/product-levels` | admin (respeitando `role_not_allowed`; [nível por membro](produtos-e-niveis.md#nível-por-membro-e-produto)) |
| `min_level` em `POST .../sources` (diferente do padrão) e em `PATCH .../sources/{id}` | admin; os demais campos da fonte continuam editor ([nível mínimo](produtos-e-niveis.md#quem-muda-e-o-que-acontece)) |
| `POST .../collections/{id}/search` (testar busca) | editor (v0.3; antes, qualquer membro) |
| `POST .../sources/{id}/reindex`, `POST .../collections/{id}/sync` | editor ([indexacao.md](indexacao.md#reindexar-uma-fonte)) |
| `GET`, `POST .../api-keys`, `PATCH .../api-keys/{id}`, `POST .../api-keys/{id}/revoke` | admin ([api-publica.md](api-publica.md#gestão-no-painel-owner-ou-admin)) |
| `GET /v1/models`, `POST /v1/chat/completions`, `POST /v1/conversations`, `GET /v1/conversations/{id}`, `POST /v1/conversations/{id}/messages` | chave de API (`Authorization: Bearer kbk_...`), sem sessão nem CSRF ([api-publica.md](api-publica.md#autenticação)) |
| `POST /v1/mcp` | chave de API, sem sessão nem CSRF; `Origin`, quando presente, só de `KNOBRIDGE_MCP_ALLOWED_ORIGINS` (v0.4; [mcp.md](mcp.md#autenticação)) |
| `GET`, `POST .../widgets`, `GET`, `PATCH`, `DELETE .../widgets/{id}`, `POST`, `DELETE .../widgets/{id}/signing-secret` | admin (v0.4; [widget.md](widget.md#rotas-owner-ou-admin)) |
| `GET /v1/widget/{public_key}/config`, `POST /v1/widget/{public_key}/conversations` | público, com `Origin` nos domínios do widget e limite de requisições; identidade assinada opcional (v0.4; [widget.md](widget.md#checagem-de-origin)) |
| `GET /v1/widget/{public_key}/conversations/{id}`, `POST .../messages`, `POST .../messages/{message_id}/feedback`, `POST`, `GET .../ticket-requests[/{id}]` | token de conversa do visitante (`Authorization: Bearer kbv_...`), com `Origin` permitido, sem sessão nem CSRF (v0.4; [widget.md](widget.md#token-de-conversa-kbv_)) |
| `GET`, `POST .../providers`, `PATCH`, `DELETE .../providers/{id}`, `POST .../providers/{id}/test` | editor |
| `GET .../runners`, `GET .../runners/{id}` | editor |
| `POST .../runners`, `PATCH`, `DELETE .../runners/{id}` | admin |
| `POST /v1/runner/*` | token de runner (`Authorization: Bearer kbr_...`), sem sessão nem CSRF ([runner.md](runner.md#token-de-runner)) |
| `PATCH /v1/workspaces/{id}` (renomear) | admin |
| `PATCH`, `DELETE .../members/{user_id}` | admin (respeitando `role_not_allowed` e `last_owner`) |
| `GET`, `POST .../invites`, `DELETE .../invites/{id}`, `POST .../invites/{id}/resend` | admin (convite até o próprio papel) |
| `GET .../audit` | admin |
| `GET .../admin/conversations`, `GET .../admin/conversations/stats`, `GET .../admin/conversations/{id}` | admin |

`...` = `/v1/workspaces/{workspace_id}`. Todas as rotas não seguras com sessão exigem também o header CSRF (exceções na seção [CSRF](#csrf)). O [acesso de superadmin](#acesso-de-superadmin-a-um-workspace) vale como membership com papel admin.

### Telas do painel

O papel mínimo de cada área do workspace vem de `WORKSPACE_AREAS` em `frontend/src/app/shell/navItems.ts`; o menu e a guarda de rota (`RequireWorkspaceRole`) leem a mesma tabela, então um item escondido também não abre pela URL. A guarda do frontend é conveniência: quem decide é a API.

| Tela (rota) | Papel mínimo | Observação |
|---|---|---|
| Início (`/w/:id`) | viewer | Cartões e checklist; o custo do mês só para admin+. |
| Chat (`/w/:id/chat`) | viewer | Seletor de produto e de nível, só até o máximo de quem pergunta. O atalho para gerenciar produtos só aparece para editor+. |
| Conversas (`/w/:id/conversations`) | admin | Visão administrativa. |
| Produtos (`/w/:id/products`) | editor | No lugar de Assistentes (v0.3). |
| Provedores (`/w/:id/providers`) | editor | |
| Fontes, Pipelines, Coleções, Canais | viewer | Telas de esqueleto, sem funcionalidade ainda. |
| Membros (`/w/:id/members`) | viewer | Leitor vê a lista; convidar, gerenciar e editar o nível por produto só para admin+. |
| Configurações (`/w/:id/settings`) | admin | Inclui **Níveis de resposta** (v0.3). |
| Uso e custos (`/w/:id/usage`) | admin | |
| Chaves de API (`/w/:id/api-keys`) | admin | Inclui a seção MCP, com os comandos dos clientes (v0.4). |
| Widget (`/w/:id/widgets`) | admin | Lista por produto, edição, segredo de assinatura, trecho para copiar e prévia ao vivo (v0.4). |
| Auditoria (`/w/:id/audit`) | admin | |
| Painel, Workspaces, Usuários, Auditoria da instância (`/admin/...`) | superadmin | Guarda `RequireSuperadmin`. "Entrar" em cada workspace da lista. |
| Perfil e Segurança (`/account/...`) | logado | |
| `/setup` | público | Só enquanto a instância não tem usuário. |
| `/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/accept-invitation` | público | Só depois da configuração inicial. |

## Auditoria

Login (sucesso e falha), logout, troca e redefinição de senha, verificação de e-mail, mudanças de perfil, revogação de sessões, convites, membros, níveis dos membros, provedores, produtos, configuração dos níveis, nível mínimo das fontes, chaves de API, widgets e o segredo de assinatura deles (v0.4), exclusão de conversa, entrada e saída de superadmin num workspace e todo o trabalho de superadmin gravam um evento em `audit_events` na mesma transação da mudança, sem segredos (catálogo em `backend/src/knobridge/audit/actions.py`). Owner e admin leem a trilha do workspace; o superadmin lê a da instância.

## Referências

- NIST SP 800-63B (política de senha): <https://pages.nist.gov/800-63-4/sp800-63b.html>
- OWASP, CSRF Prevention Cheat Sheet (double-submit assinado): <https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html>
- OWASP, Password Storage Cheat Sheet (argon2id): <https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html>
- Uvicorn, proxy headers: <https://www.uvicorn.org/settings/#http>
