# frontend/src/i18n/

**Função**: internacionalização do painel com i18next. Instância única, idioma padrão pt-BR.

**Entra aqui**: `index.ts` (cria e inicializa a instância `i18n`, exporta `resources`), `i18next.d.ts` (tipa as chaves a partir do pt-BR), `apiErrors.ts` (`apiErrorKey` e `translateApiError`: mensagem de erro da API pelo `code`, com `network` para falha de rede e `unknown` para o resto) e a pasta `locales/`.
**Não entra aqui**: textos de tradução soltos em código (vão para `locales/*.json`), formatação de datas e números específica de feature (`lib/`).

**Convenções locais**:

- `lng` e `fallbackLng` são `pt-BR`; recursos são empacotados no bundle e a inicialização é síncrona.
- As chaves são tipadas: `t("chave.inexistente")` não compila. Chave ausente em runtime devolve a própria chave.
- Idioma novo: um JSON em `locales/` e uma entrada em `resources`, com as mesmas chaves do pt-BR.
- Código de erro novo no backend: chave nova em `apiErrors.<code>` no `pt-BR.json`; sem ela a interface mostra a mensagem genérica.

**Como testar**: de `frontend/`, `pnpm test -- --coverage` (testes em `index.test.ts`).

**Leia também**: [locales/AGENTS.md](locales/AGENTS.md), [../AGENTS.md](../AGENTS.md).
