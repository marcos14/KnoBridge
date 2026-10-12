# KnoBridge — frontend

Painel administrativo do KnoBridge (Vite + React + TypeScript, Tailwind v4 + shadcn/ui).

Requisitos: Node 24+ e pnpm (versão fixada em `packageManager` no `package.json`).

```sh
pnpm install --frozen-lockfile   # instalar dependências
pnpm dev                         # servidor de desenvolvimento em http://localhost:5173
pnpm build                       # typecheck + build de produção em dist/
```

Em desenvolvimento, chamadas a `/v1` vão por proxy para a API em `http://127.0.0.1:8000` (suba com `uv run knobridge-api` em `backend/`). Para outra origem, defina `VITE_API_BASE_URL` (ex.: `VITE_API_BASE_URL=https://api.exemplo.test pnpm dev`).

Cliente da API (tipos gerados de `docs/specs/openapi.json`):

```sh
pnpm gen:api                     # regenera src/lib/api/schema.gen.ts
pnpm check:api                   # falha se os tipos estiverem desatualizados (CI)
```

Testes e gates:

```sh
pnpm lint && pnpm format:check && pnpm typecheck
pnpm test -- --coverage          # Vitest com cobertura (gate de 95%)
pnpm test:watch                  # modo watch, sem cobertura
pnpm exec playwright install chromium   # uma vez, antes do primeiro E2E
pnpm e2e                         # Playwright: build + vite preview na porta 4173
pnpm e2e:stack                   # Playwright contra a stack do compose já no ar
```

O `e2e:stack` precisa da stack de `deploy/docker-compose.yml` + `deploy/docker-compose.e2e.yml` no ar; passo a passo em [docs/guias/subir-ambiente.md](../docs/guias/subir-ambiente.md).

Imagem Docker (nginx servindo `dist/`, com fallback de SPA e proxy de `/v1/` para o serviço `api`):

```sh
docker build -t knobridge-frontend frontend      # da raiz do repositório
docker run --rm -p 8080:80 knobridge-frontend    # http://localhost:8080
```

Fora do compose não há serviço `api`: o indicador de status mostra "indisponível" e as rotas, que consultam `/v1/setup/status` e `/v1/me` antes de abrir, mostram o aviso de falha com "Tentar novamente".

Convenções em [AGENTS.md](AGENTS.md).
