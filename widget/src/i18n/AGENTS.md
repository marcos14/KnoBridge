# widget/src/i18n/

**Função**: textos de interface do widget. `pt-BR.ts` é o catálogo (único idioma nesta versão); `index.ts` escolhe o catálogo pelo `lang` do elemento ou da configuração, com pt-BR como padrão, e preenche os `{marcadores}`.

**Entra aqui**: catálogos de textos e a função de tradução.
**Não entra aqui**: textos vindos do painel (título, saudação, placeholder chegam pela configuração pública), mensagens da API.

**Convenções locais**: chaves em inglês; idioma novo é um arquivo com as mesmas chaves (`Messages`) registrado em `CATALOGS`. Plural simples por chave própria (ex.: `rateLimitedOne`).

**Como testar**: de `widget/`, `pnpm test`.

**Leia também**: [../AGENTS.md](../AGENTS.md).
