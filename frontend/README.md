# KnoBridge — frontend

Painel administrativo do KnoBridge (Vite + React + TypeScript).

Requisitos: Node 24+ e pnpm (versão fixada em `packageManager` no `package.json`).

```sh
pnpm install --frozen-lockfile   # instalar dependências
pnpm dev                         # servidor de desenvolvimento em http://localhost:5173
pnpm build                       # typecheck + build de produção em dist/
```

Testes e gates:

```sh
pnpm lint && pnpm format:check && pnpm typecheck
pnpm test -- --coverage          # Vitest com cobertura (gate de 95%)
pnpm test:watch                  # modo watch, sem cobertura
```

Convenções em [AGENTS.md](AGENTS.md).
