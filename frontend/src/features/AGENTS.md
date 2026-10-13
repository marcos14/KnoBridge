# frontend/src/features/

**Função**: uma pasta por área do painel, com suas telas, componentes específicos e lógica de apresentação. Hoje: `auth/` (telas públicas de setup, login, senha, verificação e convite; guardas de rota, página 403 e sessão), `account/` (perfil e segurança da conta logada), `members/` (membros e convites do workspace), `settings/` (configurações do workspace), `providers/` (provedores de LLM), `assistants/` (assistentes), `collections/` (coleções, fontes de cada coleção e teste de busca), `sources/` (fontes, inclusive as do tipo runner com módulos e tarefas do harness e as de chamados com token de envio, upload e prévia, execuções com status ao vivo, erros por documento e documentos indexados), `runners/` (runners locais do harness, para owner e admin), `chat/` (chat dos membros com streaming), `conversations/` (uso do chat e conversas de todos os membros, para owner e admin), `usage/` (uso e custos de embeddings e do chat por período, com CSV, para owner e admin), `audit/` (auditoria do workspace e da instância) e `admin/` (workspaces e usuários da instância, para superadmin).

**Entra aqui**: subpastas por área (`auth`, `account`, depois `sources`, `pipelines`, `runs`, `collections`, `assistants`, `channels`, `conversations`, `settings`…), cada uma com o seu `AGENTS.md`.
**Não entra aqui**: chamadas de API e hooks TanStack Query (`lib/api/`), componentes reutilizados entre áreas (`components/`), componentes shadcn (`components/ui/`), roteamento e providers (`app/`), textos (`i18n/locales/`).

**Convenções locais**:

- Componentes de feature não conhecem `fetch`: recebem dados pelos hooks de `lib/api/`.
- Uma área não importa a pasta interna de outra; o que for compartilhado sobe para `components/` ou `lib/`.
- Lógica sem JSX em funções puras, com teste próprio.
- Telas são ligadas às rotas em `app/router.tsx`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage` (testes ao lado dos arquivos, com Testing Library + MSW).

**Leia também**: [../AGENTS.md](../AGENTS.md), [../../AGENTS.md](../../AGENTS.md).
