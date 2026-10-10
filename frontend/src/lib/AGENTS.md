# frontend/src/lib/

**Função**: código sem interface. Utilitários puros e, em `api/`, o acesso ao backend.

**Entra aqui**:

- `utils.ts`: `cn()` (junta classes e resolve conflitos do Tailwind), usado pelos componentes do shadcn/ui e pelos nossos.
- `storage.ts`: `readStoredItem`/`writeStoredItem`/`removeStoredItem`, acesso ao `localStorage` (padrão) ou ao `sessionStorage` (`"session"`, só a aba atual) que nunca lança (janela privada, dados bloqueados → "nada guardado"). Só para conveniências do navegador (tema, último workspace, convite pendente durante o login).
- `theme.ts`: `Theme`, `THEMES`, `resolveTheme`, `applyTheme` (classe `dark` e `color-scheme` no `<html>`), `storeTheme`. A chave `knobridge-theme` é lida também pelo script inline do `index.html` (primeiro paint): mude os dois juntos.
- `lastWorkspace.ts`: último workspace usado (`localStorage`) e `pickWorkspace` (último, se ainda membro e ativo; senão o primeiro ativo; senão o primeiro).
- `initials.ts`: iniciais para o avatar.
- `api/`: cliente gerado do OpenAPI e hooks TanStack Query (ver [api/AGENTS.md](api/AGENTS.md)).
- Futuramente: funções puras de domínio usadas por várias features (formatação, validação, transformação do grafo do canvas).

**Não entra aqui**: componentes React (`components/` ou `features/`), textos de interface (`i18n/`), helpers de teste (`test/`).

**Convenções locais**:

- Funções puras, pequenas e tipadas; sem estado global nem efeitos colaterais na importação (exceção: a instância `apiClient`). Efeitos no navegador (`localStorage`, `<html>`) só em funções chamadas explicitamente.
- Cobertura de 100% esperada: cada função com teste ao lado (`*.test.ts`).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../AGENTS.md](../../AGENTS.md).
