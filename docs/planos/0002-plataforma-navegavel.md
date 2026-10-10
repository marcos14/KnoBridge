---
id: 0002
titulo: Plataforma navegável — autenticação, multi-tenant, telas administrativas e chat
slug: plataforma-navegavel
solicitado_por: usuario
criado_em: 2026-10-10
atualizado_em: 2026-10-10
status: em_execucao
aprovado_em: 2026-10-10
aprovado_por: usuario
concluido_em: null
branch: plano/0002-plataforma-navegavel
fases:
  - id: F1
    titulo: "Fundação de dados, segurança e e-mail (backend)"
    status: em_execucao
    subfases:
      - id: F1.1
        titulo: "Modelos de tenancy e RLS"
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: c7f63af
      - id: F1.2
        titulo: "Primitivas de segurança: senha, tokens, sessões e CSRF"
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: null
      - id: F1.3
        titulo: "E-mail: interface, SMTP, templates e Mailpit"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F1.4
        titulo: "Auditoria: modelo, serviço e consulta"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F2
    titulo: "API de autenticação, tenancy e administração (backend)"
    status: pendente
    subfases:
      - id: F2.1
        titulo: "Setup inicial, login, logout, sessão atual e RBAC"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.2
        titulo: "Recuperação de senha, verificação de e-mail, perfil e sessões"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.3
        titulo: "Convites e membros do workspace"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.4
        titulo: "API do superadmin"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F3
    titulo: "Shell navegável e telas de conta e administração (frontend)"
    status: pendente
    subfases:
      - id: F3.1
        titulo: "Infraestrutura de autenticação no frontend"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.2
        titulo: "Shell: sidebar, menus, seletor de workspace, menu do usuário e tema"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.3
        titulo: "Telas públicas: setup, login, senha, convite e verificação"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.4
        titulo: "Perfil e segurança da conta"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.5
        titulo: "Membros, convites e configurações do workspace"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.6
        titulo: "Auditoria e painel do superadmin"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F4
    titulo: "Provedores de LLM, assistentes e conversas (backend)"
    status: pendente
    subfases:
      - id: F4.1
        titulo: "Segredos cifrados e credenciais de provedor"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.2
        titulo: "Camada LLM: interface, adaptadores e teste de conexão"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.3
        titulo: "Assistentes"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.4
        titulo: "Conversas, mensagens em streaming e feedback"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.5
        titulo: "Consulta administrativa de conversas"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F5
    titulo: "Assistentes, chat e conversas (frontend)"
    status: pendente
    subfases:
      - id: F5.1
        titulo: "Telas de provedores e assistentes"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F5.2
        titulo: "Chat com streaming"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F5.3
        titulo: "Tela de conversas (owner/admin)"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F6
    titulo: "Ponta a ponta e documentação"
    status: pendente
    subfases:
      - id: F6.1
        titulo: "Compose, E2E contra a stack e CI"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F6.2
        titulo: "Specs, guias e documentação final"
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes:
  - id: D1
    data: 2026-10-10
    por: usuario
    decisao: "Foco nos sistemas navegáveis: autenticação, multi-tenant, telas administrativas, menus e chat, com a stack da seção 8 da visão."
    motivo: "Pedido do usuário ao redirecionar o plano."
    alternativas: "Implementar o roadmap da visão na ordem (Fase 0 com protótipo de CLI, harness e experimentos)."
    adr: null
  - id: D2
    data: 2026-10-10
    por: usuario
    decisao: "Multi-tenant com N workspaces por usuário e papéis owner/admin/editor/viewer; só convite, sem cadastro público; superadmin da instância."
    motivo: "Instalação self-host fechada, com consultores atendendo vários clientes."
    alternativas: "1 workspace por usuário; cadastro público."
    adr: null
  - id: D3
    data: 2026-10-10
    por: usuario
    decisao: "E-mail por interface EmailSender + SMTP, Mailpit no compose de dev, com recuperação de senha, convites e verificação de e-mail."
    motivo: "Fluxos de conta completos e testáveis localmente."
    alternativas: "Sem verificação de e-mail."
    adr: null
  - id: D4
    data: 2026-10-10
    por: usuario
    decisao: "Primeiro superadmin criado por tela de setup inicial quando não há usuários."
    motivo: "Escolha do usuário."
    alternativas: "Comando CLI; variáveis de ambiente."
    adr: null
  - id: D5
    data: 2026-10-10
    por: usuario
    decisao: "Chat real com LLM (OpenAI, Anthropic, OpenRouter) sem RAG; sem fonte o assistente responde a mensagem padrão sem chamar o LLM (regra 8); caminho com fontes implementado e testado com Retriever fake; teste de conexão chama o LLM real."
    motivo: "Respeita a regra de citações e deixa o motor pronto para o plano de RAG."
    alternativas: "Chat com provedor fake; RAG básico já neste plano; modo livre sem fontes (exigiria ADR mudando a regra 8)."
    adr: null
  - id: D6
    data: 2026-10-10
    por: usuario
    decisao: "Sessão por cookie httpOnly com sessão no banco e CSRF double-submit; telas de Fontes, Pipelines, Coleções e Canais só como esqueleto; extras: auditoria, perfil e segurança, tema claro/escuro, painel do superadmin; todos conversam, owner/admin veem todas as conversas, owner/admin/editor configuram assistentes."
    motivo: "Respostas do entendimento."
    alternativas: "JWT; CRUD completo das telas de ingestão; privacidade total das conversas."
    adr: null
  - id: D7
    data: 2026-10-10
    por: agente
    decisao: "Formulários com react-hook-form + zod; tabelas e diálogos compartilhados em components/; rotas /w/:workspaceId no frontend e /v1/workspaces/{workspace_id} no backend com acesso validado pela membership da sessão."
    motivo: "Padrão do shadcn/ui; workspace explícito na URL facilita alternar e compartilhar links sem aceitar workspace_id do cliente como autorização."
    alternativas: "Workspace em header ou só na sessão; Formik."
    adr: null
  - id: D8
    data: 2026-10-10
    por: agente
    decisao: "Branch plano/0002-plataforma-navegavel criada a partir de plano/0001-bootstrap, que ainda não foi integrada à main."
    motivo: "O plano depende do bootstrap."
    alternativas: "Esperar o merge do bootstrap na main."
    adr: null
  - id: D9
    data: 2026-10-10
    por: agente
    decisao: "RLS: escopo por set_config transacional (app.workspace_id, app.user_id) e modo de sistema por app.system=on aceito pelas políticas; políticas separadas de leitura e escrita; workspaces com RLS forçada; users sem RLS (identidade da instância); enums como VARCHAR+CHECK."
    motivo: "Uma credencial e um pool só; parâmetros ligados sem SQL dinâmico; escrita restrita ao workspace selecionado impede autopromoção."
    alternativas: "Papel separado com BYPASSRLS para tarefas de sistema (registrado no ADR 0001 como evolução)."
    adr: null
  - id: D10
    data: 2026-10-10
    por: agente
    decisao: "Sessões e user_tokens com RLS forçada por user_id (ou modo de sistema); CSRF double-submit assinado com HMAC da secret_key; produção exige secret_key própria com 32+ caracteres; session_ttl ISO 8601 (P7D); só expiração deslizante por ora; IP e user-agent resumidos (LGPD)."
    motivo: "Defesa em profundidade para credenciais; impede cookie CSRF plantado por subdomínio."
    alternativas: "Sessões sem RLS; CSRF sem assinatura; expiração absoluta já agora."
    adr: null
pendencias_usuario: []
---
# Plano 0002 — Plataforma navegável: autenticação, multi-tenant, telas administrativas e chat

## 1. Pedido original

> "Implemente o docs\01-visao-do-projeto.md fase a fase, item a item, cada um em um agente independente"

Redirecionado pelo usuário na mesma conversa:

> "continue, mas foque em planejar os sistemas navegáveis (o que o usuário vê), telas administrativas, menus, autenticação, recuperação de senha, chats, multitenants.... Quanto a linguagem, pode usar as recomendações do arquivo: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic para o backend, React + TypeScript + Vite, shadcn/ui, React Flow (xyflow), TanStack Query para o frontend, docker compose para infra"

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | Foco e stack | Sistemas navegáveis (telas, menus, autenticação, recuperação de senha, chats, multi-tenant) com a stack da seção 8 da visão. Conectores reais, ingestão, harness e RAG ficam para planos seguintes. | 2026-10-10 |
| 2 | Modelo de multi-tenant e cadastro | Só convite, sem cadastro público. Um usuário pode pertencer a vários workspaces, com papel em cada (owner, admin, editor, viewer). Existe superadmin da instância. | 2026-10-10 |
| 3 | Envio de e-mail | Interface `EmailSender` com SMTP; Mailpit no compose de dev; templates pt-BR; recuperação de senha, convites e verificação de e-mail. | 2026-10-10 |
| 4 | Chats | Chat real com LLM (OpenAI, Anthropic, OpenRouter; chave cifrada por workspace), streaming SSE, histórico, feedback 👍/👎 e tela de conversas. Sem RAG: sem fonte, o assistente diz que não sabe (regra de citações). | 2026-10-10 |
| 5 | Telas de Fontes, Pipelines, Coleções e Canais | Só navegação e esqueleto (menus e páginas com estado vazio). | 2026-10-10 |
| 6 | Primeiro superadmin | Tela de setup inicial: sem nenhum usuário, o app mostra um assistente de instalação que cria o superadmin. | 2026-10-10 |
| 7 | Sessão do painel | Cookie httpOnly + sessão no banco (revogável, lista de sessões, logout em todos os dispositivos), SameSite + CSRF. API keys ficam para o plano de canais. | 2026-10-10 |
| 8 | Extras administrativos | Log de auditoria, perfil e segurança, tema claro/escuro, painel do superadmin. | 2026-10-10 |
| 9 | Quem usa o chat e vê conversas | Todos os membros conversam e veem as próprias conversas; owner/admin veem todas; owner/admin/editor configuram assistentes. | 2026-10-10 |

**Resumo**: ao final deste plano, uma instalação nova abre na tela de setup, cria o superadmin, que cria workspaces e convida owners por e-mail; membros entram por convite, fazem login, recuperam senha, editam perfil e sessões, alternam tema e workspace; owner/admin gerenciam membros, convites, configurações e auditoria; admin/editor configuram provedores de LLM e assistentes; todos conversam com os assistentes em streaming, com histórico e feedback; owner/admin veem todas as conversas. Fontes, Pipelines, Coleções e Canais aparecem no menu com estado vazio.

**Fora do escopo**: conectores, pipelines executáveis, canvas funcional, ingestão, embeddings, busca, RAG, harness, API keys e canais externos (REST pública, OpenAI-compat, MCP, Slack, Google Chat, widget), OIDC, MFA, custos.

**Consequência da regra de citações (AGENTS.md, regra 8)**: a orquestração do chat já tem a etapa de recuperação atrás de uma interface `Retriever`. Neste plano a implementação de produção é `NullRetriever` (nenhuma fonte), então em uso real o assistente responde a mensagem padrão "não encontrei fonte" e oferece abrir chamado, sem inventar. O caminho com fontes (LLM em streaming com citações numeradas) é implementado e testado com um `Retriever` fake e passa a valer quando o plano de RAG plugar a busca real. O teste de conexão com o provedor chama o LLM de verdade (D5).

## 3. Critérios de aceite

- [ ] Instalação nova: `/` leva ao setup; o setup cria o superadmin e some depois disso (também por API, com proteção contra corrida).
- [ ] Login, logout, logout em todos os dispositivos, recuperação de senha, verificação de e-mail e aceite de convite funcionando ponta a ponta com e-mails visíveis no Mailpit.
- [ ] Multi-tenant: toda tabela de dados de workspace tem `workspace_id` e RLS forçada; testes de isolamento para cada consulta (workspace B não vê dado do A).
- [ ] RBAC owner/admin/editor/viewer aplicado na API e refletido no menu; superadmin com painel próprio.
- [ ] Auditoria registrando os eventos de autenticação, membros, convites, configurações, provedores e assistentes, com tela de consulta paginada e filtrável.
- [ ] Provedores de LLM com chave cifrada em repouso, nunca devolvida pela API; assistentes configuráveis; chat com streaming SSE, histórico, feedback e tela de conversas para admin.
- [ ] Shell navegável: sidebar com menus por papel, seletor de workspace, menu do usuário, tema claro/escuro/sistema persistido, i18n pt-BR, páginas esqueleto de Fontes, Pipelines, Coleções e Canais.
- [ ] E2E Playwright contra a stack do compose cobrindo setup → login → convite → aceite → recuperação de senha → chat; rodando na CI.
- [ ] Gates de cobertura ≥ 95% (backend e frontend), lint, typecheck, `check_agents_md`, `check_plans`, contrato OpenAPI atualizado; ADRs e specs escritos.

## 4. Fases e subfases

Convenções que valem para todas as subfases (o agente recebe este bloco junto com a sua subfase):

- Backend: rotas do painel sob `/v1`; rotas de workspace sob `/v1/workspaces/{workspace_id}/...`, com o acesso validado pela membership do usuário autenticado (o `workspace_id` do path só seleciona; a permissão vem da sessão) e a sessão de banco com `app.workspace_id` e `app.user_id` definidos por `SET LOCAL` para a RLS. Listagens paginadas (`limit`/`offset`, `total` na resposta). Erros no formato único. Cada evento relevante chama o serviço de auditoria. Testes de isolamento para toda consulta nova.
- OpenAPI: toda mudança de rota regenera `docs/specs/openapi.json` (`uv run knobridge-openapi`) e, no frontend, `pnpm gen:api`.
- Frontend: rotas de workspace sob `/w/:workspaceId/...`; dados só via `lib/api` + TanStack Query; formulários com react-hook-form + zod (D7); textos via i18n pt-BR; testes com Testing Library + MSW; componentes shadcn adicionados só quando usados.
- Relógio injetado e aleatoriedade controlada nos testes; nenhum provedor externo chamado em teste.

### F1 — Fundação de dados, segurança e e-mail (backend)

#### F1.1 — Modelos de tenancy e RLS

- **Objetivo**: base ORM e os modelos de identidade e tenancy com RLS forçada.
- **Entregáveis**: `core/models.py` (Base declarativa tipada, mixins de id UUID e timestamps); pacote `tenancy/` com `models.py` (`User`: e-mail único case-insensitive, nome, hash de senha, `provider` = `password`, `is_superadmin`, `status` ativo/suspenso, `email_verified_at`, `locale`, `theme`; `Workspace`: nome, slug único, status ativo/suspenso; `Membership`: `workspace_id`, `user_id`, `role` owner/admin/editor/viewer, única por par); migração Alembic com `ENABLE` + `FORCE ROW LEVEL SECURITY` nas tabelas com `workspace_id` e políticas por `current_setting('app.workspace_id', true)` e `app.user_id` (membership visível ao próprio usuário em qualquer workspace); `core/db.py` ganha `scoped_session(workspace_id, user_id)` / helper que aplica `SET LOCAL`, e um modo de sistema explícito para tarefas da instância (setup, superadmin, login) documentado; `docs/adr/AGENTS.md` e `docs/adr/0001-tenancy-e-rls.md` (N workspaces por usuário, convite, superadmin, usuários como identidade da instância sem `workspace_id`, RLS por `SET LOCAL`, papel do banco não superusuário com `FORCE`); `docs/specs/AGENTS.md` atualizado e `docs/specs/modelo-de-dados.md` (início); `AGENTS.md` de `tenancy/`.
- **Contexto necessário**: `AGENTS.md` raiz (2, 5, 6, 9, 13); `backend/AGENTS.md`; `backend/migrations/AGENTS.md`; `backend/src/knobridge/core/AGENTS.md`; `core/db.py`, `core/settings.py`, `tests/conftest.py`, `migrations/env.py`, `migrations/versions/*`; `docs/AGENTS.md`; seções 5 e 7.7 da visão; este bloco de convenções.
- **Critérios de aceite**: `test_membership_rls_hides_other_workspace`, `test_workspace_rls_requires_setting`, `test_user_sees_own_memberships_across_workspaces`, `test_email_unique_case_insensitive`, `test_migration_upgrade_downgrade_tenancy`; isolamento testado com Postgres real e com um papel não dono; cobertura ≥ 95%.
- **Depende de**: nenhuma.

#### F1.2 — Primitivas de segurança: senha, tokens, sessões e CSRF

- **Objetivo**: base de autenticação reutilizável, sem rotas ainda.
- **Entregáveis**: `security/` com `passwords.py` (argon2id via `argon2-cffi`, verificação e rehash), `tokens.py` (tokens opacos aleatórios; só o hash SHA-256 vai ao banco), modelo `UserToken` (finalidade: reset de senha, verificação de e-mail, convite; expiração; uso único) e modelo `Session` (hash do token, user, criada/última atividade/expira, IP e user-agent resumidos, revogada); serviço de sessões (criar, validar com expiração deslizante, revogar uma, revogar todas); CSRF por double-submit (cookie não httpOnly + header `X-CSRF-Token`) como dependência/middleware para métodos não seguros; política de senha (mínimo 12 caracteres, sem lista de regras exóticas); settings: `secret_key`, `session_ttl`, `session_cookie_name`, `cookie_secure`; `Clock` injetável em `core/`; migração; `docs/adr/0002-sessao-server-side.md`; `AGENTS.md` de `security/`.
- **Contexto necessário**: `AGENTS.md` raiz (5, 6, 9); `backend/AGENTS.md`; AGENTS de `core/`, `tenancy/`, `migrations/`; `core/db.py`, `core/models.py`, `core/settings.py`, `tenancy/models.py`; `docs/adr/0001-tenancy-e-rls.md`; convenções.
- **Critérios de aceite**: `test_password_hash_and_verify`, `test_password_rehash_when_params_change`, `test_token_stored_only_as_hash`, `test_token_expired_rejected`, `test_token_single_use`, `test_session_sliding_expiration`, `test_revoke_all_sessions`, `test_csrf_rejects_missing_header`, `test_csrf_allows_safe_methods`; cobertura ≥ 95%.
- **Depende de**: F1.1.

#### F1.3 — E-mail: interface, SMTP, templates e Mailpit

- **Objetivo**: enviar e-mails transacionais em pt-BR.
- **Entregáveis**: `email/` com `EmailSender` (Protocol), `SmtpEmailSender` (`aiosmtplib`), `FakeEmailSender` em `tests/fakes/`, renderização de templates (Jinja2, HTML + texto) para redefinição de senha, verificação de e-mail, convite e definição de senha inicial; settings `smtp_host/port/user/password/from/starttls`, `public_base_url` para os links; serviço Mailpit (`axllent/mailpit`, tag fixa) no `deploy/docker-compose.yml` e API/worker apontando para ele em dev; `.env.example` (backend e deploy) e guia `docs/guias/subir-ambiente.md` atualizados; `AGENTS.md` de `email/` e de `tests/fakes/`.
- **Contexto necessário**: `AGENTS.md` raiz (5, 6); `backend/AGENTS.md`; `deploy/AGENTS.md`; `core/settings.py`, `backend/.env.example`, `deploy/docker-compose.yml`, `deploy/.env.example`, `docs/guias/subir-ambiente.md`; convenções.
- **Critérios de aceite**: `test_render_password_reset_contains_link`, `test_templates_have_text_and_html`, `test_smtp_sender_sends_message` (servidor SMTP local em processo, sem rede externa), `test_fake_sender_records_messages`; `docker compose config` válido; cobertura ≥ 95%.
- **Depende de**: nenhuma.

#### F1.4 — Auditoria: modelo, serviço e consulta

- **Objetivo**: trilha de auditoria usada por todas as subfases seguintes.
- **Entregáveis**: `audit/` com modelo `AuditEvent` (`workspace_id` nulo para eventos da instância, ator, ação com nomes estáveis tipo `auth.login.succeeded`, alvo tipo/id, metadados JSON sem segredo nem dado pessoal além do necessário, IP, data), RLS; serviço `record(...)` chamado dentro da mesma transação; repositório de consulta com filtros (ação, ator, período) e paginação; migração; `AGENTS.md` com o catálogo de ações e a regra de não logar segredos. A rota HTTP de consulta entra na F2.1 junto com as dependências de autenticação.
- **Contexto necessário**: `AGENTS.md` raiz (6, 9); `backend/AGENTS.md`; AGENTS de `core/`, `tenancy/`, `migrations/`; `core/db.py`, `core/models.py`, `tenancy/models.py`; `docs/adr/0001-tenancy-e-rls.md`; convenções.
- **Critérios de aceite**: `test_record_event_in_same_transaction`, `test_audit_query_filters_and_paginates`, `test_audit_rls_hides_other_workspace`, `test_instance_events_not_visible_in_workspace`; cobertura ≥ 95%.
- **Depende de**: F1.1.

### F2 — API de autenticação, tenancy e administração (backend)

#### F2.1 — Setup inicial, login, logout, sessão atual e RBAC

- **Objetivo**: primeiras rotas autenticadas e as dependências que todas as outras usam.
- **Entregáveis**: `GET /v1/setup/status` (`needs_setup`), `POST /v1/setup` (só sem usuários; advisory lock; cria superadmin com senha e e-mail verificado; abre sessão); `GET /v1/auth/csrf`, `POST /v1/auth/login` (mensagem genérica em falha, limitação de tentativas por e-mail+IP em tabela com janela, usuário suspenso barrado), `POST /v1/auth/logout`, `POST /v1/auth/logout-all`, `GET /v1/me` (usuário, workspaces com papel, `is_superadmin`); dependências `current_user`, `require_superadmin`, `workspace_context(workspace_id)` (valida membership e workspace ativo, aplica `SET LOCAL`), `require_role(min_role)`; `GET /v1/workspaces/{id}/audit` (owner/admin) usando a F1.4; eventos de auditoria; OpenAPI regenerado; `AGENTS.md` de `api/` atualizado com o padrão de dependências.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `api/`, `security/`, `tenancy/`, `audit/`; `api/app.py`, `api/health.py`, `core/errors.py`, `core/db.py`, `security/*`, `tenancy/models.py`, `audit/*`; ADRs 0001 e 0002; convenções.
- **Critérios de aceite**: `test_setup_creates_superadmin_once`, `test_setup_concurrent_requests_create_single_admin`, `test_login_sets_httponly_cookie`, `test_login_generic_error_on_wrong_password`, `test_login_rate_limited`, `test_suspended_user_cannot_login`, `test_logout_all_revokes_sessions`, `test_me_lists_memberships`, `test_workspace_context_rejects_non_member`, `test_require_role_hierarchy`, `test_audit_endpoint_isolated_by_workspace`; cobertura ≥ 95%.
- **Depende de**: F1.2, F1.4.

#### F2.2 — Recuperação de senha, verificação de e-mail, perfil e sessões

- **Objetivo**: autosserviço da conta.
- **Entregáveis**: `POST /v1/auth/password/forgot` (resposta idêntica exista ou não o e-mail; envia link), `POST /v1/auth/password/reset` (token de uso único; revoga todas as sessões), `POST /v1/auth/email/verify`, `POST /v1/auth/email/resend`; `PATCH /v1/me` (nome, `locale`, `theme` claro/escuro/sistema), `POST /v1/me/password` (exige senha atual; mantém só a sessão corrente), `GET /v1/me/sessions`, `DELETE /v1/me/sessions/{id}`; auditoria; OpenAPI regenerado.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `api/`, `security/`, `email/`, `audit/`; arquivos de rotas de auth da F2.1, `security/*`, `email/*`, `tests/fakes/*`; convenções.
- **Critérios de aceite**: `test_forgot_password_same_response_for_unknown_email`, `test_reset_password_revokes_sessions`, `test_reset_token_reuse_rejected`, `test_verify_email_marks_verified`, `test_change_password_requires_current`, `test_list_and_revoke_own_sessions`, `test_cannot_revoke_other_user_session`, `test_update_profile_theme_and_locale`; cobertura ≥ 95%.
- **Depende de**: F2.1, F1.3.

#### F2.3 — Convites e membros do workspace

- **Objetivo**: entrada de pessoas por convite e gestão de papéis.
- **Entregáveis**: `POST /v1/workspaces/{id}/invites` (owner/admin; admin não convida owner), `GET` (pendentes), `DELETE` (revogar), `POST .../invites/{id}/resend`; `GET /v1/invites/{token}` (público: workspace, e-mail, se o usuário já existe), `POST /v1/invites/{token}/accept` (cria usuário com nome e senha, ou vincula usuário logado com o mesmo e-mail; marca e-mail verificado); `GET /v1/workspaces/{id}/members`, `PATCH .../members/{user_id}` (papel), `DELETE .../members/{user_id}`; regras: sempre ao menos um owner, ninguém altera papel acima do seu; `PATCH /v1/workspaces/{id}` (nome, owner/admin); auditoria; OpenAPI regenerado.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `api/`, `tenancy/`, `security/`, `email/`, `audit/`; rotas e dependências da F2.1, `tenancy/models.py`, `security/tokens.py`, `email/*`; ADR 0001; convenções.
- **Critérios de aceite**: `test_invite_sends_email_with_token`, `test_admin_cannot_invite_owner`, `test_accept_invite_creates_user`, `test_accept_invite_existing_user_joins`, `test_invite_token_expired`, `test_last_owner_cannot_be_removed_or_demoted`, `test_members_isolated_by_workspace`, `test_viewer_cannot_manage_members`; cobertura ≥ 95%.
- **Depende de**: F2.1, F1.3.

#### F2.4 — API do superadmin

- **Objetivo**: administração da instância.
- **Entregáveis**: `GET/POST /v1/admin/workspaces` (criar com nome/slug e convite do primeiro owner por e-mail), `PATCH /v1/admin/workspaces/{id}` (renomear, suspender, reativar), `GET /v1/admin/users` (busca por e-mail/nome, paginação), `PATCH /v1/admin/users/{id}` (suspender/reativar, revogando sessões; conceder/remover superadmin, nunca removendo o último), `GET /v1/admin/audit` (eventos da instância); workspace suspenso bloqueia acesso dos membros; auditoria; OpenAPI regenerado.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `api/`, `tenancy/`, `audit/`; dependências da F2.1, serviço de convites da F2.3, `tenancy/models.py`, `audit/*`; convenções.
- **Critérios de aceite**: `test_non_superadmin_forbidden`, `test_create_workspace_invites_owner`, `test_suspend_workspace_blocks_members`, `test_suspend_user_revokes_sessions`, `test_cannot_remove_last_superadmin`, `test_admin_users_search_paginates`; cobertura ≥ 95%.
- **Depende de**: F2.3.

### F3 — Shell navegável e telas de conta e administração (frontend)

#### F3.1 — Infraestrutura de autenticação no frontend

- **Objetivo**: cliente, sessão e guardas de rota prontos para as telas.
- **Entregáveis**: `lib/api/client.ts` com `credentials: "include"`, header CSRF automático em métodos não seguros e tratamento de 401 (invalida `me` e leva ao login preservando o destino); hooks `useSetupStatus`, `useMe`, `useLogin`, `useLogout`; `features/auth/` com `RequireAuth`, `RequireSetupDone`, `RequireWorkspaceRole`, `RequireSuperadmin`; utilitário de workspace atual a partir de `/w/:workspaceId`; dependências `react-hook-form`, `zod`, `@hookform/resolvers` e componentes shadcn de formulário; handlers MSW por recurso em `src/test/`; i18n de erros da API por `code`; OpenAPI regenerado; `AGENTS.md` de `features/` e `features/auth/`.
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `src/`, `src/app/`, `src/lib/api/`, `src/test/`; `src/lib/api/*`, `src/app/*`, `src/test/*`, `src/i18n/*`, `docs/specs/openapi.json`; convenções.
- **Critérios de aceite**: testes do cliente (CSRF enviado em POST e não em GET; 401 redireciona preservando destino), dos guardas (sem sessão → login; sem setup → setup; papel insuficiente → página 403; não superadmin → 403), dos hooks com MSW; gates do frontend com cobertura ≥ 95.
- **Depende de**: F2.1.

#### F3.2 — Shell: sidebar, menus, seletor de workspace, menu do usuário e tema

- **Objetivo**: a moldura navegável do painel.
- **Entregáveis**: layout autenticado com sidebar (shadcn `sidebar`, recolhível, responsiva) e topbar; itens de menu por papel: Início, Chat, Conversas (owner/admin), Assistentes e Provedores (owner/admin/editor), Fontes, Pipelines, Coleções, Canais (esqueleto), Membros, Configurações e Auditoria (owner/admin), Administração da instância (superadmin); seletor de workspace (lista do `me`, troca a rota); menu do usuário (perfil, segurança, tema, sair); tema claro/escuro/sistema aplicado por classe no `html`, salvo no perfil (`PATCH /v1/me`) e em `localStorage` para o primeiro paint; páginas esqueleto com estado vazio e texto explicativo para Fontes, Pipelines, Coleções e Canais; página 403 e 404 dentro do shell; atalho `/` → último workspace usado ou tela "sem workspace"; `AGENTS.md` das pastas novas.
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `src/app/`, `src/components/`, `features/auth/`; `src/app/*`, `features/auth/*`, `src/lib/api/*`, `src/i18n/locales/pt-BR.json`; convenções.
- **Critérios de aceite**: testes de menu por papel (viewer não vê Membros; superadmin vê Administração), seletor troca de workspace, tema alterna e persiste (chamada `PATCH /v1/me`), páginas esqueleto renderizam, navegação por teclado e landmarks; cobertura ≥ 95.
- **Depende de**: F3.1.

#### F3.3 — Telas públicas: setup, login, senha, convite e verificação

- **Objetivo**: todas as telas de fora da sessão.
- **Entregáveis**: layout público; `/setup` (nome, e-mail, senha, confirmação); `/login` (com link "esqueci minha senha" e redirecionamento ao destino); `/esqueci-senha` (confirmação genérica); `/redefinir-senha?token=` ; `/convite/:token` (mostra workspace; cria conta ou entra com a conta existente e aceita); `/verificar-email?token=`; validação com zod, mensagens i18n, estados de carregamento e erro; acessibilidade (labels, foco no erro).
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/`, `features/auth/`; `features/auth/*`, `src/app/router.tsx`, `src/lib/api/*`, handlers MSW; convenções.
- **Critérios de aceite**: testes por tela (envio válido chama a API certa; validação bloqueia senha curta e confirmação diferente; erro da API exibido; token inválido mostra estado próprio; após setup/login vai para o shell); cobertura ≥ 95.
- **Depende de**: F3.1, F2.2, F2.3.

#### F3.4 — Perfil e segurança da conta

- **Objetivo**: telas de autosserviço da conta logada.
- **Entregáveis**: `/conta/perfil` (nome, idioma, tema; e-mail somente leitura com status de verificação e botão de reenviar); `/conta/seguranca` (trocar senha; lista de sessões com dispositivo resumido, último acesso, "esta sessão"; encerrar uma; encerrar todas as outras).
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/`; shell da F3.2, `src/lib/api/*`, handlers MSW; convenções.
- **Critérios de aceite**: testes de edição de perfil, troca de senha (erro de senha atual), listagem e revogação de sessões, reenvio de verificação; cobertura ≥ 95.
- **Depende de**: F3.2, F2.2.

#### F3.5 — Membros, convites e configurações do workspace

- **Objetivo**: gestão de pessoas e do workspace por owner/admin.
- **Entregáveis**: `/w/:id/membros` (tabela paginada com busca; alterar papel; remover com confirmação; aba de convites pendentes com reenviar e revogar; diálogo "convidar" com e-mail e papel respeitando as regras); `/w/:id/configuracoes` (nome do workspace); componentes compartilhados de tabela paginada e diálogo de confirmação em `components/`.
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/`, `src/components/`; shell da F3.2, `src/lib/api/*`, handlers MSW; convenções.
- **Critérios de aceite**: testes de convite (validação, papel owner indisponível para admin), alteração de papel, remoção com confirmação, erro do último owner exibido, revogar/reenviar convite, edição do nome; cobertura ≥ 95.
- **Depende de**: F3.2, F2.3.

#### F3.6 — Auditoria e painel do superadmin

- **Objetivo**: telas de auditoria do workspace e da instância.
- **Entregáveis**: `/w/:id/auditoria` (tabela paginada com filtros por ação, ator e período; detalhe do evento); `/admin/workspaces` (listar, criar com e-mail do owner, renomear, suspender/reativar), `/admin/usuarios` (busca, suspender/reativar, conceder/remover superadmin), `/admin/auditoria`; reutiliza a tabela paginada da F3.5.
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/`, `src/components/`; shell da F3.2, componentes da F3.5, `src/lib/api/*`, handlers MSW; convenções.
- **Critérios de aceite**: testes dos filtros (geram a query certa), criação de workspace, suspensão com confirmação, erro do último superadmin; cobertura ≥ 95.
- **Depende de**: F3.5, F2.4.

### F4 — Provedores de LLM, assistentes e conversas (backend)

#### F4.1 — Segredos cifrados e credenciais de provedor

- **Objetivo**: guardar chaves de API por workspace com segurança.
- **Entregáveis**: `core/crypto.py` (AES-GCM com chave derivada de `KNOBRIDGE_SECRET_KEY`, versão da chave no texto cifrado para rotação futura); modelo `ProviderCredential` (`workspace_id`, nome, tipo `openai`/`anthropic`/`openrouter`/`fake` — `fake` só fora de produção, `base_url` opcional, chave cifrada, últimos 4 caracteres para exibição), RLS; API `GET/POST/PATCH/DELETE /v1/workspaces/{id}/providers` (owner/admin/editor; a chave nunca volta, só `****1234`); auditoria; `docs/adr/0003-segredos-cifrados.md`; migração; OpenAPI regenerado.
- **Contexto necessário**: `AGENTS.md` raiz (6, 9); `backend/AGENTS.md`; AGENTS de `core/`, `api/`, `audit/`; `core/settings.py`, dependências da F2.1, `audit/*`; ADR 0001; convenções.
- **Critérios de aceite**: `test_encrypt_decrypt_roundtrip`, `test_ciphertext_differs_each_time`, `test_wrong_key_fails`, `test_provider_key_never_returned`, `test_fake_provider_rejected_in_production`, `test_providers_isolated_by_workspace`, `test_viewer_cannot_manage_providers`; cobertura ≥ 95%.
- **Depende de**: F2.1.

#### F4.2 — Camada LLM: interface, adaptadores e teste de conexão

- **Objetivo**: conversar com OpenAI, Anthropic e OpenRouter atrás de uma interface pequena.
- **Entregáveis**: `llm/` com `LLMProvider` (Protocol: `stream_chat(messages, model, params) -> AsyncIterator[ChatEvent]` com deltas de texto e uso de tokens no fim; `list_models()` opcional), adaptadores com SDKs oficiais (`openai` com `base_url` para OpenRouter e compatíveis; `anthropic`), `FakeLLMProvider` determinístico (usado em testes e no tipo `fake` de dev/E2E), fábrica a partir de `ProviderCredential`; erros mapeados para exceções de domínio (auth inválida, limite, indisponível); `POST /v1/workspaces/{id}/providers/{pid}/test` (chamada mínima real em produção; nos testes, adaptadores exercitados com transporte HTTP fake do SDK, nunca rede); `AGENTS.md` de `llm/` (D6 da visão: sem framework de LLM).
- **Contexto necessário**: `AGENTS.md` raiz (2, 5, 6); `backend/AGENTS.md`; AGENTS de `llm/` (criar), `api/`; `ProviderCredential` e rotas da F4.1, `core/crypto.py`, `core/errors.py`; seções 7.5 e 8 (LLM) da visão; convenções.
- **Critérios de aceite**: `test_openai_adapter_streams_deltas`, `test_anthropic_adapter_streams_deltas`, `test_openrouter_uses_base_url`, `test_provider_auth_error_mapped`, `test_fake_provider_is_deterministic`, `test_test_connection_endpoint_reports_failure`; cobertura ≥ 95%.
- **Depende de**: F4.1.

#### F4.3 — Assistentes

- **Objetivo**: configuração de assistentes por workspace.
- **Entregáveis**: `assistants/` com modelo `Assistant` (`workspace_id`, nome, descrição, prompt de sistema, credencial, modelo, temperatura, idioma, tom, mensagem de "sem fonte", `active`), RLS; API `GET/POST/PATCH/DELETE /v1/workspaces/{id}/assistants` (listar: todos os membros, só ativos para viewer; escrever: owner/admin/editor); validação de que a credencial é do mesmo workspace; auditoria; migração; OpenAPI regenerado; `AGENTS.md`.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `api/`, `audit/`, `llm/`; modelos e rotas da F4.1, dependências da F2.1; seção 7.5 da visão; convenções.
- **Critérios de aceite**: `test_create_assistant_requires_editor`, `test_assistant_credential_must_belong_to_workspace`, `test_viewer_lists_only_active`, `test_assistants_isolated_by_workspace`; cobertura ≥ 95%.
- **Depende de**: F4.1.

#### F4.4 — Conversas, mensagens em streaming e feedback

- **Objetivo**: o motor do chat, respeitando a regra de citações.
- **Entregáveis**: `conversations/` com modelos `Conversation` (`workspace_id`, assistente, usuário, título, canal `panel`), `Message` (papel, conteúdo, `citations` JSON, modelo, tokens de entrada/saída, latência, status), `Feedback` (👍/👎 + comentário, um por mensagem e usuário), RLS; `Retriever` (Protocol) com `NullRetriever` em produção e fake nos testes; orquestrador: carrega janela de histórico, chama o retriever, **sem fonte → mensagem "sem fonte" do assistente + oferta de abrir chamado, sem chamar o LLM**; com fonte → prompt com contexto numerado, streaming do LLM, citações gravadas; API `POST /v1/workspaces/{id}/conversations` (criar), `GET` (minhas), `GET .../{cid}` (mensagens; dono, ou owner/admin), `POST .../{cid}/messages` (SSE: eventos `delta`, `citations`, `done`, `error`), `DELETE` (dono), `POST .../messages/{mid}/feedback`; título gerado da primeira pergunta (truncado, sem LLM); log estruturado com `conversation_id`; auditoria só de exclusão; migração; OpenAPI regenerado; `AGENTS.md`.
- **Contexto necessário**: `AGENTS.md` raiz (2 regra 8, 5, 6, 9); `backend/AGENTS.md`; AGENTS de `api/`, `llm/`, `assistants/`; `llm/*`, `assistants/*`, dependências da F2.1; seções 6.2, 7.4 e 7.5 da visão; convenções.
- **Critérios de aceite**: `test_no_source_returns_fallback_without_llm_call`, `test_with_sources_streams_and_saves_citations`, `test_sse_event_sequence`, `test_llm_error_emits_error_event_and_saves_status`, `test_history_window_limits_messages`, `test_member_cannot_read_others_conversation`, `test_admin_can_read_any_conversation`, `test_conversations_isolated_by_workspace`, `test_feedback_upsert`; cobertura ≥ 95%.
- **Depende de**: F4.2, F4.3.

#### F4.5 — Consulta administrativa de conversas

- **Objetivo**: visão de owner/admin sobre o uso do chat.
- **Entregáveis**: `GET /v1/workspaces/{id}/admin/conversations` (owner/admin; filtros por assistente, usuário, período, com feedback negativo; paginação; contagens de mensagens e feedback), `GET .../admin/conversations/{cid}`; `GET /v1/workspaces/{id}/admin/conversations/stats` (totais simples do período: conversas, mensagens, 👍, 👎, respostas sem fonte); consultas sem N+1; OpenAPI regenerado.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `api/`, `conversations/`; modelos e rotas da F4.4; convenções.
- **Critérios de aceite**: `test_admin_conversations_filters`, `test_admin_conversations_forbidden_for_editor`, `test_stats_counts`, `test_admin_conversations_isolated_by_workspace`, teste de número de consultas por listagem; cobertura ≥ 95%.
- **Depende de**: F4.4.

### F5 — Assistentes, chat e conversas (frontend)

#### F5.1 — Telas de provedores e assistentes

- **Objetivo**: configurar provedores de LLM e assistentes pelo painel.
- **Entregáveis**: `/w/:id/provedores` (lista, criar/editar com tipo, nome, `base_url` e chave mascarada; "testar conexão" com resultado; excluir com confirmação); `/w/:id/assistentes` (lista com status; formulário com nome, descrição, prompt de sistema, provedor, modelo, temperatura, idioma, tom, mensagem de "sem fonte", ativo); visibilidade por papel.
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/`, `src/components/`; shell da F3.2, componentes da F3.5, `src/lib/api/*`, handlers MSW; convenções.
- **Critérios de aceite**: testes de criação e edição com validação, chave nunca exibida após salvar, teste de conexão com sucesso e falha, viewer sem acesso; cobertura ≥ 95.
- **Depende de**: F3.5, F4.2, F4.3.

#### F5.2 — Chat com streaming

- **Objetivo**: a tela de chat dos membros.
- **Entregáveis**: `/w/:id/chat` e `/w/:id/chat/:conversationId`: lista de conversas (nova, renomeada pelo título, excluir), seletor de assistente ativo, thread com mensagens em Markdown seguro (sem HTML cru), composer com Enter/Shift+Enter, botão parar; hook único `useChatStream` para SSE (POST com `fetch` + leitura de stream, CSRF, cancelamento por `AbortController`, eventos `delta`/`citations`/`done`/`error`) em `lib/api/`; citações numeradas clicáveis (painel com fonte; neste plano aparecem só no caminho com fonte); mensagem "sem fonte" com botão "abrir chamado" desabilitado com dica "disponível quando houver integração de chamados"; feedback 👍/👎 com comentário opcional; rolagem e estado de digitação acessíveis (`aria-live`).
- **Contexto necessário**: `frontend/AGENTS.md` (streaming por hook único); AGENTS de `features/`, `src/lib/api/`; shell da F3.2, `src/lib/api/*`, handlers MSW; contrato SSE da F4.4 em `docs/specs/openapi.json` e na spec do chat; convenções.
- **Critérios de aceite**: testes do hook (sequência de eventos, erro, cancelamento), envio e renderização incremental, citações, fallback sem fonte, feedback, exclusão de conversa; cobertura ≥ 95.
- **Depende de**: F3.2, F4.4.

#### F5.3 — Tela de conversas (owner/admin)

- **Objetivo**: acompanhar o uso do chat.
- **Entregáveis**: `/w/:id/conversas`: cartões com totais do período, tabela paginada com filtros (assistente, usuário, período, só 👎), detalhe somente leitura da conversa com feedback e citações.
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/`, `src/components/`; componentes da F3.5 e da F5.2 (renderização de mensagens), `src/lib/api/*`, handlers MSW; convenções.
- **Critérios de aceite**: testes dos filtros, totais, detalhe e bloqueio para editor/viewer; cobertura ≥ 95.
- **Depende de**: F5.2, F4.5.

### F6 — Ponta a ponta e documentação

#### F6.1 — Compose, E2E contra a stack e CI

- **Objetivo**: provar os fluxos navegáveis de ponta a ponta.
- **Entregáveis**: compose de dev com `KNOBRIDGE_SECRET_KEY`, `public_base_url`, cookies não `Secure` só em dev, Mailpit; perfil ou arquivo `deploy/docker-compose.e2e.yml` que permite o provedor `fake`; Playwright em `frontend/e2e/` com projeto `stack` (baseURL do frontend do compose) cobrindo: setup → login → criar workspace e convidar owner (superadmin) → aceitar convite lendo o link pela API do Mailpit → convidar viewer → esqueci senha → redefinir → criar provedor `fake` e assistente → chat com resposta "sem fonte" e feedback → owner vê a conversa na tela de conversas → troca de tema persiste; job `e2e-stack` na CI que sobe o compose e roda o projeto; o smoke atual continua sem backend.
- **Contexto necessário**: `AGENTS.md` raiz (5, 8); `frontend/AGENTS.md`, `deploy/AGENTS.md`, `.github/workflows/AGENTS.md`; `deploy/docker-compose.yml`, `deploy/.env.example`, `frontend/playwright.config.ts`, `frontend/e2e/*`, `.github/workflows/ci.yml`; convenções.
- **Critérios de aceite**: E2E verde localmente contra o compose (verificado pelo orquestrador); actionlint limpo; `docker compose config` válido.
- **Depende de**: F3.6, F5.3.

#### F6.2 — Specs, guias e documentação final

- **Objetivo**: documentação na mesma entrega do comportamento.
- **Entregáveis**: `docs/specs/modelo-de-dados.md` completo (tabelas, RLS, diagrama Mermaid), `docs/specs/autenticacao.md` (sessão, CSRF, tokens, convites, papéis e matriz de permissões), `docs/specs/chat.md` (contrato SSE, regra de citações, `Retriever`); `docs/guias/primeiro-acesso.md` (setup, criar workspace, convidar, configurar provedor e assistente); `README.md`, `CHANGELOG.md`, `AGENTS.md` da raiz (estado) e AGENTS das pastas tocadas revisados; tabela da seção 9 da visão com linhas para os ADRs 0001–0003 (sem mudar decisões existentes).
- **Contexto necessário**: `AGENTS.md` raiz (7, 11); `docs/AGENTS.md`; ADRs 0001–0003; `docs/specs/*`; rotas e modelos do backend (leitura); convenções.
- **Critérios de aceite**: links relativos resolvem; Mermaid válido; `check_agents_md` e `check_plans` passam; pre-commit limpo.
- **Depende de**: F6.1.

## 5. Decisões

Ver `decisoes[]` no frontmatter. ADRs previstos: 0001 (tenancy e RLS, F1.1), 0002 (sessão server-side, F1.2), 0003 (segredos cifrados, F4.1).

## 6. Pendências do usuário

Nenhuma aberta.

## 7. Registro de andamento

- 2026-10-10 — entendimento concluído (9 respostas); plano criado; aguardando aprovação.
- 2026-10-10 — plano aprovado pelo usuário; início da execução.
- 2026-10-10 — F1.1 iniciada.
- 2026-10-10 — F1.1 concluída: 90 testes, cobertura 100%; RLS provada com papel dono e papel não dono; ADR 0001 (D9).
- 2026-10-10 — F1.2 iniciada.
- 2026-10-10 — F1.2 concluída: 153 testes, cobertura 100%; ADR 0002 (D10). KNOBRIDGE_SECRET_KEY no compose fica para F1.3/F6.1.

## 8. Encerramento

A preencher ao concluir.
