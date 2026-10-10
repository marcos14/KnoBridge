# Modelo de dados

> Rascunho v0.1 · 2026-10-10 · Em construção (plano 0002)

Tabelas do Postgres do KnoBridge, criadas pelas migrações em [`backend/migrations/`](../../backend/migrations/). Modelos ORM em `backend/src/knobridge/<módulo>/models.py`. Regras de tenancy e RLS no [ADR 0001](../adr/0001-tenancy-e-rls.md).

## Convenções

- Chave primária `id` UUID (gerada na aplicação ou por `gen_random_uuid()`).
- `created_at` e `updated_at` `timestamptz`, preenchidos pelo relógio do banco.
- Enums gravados como `varchar(32)` + `CHECK` (`ck_<tabela>_<coluna>`), com o valor em minúsculas.
- Nomes de restrição: `pk_<tabela>`, `uq_<tabela>_<colunas>`, `fk_<tabela>_<coluna>_<tabela_ref>`, `ix_<tabela>_<colunas>`.
- Tabela com dado de workspace: `workspace_id NOT NULL` e RLS `ENABLE` + `FORCE`.

## Escopo de RLS

| Configuração (por transação) | Quem define | Efeito |
|---|---|---|
| `app.workspace_id` | `scoped_session(workspace_id=...)` | Seleciona o workspace; já autorizado pela membership. |
| `app.user_id` | `scoped_session(user_id=...)` | Usuário autenticado; libera as próprias memberships e os workspaces dele. |
| `app.system` = `on` | `system_session()` | Modo de sistema: setup, superadmin, login. |

Sem nenhuma delas, as tabelas com RLS não retornam linhas. Exceção de modelo: `audit_events` aceita `workspace_id` nulo para eventos da instância, visíveis só em modo de sistema.

## Diagrama

```mermaid
erDiagram
    users ||--o{ memberships : "participa"
    workspaces ||--o{ memberships : "tem"
    users ||--o{ sessions : "abre"
    users |o--o{ user_tokens : "recebe"
    workspaces |o--o{ user_tokens : "emite convite"
    workspaces ||--o{ invitations : "convida"
    user_tokens ||--o| invitations : "link atual"
    users |o--o{ invitations : "convidou"
    workspaces |o--o{ audit_events : "registra"
    users |o--o{ audit_events : "age"
    workspaces ||--o{ provider_credentials : "guarda"
    provider_credentials {
        uuid id PK
        uuid workspace_id FK
        varchar name "único por workspace"
        varchar kind "openai | anthropic | openrouter | fake"
        varchar base_url "opcional"
        text key_ciphertext "AES-GCM; v1.base64url"
        varchar key_last4 "exibição ****1234"
    }
    login_attempts {
        uuid id PK
        varchar key_hash "único; SHA-256 de e-mail + IP"
        integer failures
        timestamptz window_started_at
    }
    users {
        uuid id PK
        varchar email "único sem diferenciar maiúsculas"
        varchar name
        varchar password_hash "nulo para provedores futuros"
        varchar provider "password"
        boolean is_superadmin
        varchar status "active | suspended"
        timestamptz email_verified_at
        varchar locale "pt-BR"
        varchar theme "system | light | dark"
    }
    workspaces {
        uuid id PK
        varchar name
        varchar slug "único"
        varchar status "active | suspended"
    }
    memberships {
        uuid id PK
        uuid workspace_id FK
        uuid user_id FK
        varchar role "owner | admin | editor | viewer"
    }
    sessions {
        uuid id PK
        uuid user_id FK
        varchar token_hash "único; SHA-256"
        timestamptz last_seen_at
        timestamptz expires_at
        varchar ip_prefix
        varchar user_agent
        timestamptz revoked_at
    }
    user_tokens {
        uuid id PK
        uuid user_id FK "nulo só em convites"
        uuid workspace_id FK "só em convites"
        varchar purpose "password_reset | email_verification | invitation"
        varchar token_hash "único; SHA-256"
        timestamptz expires_at
        timestamptz used_at
    }
    invitations {
        uuid id PK
        uuid workspace_id FK
        varchar email "minúsculas"
        varchar role "owner | admin | editor | viewer"
        uuid invited_by_user_id FK "nulo se o autor foi excluído"
        uuid token_id FK "único; link atual"
        timestamptz expires_at
        timestamptz accepted_at
        timestamptz revoked_at
    }
    audit_events {
        uuid id PK
        uuid workspace_id FK "nulo para eventos da instância"
        uuid actor_user_id FK "nulo para sistema ou anônimo"
        varchar action "catálogo estável, ex.: auth.login.succeeded"
        varchar target_type
        varchar target_id
        jsonb details "sem segredos"
        varchar ip_address
        timestamptz occurred_at
    }
```

## Tabelas

### `users`

Identidade da instância. Sem `workspace_id` e sem RLS.

| Coluna | Tipo | Regras |
|---|---|---|
| `email` | `varchar(320)` | Obrigatório; único por `lower(email)` (`uq_users_email_lower`). |
| `name` | `varchar(200)` | Obrigatório. |
| `password_hash` | `varchar(255)` | Opcional (identidades OIDC futuras não têm senha). |
| `provider` | `varchar(32)` | `password` (padrão). |
| `is_superadmin` | `boolean` | Padrão `false`. |
| `status` | `varchar(32)` | `active` (padrão) ou `suspended`. |
| `email_verified_at` | `timestamptz` | Nulo até a verificação. |
| `locale` | `varchar(16)` | Padrão `pt-BR`. |
| `theme` | `varchar(32)` | `system` (padrão), `light` ou `dark`. |

### `workspaces`

Tenant. RLS forçada.

| Coluna | Tipo | Regras |
|---|---|---|
| `name` | `varchar(200)` | Obrigatório. |
| `slug` | `varchar(64)` | Obrigatório; único (`uq_workspaces_slug`). |
| `status` | `varchar(32)` | `active` (padrão) ou `suspended`. |

Políticas: `workspaces_select` (selecionado, membro pelo `app.user_id` ou sistema) e `workspaces_write` (selecionado ou sistema).

### `memberships`

Papel de um usuário num workspace. RLS forçada.

| Coluna | Tipo | Regras |
|---|---|---|
| `workspace_id` | `uuid` | FK `workspaces.id`, `ON DELETE CASCADE`. |
| `user_id` | `uuid` | FK `users.id`, `ON DELETE CASCADE`; índice `ix_memberships_user_id`. |
| `role` | `varchar(32)` | `owner`, `admin`, `editor` ou `viewer`. |

Única por (`workspace_id`, `user_id`). Políticas: `memberships_select` (workspace selecionado, próprias memberships ou sistema) e `memberships_write` (workspace selecionado ou sistema).

### `sessions`

Sessão de login server-side ([ADR 0002](../adr/0002-sessao-server-side.md)). Dado da instância (sem `workspace_id`), com RLS forçada pelo dono: política `sessions_owner` (`user_id = app.user_id` ou sistema). Validação por token roda em modo de sistema.

| Coluna | Tipo | Regras |
|---|---|---|
| `user_id` | `uuid` | FK `users.id`, `ON DELETE CASCADE`; índice `ix_sessions_user_id`. |
| `token_hash` | `varchar(64)` | SHA-256 em hex do token do cookie; único (`uq_sessions_token_hash`). O token em claro nunca é gravado. |
| `last_seen_at` | `timestamptz` | Última validação. |
| `expires_at` | `timestamptz` | `last_seen_at + session_ttl` (expiração deslizante). |
| `ip_prefix` | `varchar(64)` | Prefixo de rede do IP (IPv4 /24, IPv6 /48); opcional. |
| `user_agent` | `varchar(200)` | User-agent truncado; opcional. |
| `revoked_at` | `timestamptz` | Nulo enquanto a sessão vale. |

`created_at` vem do relógio da aplicação (o mesmo da expiração).

### `user_tokens`

Token de uso único enviado por e-mail. Dado da instância, com RLS forçada pelo dono: política `user_tokens_owner` (`user_id = app.user_id`, `workspace_id = app.workspace_id` ou sistema). Tokens de conta (reset, verificação) são emitidos e consumidos em modo de sistema. Tokens de convite pertencem ao workspace que convida: são emitidos, reenviados e revogados na transação do workspace, junto com o convite; a pré-visualização e o aceite (só com o token) rodam em modo de sistema.

| Coluna | Tipo | Regras |
|---|---|---|
| `user_id` | `uuid` | FK `users.id`, `ON DELETE CASCADE`; índice `ix_user_tokens_user_id`. Obrigatório, exceto em convites (`ck_user_tokens_user_required`). |
| `workspace_id` | `uuid` | FK `workspaces.id`, `ON DELETE CASCADE`; índice `ix_user_tokens_workspace_id`. Só em convites (`ck_user_tokens_workspace_only_invitation`). |
| `purpose` | `varchar(32)` | `password_reset`, `email_verification` ou `invitation`. |
| `token_hash` | `varchar(64)` | SHA-256 em hex; único (`uq_user_tokens_token_hash`). |
| `expires_at` | `timestamptz` | Após este instante o token é recusado. |
| `used_at` | `timestamptz` | Preenchido no consumo; token usado é recusado. |

### `invitations`

Convite de um e-mail para um workspace com um papel (plano 0002, F2.3), em `backend/src/knobridge/tenancy/`. Dado de workspace com RLS forçada: política `invitations_workspace` (`workspace_id = app.workspace_id` ou sistema). Pendente = sem `accepted_at` e sem `revoked_at` (um convite vencido continua pendente e pode ser reenviado). Reconvidar o mesmo e-mail revoga o pendente; reenviar troca o token (o antigo é marcado como usado) e recomeça a validade (`invitation_ttl`, padrão 7 dias); revogar marca o token como usado.

| Coluna | Tipo | Regras |
|---|---|---|
| `workspace_id` | `uuid` | FK `workspaces.id`, `ON DELETE CASCADE`. |
| `email` | `varchar(320)` | Obrigatório, em minúsculas. Um pendente por (`workspace_id`, `email`): índice único parcial `uq_invitations_pending_email` (`WHERE accepted_at IS NULL AND revoked_at IS NULL`). |
| `role` | `varchar(32)` | `owner`, `admin`, `editor` ou `viewer`; nunca acima do papel de quem convida. |
| `invited_by_user_id` | `uuid` | FK `users.id`, `ON DELETE SET NULL`. |
| `token_id` | `uuid` | FK `user_tokens.id`, `ON DELETE CASCADE`; único (`uq_invitations_token_id`). Link atual. |
| `expires_at` | `timestamptz` | Cópia da validade do token atual, para listar sem ler `user_tokens`. |
| `accepted_at` | `timestamptz` | Preenchido no aceite, junto com a membership. |
| `revoked_at` | `timestamptz` | Preenchido ao revogar ou ao ser substituído por novo convite. |

### `audit_events`

Trilha de auditoria, append-only ([`backend/src/knobridge/audit/`](../../backend/src/knobridge/audit/AGENTS.md)). Gravada pelo `AuditService.record` na mesma transação da mudança. Sem `created_at`/`updated_at`: a data é `occurred_at`, do relógio da aplicação. RLS forçada, com políticas separadas por comando:

- `audit_events_select`: `workspace_id = app.workspace_id` ou sistema. Eventos da instância (`workspace_id` nulo) só são legíveis em modo de sistema (superadmin).
- `audit_events_insert`: no workspace selecionado, evento da instância cujo ator é o `app.user_id`, ou sistema.
- `audit_events_delete`: só sistema (retenção).
- Sem política de UPDATE: nenhum evento é alterado, nem em modo de sistema.

| Coluna | Tipo | Regras |
|---|---|---|
| `workspace_id` | `uuid` | FK `workspaces.id`, `ON DELETE CASCADE`; nulo para eventos da instância (setup, login, superadmin). Índice `ix_audit_events_workspace_id_occurred_at` (`workspace_id`, `occurred_at`). |
| `actor_user_id` | `uuid` | FK `users.id`, `ON DELETE SET NULL`; nulo para o próprio sistema ou chamador anônimo (ex.: login falho). Índice `ix_audit_events_actor_user_id`. |
| `action` | `varchar(64)` | Obrigatório; valor do catálogo `AuditAction` (sem `CHECK`, para ação nova não exigir migração). Índice `ix_audit_events_action`. |
| `target_type` | `varchar(64)` | Tipo do alvo (ex.: `membership`); opcional. |
| `target_id` | `varchar(64)` | Id do alvo; opcional. |
| `details` | `jsonb` | Metadados da ação, padrão `{}`. Nunca segredo; dado pessoal só o necessário (chaves com `password`, `secret`, `token`, `cookie`, `authorization`, `api_key` são recusadas). |
| `ip_address` | `varchar(45)` | IP do chamador normalizado; opcional. |
| `occurred_at` | `timestamptz` | Obrigatório; relógio injetado da aplicação. |

### `login_attempts`

Limitação de tentativas de login ([ADR 0002](../adr/0002-sessao-server-side.md)), em `backend/src/knobridge/security/throttle.py`. Uma linha por chave: o SHA-256 de `lower(email)|ip`, de modo que a tabela não guarda e-mail nem IP. Janela fixa contada da primeira falha (`login_attempt_window`, padrão 15 min); atingido `login_max_attempts` (padrão 5) dentro da janela, o login responde 429 até ela acabar, mesmo com a senha certa. Login bem-sucedido apaga a linha. Sem `created_at`/`updated_at`: as datas vêm do relógio da aplicação. RLS forçada com uma única política, `login_attempts_system` (só modo de sistema), porque quem tenta logar ainda é anônimo.

A mesma tabela guarda o limite de e-mails de conta por endereço (plano 0002, F2.2), com chaves de escopo próprio: SHA-256 de `password_reset|lower(email)|` e de `email_verification|lower(email)|` (sem IP, para limitar o que chega a uma caixa de entrada vinda de qualquer origem). Até `account_email_max_requests` (padrão 3) por `account_email_window` (padrão 1 h); acima disso, o "esqueci a senha" responde igual sem enviar e o reenvio de verificação responde 429. O contador conta pedidos, inclusive para e-mails sem conta.

| Coluna | Tipo | Regras |
|---|---|---|
| `key_hash` | `varchar(64)` | SHA-256 em hex da chave; único (`uq_login_attempts_key_hash`). |
| `failures` | `integer` | Falhas na janela atual. |
| `window_started_at` | `timestamptz` | Primeira falha da janela atual; janela vencida recomeça em 1 na próxima falha. |

### `provider_credentials`

Chave de API de um provedor de LLM, por workspace (plano 0002, F4.1), em [`backend/src/knobridge/llm/`](../../backend/src/knobridge/llm/AGENTS.md). Dado de workspace com RLS forçada: política `provider_credentials_workspace` (`workspace_id = app.workspace_id` ou sistema). A chave é gravada só cifrada com AES-256-GCM ([ADR 0003](../adr/0003-segredos-cifrados.md)), com chave de dados derivada de `KNOBRIDGE_SECRET_KEY` (HKDF, `info` `knobridge/provider-credentials/v1`) e dados associados `provider_credential:<workspace_id>:<id>`, de modo que o texto cifrado não decifra em outra linha nem em outro workspace. A API nunca devolve a chave, só `****` + `key_last4`. Owner, admin e editor gerenciam; viewer não. Criar, alterar e excluir auditam `provider.created`, `provider.updated` (`fields`: `name`, `base_url`, `key`) e `provider.deleted`, sem a chave.

| Coluna | Tipo | Regras |
|---|---|---|
| `workspace_id` | `uuid` | FK `workspaces.id`, `ON DELETE CASCADE`. |
| `name` | `varchar(200)` | Obrigatório; único por workspace (`uq_provider_credentials_workspace_id_name`; 409 `provider_name_taken`). |
| `kind` | `varchar(32)` | `openai`, `anthropic`, `openrouter` ou `fake`. `fake` é recusado em produção (422 `provider_kind_not_allowed`). Não muda depois de criado. |
| `base_url` | `varchar(500)` | Opcional; endpoint alternativo (`http(s)://`), ex.: gateway ou servidor compatível. |
| `key_ciphertext` | `text` | `v<versão da chave>.<base64url(nonce ‖ cifrado ‖ tag)>`. Recifrado a cada troca de chave. |
| `key_last4` | `varchar(4)` | Últimos 4 caracteres da chave (que tem no mínimo 8), para exibição. |

Assistentes (F4.3) vão referenciar `provider_credentials.id` com `ON DELETE RESTRICT`: credencial em uso não pode ser excluída.
