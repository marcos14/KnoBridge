# frontend/src/features/audit/

**Função**: telas da trilha de auditoria. `/w/:workspaceId/audit` (owner e admin) mostra os eventos do workspace; `/admin/audit` (superadmin) mostra os eventos da instância (setup, entradas, trabalho dos superadministradores). As duas usam o mesmo `AuditLog`.

**Entra aqui**:

- `WorkspaceAuditPage.tsx` e `InstanceAuditPage.tsx`: título e origem dos eventos (`useWorkspaceAudit` ou `useInstanceAudit`) e dos autores (membros do workspace ou a primeira página de usuários da instância, até 200).
- `AuditLog.tsx`: barra de filtros, tabela paginada pela API (`DataTable`, 20 por página), estados de carregando, erro com "Tentar novamente", vazio (com ou sem filtro) e o diálogo de detalhe.
- `AuditFilterBar.tsx`: ação (todas as ações do contrato, com rótulo pt-BR), autor, período "De"/"Até" (dias inclusivos) e "Limpar filtros". Cada mudança vale na hora. Os selects são o `FilterSelect` de `components/`.
- `AuditEventDialog.tsx`: todos os campos do evento e os `details` chave a chave (texto como está, o resto em JSON indentado).
- `useAuditSearch.ts`: filtros e página na query string (`?action=&actor=&from=&to=&offset=`); mudar filtro volta para a primeira página.
- `actors.ts`: nome do autor (`Sistema` sem autor, `Usuário <id>` para quem não está na lista).

**Não entra aqui**: chamadas de API (`lib/api/audit.ts`, `lib/api/admin.ts`), leitura e escrita da query string e conversão do período (`lib/auditFilters.ts`, com os dias de `lib/days.ts`), lista de ações (`lib/auditActions.ts`), rótulo das ações (`i18n/auditActions.ts`, chaves `auditActions.*`), telas de administração (`features/admin/`).

**Convenções locais**:

- A URL é a fonte dos filtros: link compartilhado abre a mesma visão; valor que a API recusaria (ação desconhecida, id ou dia malformado) é ignorado.
- O período vai para a API como `[início de "De", início do dia seguinte a "Até")` no fuso do navegador.
- Ação nova no contrato quebra o typecheck de `lib/auditActions.ts` até ganhar entrada lá e rótulo em `auditActions.*`; ação desconhecida em runtime aparece pelo código cru.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Testes pela árvore real (`renderWithProviders({ path: "/w/<id>/audit?..." })`) com MSW: `auditRecorder(scope, events)` guarda a query string de cada requisição; `auditAs`, `auditServerError`. Datas com `fireEvent.change` (o `userEvent.type` não preenche `input[type=date]` no jsdom).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`/v1/workspaces/{workspace_id}/audit`, `/v1/admin/audit`).
