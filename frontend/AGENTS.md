# frontend/

**Função**: painel administrativo do KnoBridge em React + TypeScript. Fontes e conectores, canvas de pipelines (React Flow), execuções, coleções, assistentes, canais, conversas, custos e configurações do workspace. Estado: app Vite com providers (roteador, TanStack Query, i18n pt-BR), Tailwind v4 + shadcn/ui, cliente tipado gerado do OpenAPI (`src/lib/api/`), indicador de status da API no cabeçalho, autenticação (cliente com cookie de sessão e CSRF, hooks de sessão, guardas de rota e telas públicas de setup, login, recuperação e redefinição de senha, verificação de e-mail e aceite de convite em `src/features/auth/`, rotas em inglês), perfil e segurança da conta logada em `src/features/account/` (`/account/profile`, `/account/security`: nome, idioma, tema, verificação de e-mail, troca de senha e sessões), membros e convites do workspace em `src/features/members/` (`/w/:workspaceId/members`: leitura para todo membro, gestão por owner/admin) configurações em `src/features/settings/` (`/w/:workspaceId/settings`: nome do workspace), provedores de LLM em `src/features/providers/` (`/w/:workspaceId/providers`: cadastrar, editar com chave mascarada, testar conexão e excluir) e assistentes em `src/features/assistants/` (`/w/:workspaceId/assistants`: lista com status e quantas coleções usa, criar, editar (com as coleções e a similaridade mínima) e excluir), ambos para owner, admin e editor, coleções em `src/features/collections/` (`/w/:workspaceId/collections` e `/collections/:collectionId`: lista com contagens, criar, editar e excluir para owner, admin e editor; detalhe com as fontes da coleção e "Testar busca", também para viewer), fontes em `src/features/sources/` (`/w/:workspaceId/sources` e `/sources/:sourceId`: lista com última e próxima execução; criar (Git, pasta ou runner local, com runner, repositório, executor, modelos, orçamento, tempo limite, excerto e disparo a cada commit), editar, excluir, testar conexão, sincronizar e cancelar para owner, admin e editor; detalhe com execuções atualizadas por polling enquanto rodam, erros por documento e documentos indexados; na fonte runner, abas Módulos (sugeridos e manuais, editar, ligar/desligar, selecionar e rodar com o executor escolhido), Tarefas (ao vivo por polling enquanto houver tarefa ativa, detalhe com rejeições por motivo, cancelar), Conhecimento (por módulo, filtros por status e confiança, evidências com excerto, editar, aprovar, descartar e reabrir com atualização otimista, rejeitados da última tarefa com o motivo e exportação do `.md` do módulo) e Indexação, em `src/features/sources/harness/`), runners locais do harness em `src/features/runners/` (`/w/:workspaceId/runners`, owner e admin: lista com online/offline pelo último contato, versão, executores e repositórios; criar mostrando o token uma única vez com os comandos de instalação e configuração copiáveis; revogar e excluir com confirmação), chat dos membros em `src/features/chat/` (`/w/:workspaceId/chat` e `/chat/:conversationId`: conversas, assistente ativo, resposta em streaming pelo hook único `useChatStream`, Markdown seguro com `react-markdown`, citações (inclusive de item de conhecimento, com selo de confiança e evidências), "sem fonte" e avaliação), conversas do workspace em `src/features/conversations/` (`/w/:workspaceId/conversations` e `/conversations/:conversationId`, owner e admin: totais do período, filtros por assistente, usuário, período e 👎 na query string, tabela paginada no servidor e a conversa somente leitura com avaliações e citações), auditoria em `src/features/audit/` (`/w/:workspaceId/audit` e `/admin/audit`: filtros por ação, autor e período na query string, paginação no servidor e detalhe do evento), administração da instância em `src/features/admin/` (`/admin/workspaces`: criar com e-mail do proprietário, renomear, suspender e reativar; `/admin/users`: buscar, suspender, reativar, conceder e remover superadmin), tabela paginada, diálogo de confirmação, select de filtro e a renderização das respostas do assistente (Markdown, fontes, painel da fonte) compartilhados em `src/components/`, shell autenticado em `src/app/shell/` (sidebar recolhível por papel, seletor de workspace, menu do usuário, tema claro/escuro/sistema aplicado antes do primeiro paint pelo script inline do `index.html`, páginas esqueleto de Pipelines e Canais), páginas de feature carregadas sob demanda (code splitting por rota com `React.lazy`, em `src/app/lazyPage.tsx`), MSW nos testes, smoke E2E com Playwright, E2E dos fluxos navegáveis contra a stack do compose (`e2e/stack/`, incluindo a indexação de uma pasta sintética até a resposta com citação) e imagem nginx. As telas de produto começam por provedores e assistentes.

**Entra aqui**: aplicação Vite em `src/`, testes ao lado dos arquivos (`*.test.tsx`) e E2E em `e2e/`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` (configurações do pnpm), `components.json` (shadcn), configs de ESLint, Prettier, Vitest e Playwright (`playwright.config.ts` e `playwright.stack.config.ts`), `Dockerfile`, `nginx.conf`, `.dockerignore`, `README.md` curto.
**Não entra aqui**: o widget embutível (vai para `widget/`), documentação (vai para `docs/`), lógica de negócio que pertence ao backend, dados reais.

**Layout previsto** (crie cada pasta só quando for necessária, sempre com o seu `AGENTS.md`):

```
frontend/src/
  app/            # roteamento, providers, layout, páginas estruturais
  features/       # uma pasta por área: auth, sources, pipelines, runs, collections, assistants, channels, conversations, settings
  components/ui/  # shadcn/ui (gerado; editar só o necessário)
  components/     # componentes compartilhados próprios
  hooks/          # hooks React genéricos (caminho esperado pelo shadcn, ex.: use-mobile)
  lib/api/        # cliente gerado do OpenAPI do backend + hooks TanStack Query
  lib/            # utilitários puros (cobertura 100%)
  i18n/           # pt-BR primeiro; chaves em inglês
  test/           # setup do Vitest, handlers MSW, fábricas de dados
```

**Convenções locais**

- Node LTS, `pnpm`. TypeScript `strict`; sem `any` sem comentário; sem `@ts-ignore` (use `@ts-expect-error` com motivo).
- ESLint + Prettier. A CI falha com aviso.
- Estado de servidor só via TanStack Query; estado local via hooks; store global só com necessidade demonstrada.
- Cliente de API gerado do OpenAPI do backend. Nunca escrever tipos de resposta à mão. Toda chamada passa por `lib/api/`. Contrato em `docs/specs/openapi.json`; `pnpm gen:api` regenera `src/lib/api/schema.gen.ts` e `pnpm check:api` (CI) falha se ele estiver desatualizado.
- A API é chamada na mesma origem, sob `/v1` (`VITE_API_BASE_URL`, padrão `/`): em desenvolvimento o proxy do Vite repassa para `127.0.0.1:8000`; na imagem, o `nginx.conf` repassa para o serviço `api` do compose.
- Dependências com script de instalação precisam de decisão explícita em `allowBuilds` no `pnpm-workspace.yaml`; exceções de peer dependency ficam em `peerDependencyRules`, com comentário. `pnpm peers check` deve sair limpo.
- Canvas: React Flow (xyflow). Nós e arestas tipados; o grafo salvo é o contrato com o backend (spec em `docs/specs/`).
- Componentes de `features/` não conhecem `fetch`; recebem dados por hooks. Componentes pequenos; lógica em funções puras em `lib/`, testadas isoladamente.
- Acessibilidade: elementos semânticos, foco visível, labels. Testes com Testing Library consultam por papel e texto, nunca por classe CSS.
- Textos de interface em pt-BR via i18n desde o início; nada hardcoded. URLs do painel em inglês (plano 0002, D11): públicas `/setup`, `/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/accept-invitation`; autenticadas `/w/:workspaceId/...`, `/account/...`, `/admin/...`.
- Formulários com react-hook-form + zod (`@hookform/resolvers`) e os componentes de `components/ui/form.tsx`; mensagens de erro da API pelo `code`, via `translateApiError` de `src/i18n/apiErrors.ts`.
- Streaming de respostas (SSE) tratado por um hook único, reutilizado pelo chat de teste e pela visualização de conversas.

**Como testar**

```sh
pnpm lint && pnpm typecheck
pnpm test -- --coverage        # Vitest; thresholds de 95 em lines, branches, functions e statements
pnpm check:api                 # tipos do cliente em dia com docs/specs/openapi.json
pnpm e2e                       # Playwright: fluxos críticos do canvas e do chat de teste
pnpm e2e:stack                 # Playwright contra a stack do compose já no ar (e2e/stack/)
```

- Vitest + Testing Library para componentes e hooks; MSW para a API (nunca mockar `fetch` à mão; handlers por recurso em `src/test/handlers/`). O Vitest lê só `src/**/*.test.{ts,tsx}`.
- Playwright só para os poucos fluxos críticos; na CI (job `frontend` de `.github/workflows/ci.yml`) rodam contra o build de produção servido pelo `vite preview`, sem backend. Fluxos que precisam da API real ficam em `e2e/stack/`, com `playwright.stack.config.ts` (projeto `stack`, `baseURL` por `E2E_BASE_URL`), e rodam no job `e2e-stack` contra `deploy/docker-compose.yml` + `deploy/docker-compose.e2e.yml`.
- Componentes de `components/ui/` gerados pelo shadcn podem ficar fora da medição de cobertura, com justificativa no `vitest.config.ts`.

**Leia também**: `AGENTS.md` da raiz (seções 5 e 6.3); `docs/01-visao-do-projeto.md`, seções 7.2 e 8.
