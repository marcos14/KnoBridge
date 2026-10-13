# frontend/src/features/usage/

**Função**: tela **Uso e custos** do workspace em `/w/:workspaceId/usage`, para owner e admin: tokens e custo estimado em US$ de embeddings e do chat num período, agrupados, com totais, gráfico por dia e exportação CSV. Editor e viewer não veem o item do menu e recebem 403 na rota (`minRole: "admin"` em `app/shell/navItems.ts`). Contrato em `docs/specs/uso-e-custos.md`.

**Entra aqui**:

- `UsagePage.tsx`: título, barra de período e agrupamento, botão "Exportar CSV" (download pelo navegador com o nome do `Content-Disposition`; erro mostrado na tela) e o relatório: carregando, erro com o motivo traduzido (ex.: 422 `usage_period_too_long`) e "Tentar novamente", totais, gráfico (só em `group_by=day`) e tabela.
- `UsageFilterBar.tsx`: período (este mês, mês passado, últimos 30 dias, personalizado com "De"/"Até") e agrupamento (dia, fonte, coleção, assistente, canal, chave de API, modelo); cada mudança vale na hora. "Personalizado" começa com os dias do período que estava na tela.
- `UsageTotals.tsx`: período devolvido pela API (fim exclusivo convertido no último dia, em UTC), custo estimado total, cartões de embeddings e de chat e o aviso "Custo parcial" quando `unpriced_runs`/`unpriced_answers` > 0.
- `UsageTable.tsx`: uma linha por grupo com só as colunas que se aplicam ao agrupamento, ordenação por qualquer coluna (cabeçalho com `aria-sort`; até o primeiro clique, a ordem da API), marca de custo parcial na linha e os totais no rodapé. Canais traduzidos; dias formatados.
- `UsageDayChart.tsx`: barras do custo por dia em CSS puro (sem biblioteca de gráfico), uma série, cada barra com dia e custo no `title` e no nome acessível; os valores exatos ficam na tabela.
- `usageRows.ts`: colunas por agrupamento, ordenação (nulos por último nos dois sentidos, empate pelo rótulo), `isPartialRow` e `formatUsageDay`.
- `useUsageSearch.ts`: período e agrupamento na query string (`?period=&from=&to=&group=`).

**Não entra aqui**: chamadas de API (`lib/api/usage.ts`), leitura e escrita da query string e cálculo do período (`lib/usagePeriod.ts`), formatação de US$ e contagens (`lib/numberFormat.ts`), textos (`i18n/locales/`, chaves `usage.*`).

**Convenções locais**:

- O período é em dias **UTC**, como o backend agrega: `[meia-noite UTC de "De", meia-noite UTC do dia seguinte a "Até")`. Assim as linhas por dia e o nome do CSV batem com o que a tela mostra.
- Valores em US$ são estimativas; preço desconhecido nunca vira zero na tela: coluna que não se aplica mostra "—" e o aviso de custo parcial explica o que ficou de fora.
- A URL é a fonte do filtro: link compartilhado abre a mesma visão; valor inválido volta ao padrão (este mês, por dia).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/usage?..." })`) com MSW: `usageRecorder(report)` guarda a query string do relatório e do CSV; `usageAs`, `usageFails`, `usageCsvFails`, `usageCsvPending`, `usageCsvWithoutName`; dados em `@/test/usageFactories`. Downloads com `stubDownloads()`. O relógio é `TEST_NOW` (2026-10-10T12:00Z).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/uso-e-custos.md`.
